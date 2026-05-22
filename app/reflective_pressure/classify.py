from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.reflective_pressure.models import build_classification_record, validate_input_record


def classify_input(input_record: Mapping[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    validate_input_record(input_record)
    text = " ".join(
        [
            str(input_record.get("source_type") or ""),
            str(input_record.get("source_context") or ""),
            str(input_record.get("raw_text") or ""),
            " ".join(str(tag) for tag in input_record.get("tags") or []),
        ]
    ).lower()

    rule = _select_rule(text)
    return build_classification_record(
        input_id=str(input_record["input_id"]),
        surface_claim=rule["surface_claim"],
        hidden_pressure=rule["hidden_pressure"],
        pressure_type=rule["pressure_type"],
        moral_temperature=rule["moral_temperature"],
        ambiguity_level=rule["ambiguity_level"],
        audience_self_insertion_potential=rule["audience_self_insertion_potential"],
        risk_of_tribal_escalation=rule["risk_of_tribal_escalation"],
        recognition_potential=rule["recognition_potential"],
        recommended_output_type=rule["recommended_output_type"],
        rationale=rule["rationale"],
        confidence=rule["confidence"],
        created_at=created_at,
    )


def _select_rule(text: str) -> dict[str, Any]:
    if _contains_any(text, ("scripture", "bible", "salvation", "gospel", "jesus", "sin", "repent")):
        return _rule(
            pressure_type="spiritual_reductionism",
            surface_claim="The input invokes sacred or doctrinal language.",
            hidden_pressure="A sacred frame may be compressing a larger human tension into a smaller certainty.",
            recommended_output_type="theological_reflection",
            rationale="scripture_language_rule fired on scripture, Bible, salvation, gospel, or adjacent terms.",
            moral_temperature=3,
            ambiguity_level=4,
            audience_self_insertion_potential=3,
            risk_of_tribal_escalation=3,
            recognition_potential=4,
            confidence=0.72,
        )
    if _contains_any(text, ("mockery", "sarcasm", "lol", "meme", "haha", "joking", "roast")):
        return _rule(
            pressure_type="humor_as_shield",
            surface_claim="The input carries pressure through humor, mockery, or meme language.",
            hidden_pressure="The joke may be protecting something more vulnerable than the surface tone admits.",
            recommended_output_type="reply",
            rationale="humor_language_rule fired on mockery, sarcasm, lol, meme, or adjacent terms.",
            moral_temperature=2,
            ambiguity_level=3,
            audience_self_insertion_potential=4,
            risk_of_tribal_escalation=2,
            recognition_potential=4,
            confidence=0.7,
        )
    if _contains_any(text, ("hypocrisy", "hypocrite", "double standard", "expose", "heart", "performative")):
        return _rule(
            pressure_type="moral_contradiction_exposure",
            surface_claim="The input is naming perceived hypocrisy or contradiction.",
            hidden_pressure="The deeper tension is the pain of seeing public claims split from private reality.",
            recommended_output_type="short_post",
            rationale="moral_contradiction_rule fired on hypocrisy, double standard, expose, heart, or adjacent terms.",
            moral_temperature=4,
            ambiguity_level=3,
            audience_self_insertion_potential=4,
            risk_of_tribal_escalation=4,
            recognition_potential=4,
            confidence=0.74,
        )
    if _contains_any(text, ("offended", "misunderstood", "intent", "accusation", "accused", "defensive")):
        return _rule(
            pressure_type="peace_vs_escalation",
            surface_claim="The input is orbiting offense, intent, or accusation.",
            hidden_pressure="The pressure is whether the moment becomes recognition or escalation.",
            recommended_output_type="reply",
            rationale="peace_escalation_rule fired on offended, misunderstood, intent, accusation, or adjacent terms.",
            moral_temperature=3,
            ambiguity_level=4,
            audience_self_insertion_potential=4,
            risk_of_tribal_escalation=3,
            recognition_potential=4,
            confidence=0.7,
        )
    if _contains_any(text, ("authority", "government", "system", "money", "power", "institution")):
        return _rule(
            pressure_type="authority_confusion",
            surface_claim="The input is naming power, authority, or institutional pressure.",
            hidden_pressure="The deeper tension is uncertainty about which authority is legitimate and which is merely loud.",
            recommended_output_type="system_note",
            rationale="authority_language_rule fired on authority, government, system, money, power, or adjacent terms.",
            moral_temperature=3,
            ambiguity_level=4,
            audience_self_insertion_potential=3,
            risk_of_tribal_escalation=3,
            recognition_potential=3,
            confidence=0.68,
        )
    if _contains_any(text, ("lonely", "loneliness", "unseen", "nobody understands", "ignored", "invisible")):
        return _rule(
            pressure_type="recognition_deprivation",
            surface_claim="The input is naming being unseen or misunderstood.",
            hidden_pressure="The deeper pressure is the desire to be recognized without needing to perform pain.",
            recommended_output_type="letter_of_light_seed",
            rationale="recognition_deprivation_rule fired on loneliness, unseen, nobody understands, or adjacent terms.",
            moral_temperature=2,
            ambiguity_level=3,
            audience_self_insertion_potential=5,
            risk_of_tribal_escalation=1,
            recognition_potential=5,
            confidence=0.76,
        )
    if _contains_any(text, ("slogan", "slogans", "certainty", "obvious", "everyone knows", "just admit")):
        return _rule(
            pressure_type="shallow_certainty",
            surface_claim="The input is reacting against flattened certainty or slogan-level speech.",
            hidden_pressure="The deeper tension is the frustration of complex pressure being reduced too quickly.",
            recommended_output_type="reply",
            rationale="shallow_certainty_rule fired on slogan, certainty, obvious, everyone knows, or adjacent terms.",
            moral_temperature=2,
            ambiguity_level=4,
            audience_self_insertion_potential=4,
            risk_of_tribal_escalation=2,
            recognition_potential=4,
            confidence=0.66,
        )
    return _rule(
        pressure_type="unknown",
        surface_claim="The input contains pressure that is not yet clearly typed.",
        hidden_pressure="There may be a meaningful tension here, but v0 rules do not classify it confidently.",
        recommended_output_type="pressure_log_entry",
        rationale="default_unknown_rule fired because no deterministic v0 keyword rule matched.",
        moral_temperature=1,
        ambiguity_level=5,
        audience_self_insertion_potential=2,
        risk_of_tribal_escalation=1,
        recognition_potential=2,
        confidence=0.35,
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _rule(**values: Any) -> dict[str, Any]:
    return dict(values)
