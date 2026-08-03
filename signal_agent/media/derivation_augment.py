from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from signal_agent.inference import (
    GovernedInferenceCache,
    InferenceRequestContext,
    PromptEnvelope,
    REASON_CONSTRAINT_PACK_MISMATCH,
    REASON_MODEL_MISMATCH,
    REASON_PAYLOAD_VALIDATION_FAILED,
    fingerprint_payload,
    fingerprint_text,
    stable_json_dumps,
)


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
REPO_ROOT = Path(__file__).resolve().parents[2]
_DERIVATION_VALIDATOR_ID = "derivation_augment_result_v1"
_CACHE_RUNTIME_FIELDS = {
    "cache_entry_id",
    "cache_similarity",
    "cache_status",
    "prefix_cache_eligible",
    "prefix_fingerprint",
    "prompt_fingerprint",
}
_DERIVATION_SYSTEM_INSTRUCTION = (
    "You are a semantic derivation augmentation engine operating inside a deterministic "
    "content pipeline.\n\n"
    "Your task is to analyze a transcript and return a JSON object that improves downstream "
    "deterministic artifact generation.\n\n"
    "You do not write final social posts.\n"
    "You do not rewrite the transcript.\n"
    "You do not produce markdown.\n\n"
    "You only return structured semantic guidance.\n\n"
    "Rules:\n"
    "- Return valid JSON only.\n"
    "- No surrounding commentary.\n"
    "- No code fences.\n"
    "- Be concise and specific.\n"
    "- Preserve the source intent.\n"
    "- Prefer concrete themes over vague abstractions.\n"
    "- Hooks must be platform-agnostic but audience-relevant.\n"
    "- Voice drift score must estimate how likely the content is to drift away from the source tone if aggressively repurposed.\n"
    "- voice_drift_score must be a float from 0.0 to 1.0.\n"
)
_DERIVATION_OUTPUT_SCHEMA = {
    "thematic_summary": "string, 2-3 sentences",
    "audience_hooks": ["string", "string", "string"],
    "semantic_topics": ["string"],
    "voice_drift_score": "float 0.0-1.0",
    "voice_notes": ["string"],
    "repurposing_risks": ["string"],
}
_DERIVATION_STATIC_USER_PAYLOAD = {
    "task": "semantic_derivation_augmentation",
    "output_schema": _DERIVATION_OUTPUT_SCHEMA,
}
_DERIVATION_STATIC_USER_PAYLOAD_JSON = stable_json_dumps(
    _DERIVATION_STATIC_USER_PAYLOAD,
    ensure_ascii=False,
)
_DERIVATION_STATIC_PREFIX_TEXT = "\n\n".join(
    (
        "SYSTEM INSTRUCTION:",
        _DERIVATION_SYSTEM_INSTRUCTION,
        "USER PAYLOAD STATIC CONTENT:",
        _DERIVATION_STATIC_USER_PAYLOAD_JSON,
        "USER PAYLOAD DYNAMIC CONTENT:",
    )
)


@dataclass(frozen=True)
class DerivationAugmentResult:
    thematic_summary: str
    audience_hooks: list[str]
    semantic_topics: list[str]
    voice_drift_score: float | None
    voice_notes: list[str]
    repurposing_risks: list[str]
    generation_prompt: str
    generation_response: str
    model_id: str
    latency_ms: int
    used_fallback: bool
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "thematic_summary": self.thematic_summary,
            "audience_hooks": self.audience_hooks,
            "semantic_topics": self.semantic_topics,
            "voice_drift_score": self.voice_drift_score,
            "voice_notes": self.voice_notes,
            "repurposing_risks": self.repurposing_risks,
            "generation_prompt": self.generation_prompt,
            "generation_response": self.generation_response,
            "model_id": self.model_id,
            "latency_ms": self.latency_ms,
            "used_fallback": self.used_fallback,
            "failure_reason": self.failure_reason,
        }


def _fallback_result(
    *,
    prompt_text: str,
    model_id: str,
    failure_reason: str,
    latency_ms: int = 0,
) -> DerivationAugmentResult:
    return DerivationAugmentResult(
        thematic_summary="",
        audience_hooks=[],
        semantic_topics=[],
        voice_drift_score=None,
        voice_notes=[],
        repurposing_risks=[],
        generation_prompt=prompt_text,
        generation_response="",
        model_id=model_id,
        latency_ms=latency_ms,
        used_fallback=True,
        failure_reason=failure_reason,
    )


def _safe_list_of_str(value: Any, *, limit: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                out.append(cleaned)
    if limit is not None:
        return out[:limit]
    return out


def _safe_float_0_1(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _normalize_response(
    raw: dict[str, Any],
    *,
    prompt_text: str,
    response_text: str,
    model_id: str,
    latency_ms: int,
) -> DerivationAugmentResult:
    return DerivationAugmentResult(
        thematic_summary=str(raw.get("thematic_summary", "")).strip(),
        audience_hooks=_safe_list_of_str(raw.get("audience_hooks"), limit=3),
        semantic_topics=_safe_list_of_str(raw.get("semantic_topics"), limit=8),
        voice_drift_score=_safe_float_0_1(raw.get("voice_drift_score")),
        voice_notes=_safe_list_of_str(raw.get("voice_notes"), limit=6),
        repurposing_risks=_safe_list_of_str(raw.get("repurposing_risks"), limit=6),
        generation_prompt=prompt_text,
        generation_response=response_text,
        model_id=model_id,
        latency_ms=latency_ms,
        used_fallback=False,
        failure_reason=None,
    )


def build_derivation_augment_prompt(
    *,
    transcript_text: str,
    semantic_segments: list[dict[str, Any]],
    topic_labels: list[str],
    constraint_pack: dict[str, Any] | None = None,
) -> tuple[str, str]:
    system_instruction, user_payload_json, _dynamic_payload_json, _prompt_envelope = _build_derivation_prompt_materials(
        transcript_text=transcript_text,
        semantic_segments=semantic_segments,
        topic_labels=topic_labels,
        constraint_pack=constraint_pack,
    )
    return system_instruction, user_payload_json


def _build_derivation_dynamic_payload(
    *,
    transcript_text: str,
    semantic_segments: list[dict[str, Any]],
    topic_labels: list[str],
    constraint_pack: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "transcript_text": transcript_text[:16000],
        "semantic_segments": semantic_segments[:12],
        "topic_labels": topic_labels[:12],
        "constraint_pack": constraint_pack,
    }


def _build_derivation_user_payload(dynamic_payload: dict[str, Any]) -> dict[str, Any]:
    user_payload = dict(_DERIVATION_STATIC_USER_PAYLOAD)
    user_payload.update(dynamic_payload)
    return user_payload


def _render_derivation_full_prompt(*, system_instruction: str, user_payload_json: str) -> str:
    return (
        "SYSTEM INSTRUCTION:\n"
        f"{system_instruction}\n\n"
        "USER PAYLOAD:\n\n"
        f"{user_payload_json}"
    )


def _build_derivation_prompt_materials(
    *,
    transcript_text: str,
    semantic_segments: list[dict[str, Any]],
    topic_labels: list[str],
    constraint_pack: dict[str, Any] | None = None,
) -> tuple[str, str, str, PromptEnvelope]:
    dynamic_payload = _build_derivation_dynamic_payload(
        transcript_text=transcript_text,
        semantic_segments=semantic_segments,
        topic_labels=topic_labels,
        constraint_pack=constraint_pack,
    )
    dynamic_payload_json = stable_json_dumps(dynamic_payload, ensure_ascii=False)
    user_payload_json = stable_json_dumps(
        _build_derivation_user_payload(dynamic_payload),
        ensure_ascii=False,
    )
    prompt_envelope = PromptEnvelope.from_parts(
        static_prefix_parts=(_DERIVATION_STATIC_PREFIX_TEXT,),
        dynamic_suffix_parts=(dynamic_payload_json,),
    )
    full_prompt = _render_derivation_full_prompt(
        system_instruction=_DERIVATION_SYSTEM_INSTRUCTION,
        user_payload_json=user_payload_json,
    )
    prompt_envelope = replace(
        prompt_envelope,
        full_prompt=full_prompt,
        prompt_fingerprint=fingerprint_text(full_prompt),
    )
    return (
        _DERIVATION_SYSTEM_INSTRUCTION,
        user_payload_json,
        dynamic_payload_json,
        prompt_envelope,
    )


def _derivation_cache_validation_metadata(
    *,
    constraint_pack: dict[str, Any] | None,
    model_id: str,
) -> dict[str, Any]:
    return {
        "constraint_pack_fingerprint": (
            fingerprint_payload(constraint_pack)
            if constraint_pack is not None
            else ""
        ),
        "model_id": model_id,
    }


def _validate_derivation_cache_entry(
    entry: dict[str, Any],
    validation_context: dict[str, Any],
) -> tuple[bool, str]:
    payload = entry.get("response_payload")
    if not isinstance(payload, dict):
        return False, REASON_PAYLOAD_VALIDATION_FAILED
    if payload.get("used_fallback") is True:
        return False, REASON_PAYLOAD_VALIDATION_FAILED

    required_keys = (
        "thematic_summary",
        "audience_hooks",
        "semantic_topics",
        "voice_drift_score",
        "voice_notes",
        "repurposing_risks",
        "generation_prompt",
        "generation_response",
        "model_id",
        "latency_ms",
        "used_fallback",
        "failure_reason",
    )
    for key in required_keys:
        if key not in payload:
            return False, REASON_PAYLOAD_VALIDATION_FAILED

    metadata = entry.get("validation_metadata")
    if not isinstance(metadata, dict):
        return False, REASON_PAYLOAD_VALIDATION_FAILED
    if metadata.get("constraint_pack_fingerprint", "") != validation_context.get("constraint_pack_fingerprint", ""):
        return False, REASON_CONSTRAINT_PACK_MISMATCH
    if metadata.get("model_id", "") != validation_context.get("model_id", ""):
        return False, REASON_MODEL_MISMATCH
    return True, "validated"


def _attach_cache_runtime(
    payload: dict[str, Any],
    *,
    prompt_envelope: PromptEnvelope,
    prefix_status: dict[str, Any],
    cache_status: str,
    cache_entry_id: str = "",
    cache_similarity: float | None = None,
) -> dict[str, Any]:
    result = dict(payload)
    result["cache_status"] = cache_status
    result["prefix_cache_eligible"] = prefix_status.get("eligible", False)
    result["prefix_fingerprint"] = prefix_status.get("prefix_fingerprint", "")
    result["prompt_fingerprint"] = prompt_envelope.prompt_fingerprint
    if cache_entry_id:
        result["cache_entry_id"] = cache_entry_id
    if cache_similarity is not None:
        result["cache_similarity"] = cache_similarity
    return result


def _strip_cache_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in _CACHE_RUNTIME_FIELDS
    }


def _extract_text_from_google_genai_response(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, list):
        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            content_parts = getattr(content, "parts", None)
            if not isinstance(content_parts, list):
                continue
            for part in content_parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    parts.append(part_text.strip())
        if parts:
            return "\n".join(parts)

    return ""


def _call_gemini_google_genai(
    *,
    system_instruction: str,
    user_payload_json: str,
    model_id: str,
) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(f"google-genai import failed: {exc}") from exc

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_id,
        contents=user_payload_json,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=1200,
            response_mime_type="application/json",
        ),
    )
    text = _extract_text_from_google_genai_response(response)
    if not text:
        raise RuntimeError("Gemini returned empty response text")
    return text


def gemini_enhance_derivation(
    *,
    transcript_text: str,
    semantic_segments: list[dict[str, Any]],
    topic_labels: list[str],
    constraint_pack: dict[str, Any] | None = None,
    model_id: str = DEFAULT_MODEL,
    source_artifact_id: str | None = None,
) -> dict[str, Any]:
    system_instruction, user_payload_json, _dynamic_payload_json, prompt_envelope = _build_derivation_prompt_materials(
        transcript_text=transcript_text,
        semantic_segments=semantic_segments,
        topic_labels=topic_labels,
        constraint_pack=constraint_pack,
    )
    full_prompt = prompt_envelope.full_prompt
    cache = GovernedInferenceCache(repo_root=REPO_ROOT)
    cache_context = InferenceRequestContext(
        workflow_id="source_video_derivation_augment",
        workflow_mode="read_only",
        artifact_id=source_artifact_id or "",
        model_id=model_id,
        operation="signal_agent.media.derivation_augment",
    )
    prefix_status = cache.assess_prefix_cache(
        context=cache_context,
        envelope=prompt_envelope,
    )
    validation_metadata = _derivation_cache_validation_metadata(
        constraint_pack=constraint_pack,
        model_id=model_id,
    )
    cached_payload, cache_meta = cache.lookup_semantic_reuse(
        context=cache_context,
        envelope=prompt_envelope,
        normalized_query=user_payload_json,
        validator_id=_DERIVATION_VALIDATOR_ID,
        validator=_validate_derivation_cache_entry,
        validation_context=validation_metadata,
    )
    if cached_payload is not None:
        cached_payload["generation_prompt"] = full_prompt
        cached_payload["latency_ms"] = 0
        return _attach_cache_runtime(
            cached_payload,
            prompt_envelope=prompt_envelope,
            prefix_status=prefix_status,
            cache_status="semantic_hit",
            cache_entry_id=str(cache_meta.get("entry_id") or ""),
            cache_similarity=(
                float(cache_meta["similarity"])
                if cache_meta.get("similarity") is not None
                else None
            ),
        )

    started = time.perf_counter()
    try:
        response_text = _call_gemini_google_genai(
            system_instruction=system_instruction,
            user_payload_json=user_payload_json,
            model_id=model_id,
        )
        parsed = json.loads(response_text)
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = _normalize_response(
            parsed,
            prompt_text=full_prompt,
            response_text=response_text,
            model_id=model_id,
            latency_ms=latency_ms,
        ).to_dict()
        cache.write_semantic_entry(
            context=cache_context,
            envelope=prompt_envelope,
            normalized_query=user_payload_json,
            response_payload=_strip_cache_runtime(result),
            validator_id=_DERIVATION_VALIDATOR_ID,
            validation_metadata=validation_metadata,
        )
        return _attach_cache_runtime(
            result,
            prompt_envelope=prompt_envelope,
            prefix_status=prefix_status,
            cache_status=str(cache_meta.get("status", "miss")),
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return _attach_cache_runtime(
            _fallback_result(
                prompt_text=full_prompt,
                model_id=model_id,
                failure_reason=str(exc),
                latency_ms=latency_ms,
            ).to_dict(),
            prompt_envelope=prompt_envelope,
            prefix_status=prefix_status,
            cache_status=str(cache_meta.get("status", "miss")),
        )


def prompt_hash(prompt_text: str) -> str:
    return sha256(prompt_text.encode("utf-8")).hexdigest()
