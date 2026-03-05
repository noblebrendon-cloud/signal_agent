"""Deterministic feature extraction for Interaction Signals v0.1."""
from __future__ import annotations
from .types import Event, Features
from .ema import clamp01
from .tokenize import tokenize, count_questions, count_sentences, has_code_fence, has_url, has_digits
from .lexicons import (
    CERTAINTY_MARKERS, HEDGE_MARKERS, CAUSAL_MARKERS, INTEGRATION_MARKERS,
    EXTRACTION_MARKERS, AUTHORITY_MARKERS, ADVERSARIAL_MARKERS, PROMO_MARKERS,
    CHALLENGE_MARKERS, REPAIR_MARKERS, CONTACT_PULL_MARKERS, SELF_REF_TOKENS,
)


def _hit(text_lower: str, tokens: list[str], lexicon: frozenset[str]) -> int:
    """Count lexicon matches (phrase match for multi-word, token match for single)."""
    count = 0
    for phrase in lexicon:
        if " " in phrase:
            count += text_lower.count(phrase)
        else:
            count += tokens.count(phrase)
    return count


def _ratio(count: int, total: int, scale: float = 1.0) -> float:
    return clamp01(count * scale / max(1, total))


def compute_features(event: Event) -> Features:
    text = event.text
    meta = event.meta
    tl = text.lower()
    tokens = tokenize(text)
    n_tok = max(1, len(tokens))
    n_sent = count_sentences(text)
    n_q = count_questions(text)

    h_cert  = _hit(tl, tokens, CERTAINTY_MARKERS)
    h_hedge = _hit(tl, tokens, HEDGE_MARKERS)
    h_auth  = _hit(tl, tokens, AUTHORITY_MARKERS)
    h_self  = _hit(tl, tokens, SELF_REF_TOKENS)
    h_ext   = _hit(tl, tokens, EXTRACTION_MARKERS)
    h_caus  = _hit(tl, tokens, CAUSAL_MARKERS)
    h_integ = _hit(tl, tokens, INTEGRATION_MARKERS)
    h_adv   = _hit(tl, tokens, ADVERSARIAL_MARKERS)
    h_promo = _hit(tl, tokens, PROMO_MARKERS)
    h_chal  = _hit(tl, tokens, CHALLENGE_MARKERS)
    h_rep   = _hit(tl, tokens, REPAIR_MARKERS)
    h_cont  = _hit(tl, tokens, CONTACT_PULL_MARKERS)

    q_ratio           = clamp01(n_q / max(1, n_sent))
    certainty_ratio   = _ratio(h_cert, n_tok)
    hedge_ratio       = _ratio(h_hedge, n_tok, 3.0)
    authority_ref_ratio = _ratio(h_auth, n_tok, 4.0)
    self_ref_ratio    = _ratio(h_self, n_tok)
    extraction_ratio  = _ratio(h_ext, n_tok, 5.0)
    causal_ratio      = _ratio(h_caus, n_tok, 4.0)
    integration_ratio = _ratio(h_integ, n_tok, 4.0)
    adversarial_tone  = _ratio(h_adv, n_tok, 5.0)
    promo_density     = _ratio(h_promo, n_tok, 5.0)
    challenge_intensity = _ratio(h_chal, n_tok, 4.0)

    long_words = sum(1 for t in tokens if len(t) >= 8)
    abstraction_ratio = _ratio(long_words, n_tok, 2.0)

    example_given = (
        has_digits(text) or has_code_fence(text)
        or "e.g." in tl or "example:" in tl
        or "for example" in tl or "confidence:" in tl
        or "instance:" in tl
    )
    example_request = (
        n_q > 0 and (
            "give me an example" in tl or "can you give" in tl
            or "show me" in tl or "demonstrate" in tl
        )
    )
    proof_move = (
        has_url(text) or has_code_fence(text)
        or "benchmark" in tokens or "log" in tokens
        or ("test" in tokens and has_digits(text))
        or ("show" in tokens and has_digits(text))
    )
    challenge_present = h_chal > 0
    repair_attempt    = h_rep > 0
    contact_pull      = h_cont > 0

    # Scope control: token overlap with reply_to
    reply_to = meta.get("reply_to", "")
    if reply_to:
        prev_toks = set(tokenize(reply_to))
        curr_toks = set(tokens)
        if prev_toks and curr_toks:
            scope_control = clamp01(len(prev_toks & curr_toks) / max(1, min(len(prev_toks), len(curr_toks))))
        else:
            scope_control = 0.5
    else:
        scope_control = 0.5

    question_follow_through = not (
        challenge_present and causal_ratio < 0.03 and integration_ratio < 0.03
    )

    novelty_injection = clamp01(
        0.3 * float(example_given) + 0.2 * float(proof_move) + 0.1 * integration_ratio
    )
    synthesis_quality = clamp01(
        0.4 * integration_ratio + 0.3 * causal_ratio
        + 0.2 * float(example_given) + 0.1 * hedge_ratio
    )
    time_to_concrete = 0.5  # placeholder

    return Features(event_id=event.event_id, f={
        "q_ratio":               q_ratio,
        "certainty_ratio":       certainty_ratio,
        "hedge_ratio":           hedge_ratio,
        "authority_ref_ratio":   authority_ref_ratio,
        "self_ref_ratio":        self_ref_ratio,
        "extraction_ratio":      extraction_ratio,
        "causal_ratio":          causal_ratio,
        "integration_ratio":     integration_ratio,
        "abstraction_ratio":     abstraction_ratio,
        "example_request":       example_request,
        "example_given":         example_given,
        "challenge_present":     challenge_present,
        "challenge_intensity":   challenge_intensity,
        "repair_attempt":        repair_attempt,
        "adversarial_tone":      adversarial_tone,
        "proof_move":            proof_move,
        "question_follow_through": question_follow_through,
        "scope_control":         scope_control,
        "time_to_concrete":      time_to_concrete,
        "contact_pull":          contact_pull,
        "promo_density":         promo_density,
        "novelty_injection":     novelty_injection,
        "synthesis_quality":     synthesis_quality,
    })
