import json
from unittest import mock
import pytest

from signal_agent.media.derivation_augment import (
    gemini_enhance_derivation,
    build_derivation_augment_prompt,
)


def test_build_derivation_augment_prompt():
    system, user_json = build_derivation_augment_prompt(
        transcript_text="hello world",
        semantic_segments=[{"text": "segment 1"}],
        topic_labels=["topic 1"],
        constraint_pack={"rule": "keep concise"},
    )
    assert "You are a semantic derivation augmentation engine" in system
    payload = json.loads(user_json)
    assert payload["transcript_text"] == "hello world"
    assert payload["topic_labels"] == ["topic 1"]
    assert "output_schema" in payload


def test_gemini_enhance_derivation_fallback_on_import_error():
    # google.genai is not installed/mockable, this will hit ImportError
    # and gracefully fall back
    with mock.patch("signal_agent.media.derivation_augment._call_gemini_google_genai") as mock_call:
        mock_call.side_effect = RuntimeError("google-genai import failed")
        
        result = gemini_enhance_derivation(
            transcript_text="test",
            semantic_segments=[],
            topic_labels=[],
        )
        
        assert result["used_fallback"] is True
        assert "google-genai import failed" in result["failure_reason"]
        assert result["thematic_summary"] == ""
        assert result["semantic_topics"] == []


def test_gemini_enhance_derivation_fallback_on_invalid_json():
    with mock.patch("signal_agent.media.derivation_augment._call_gemini_google_genai") as mock_call:
        mock_call.return_value = "this is not json"
        
        result = gemini_enhance_derivation(
            transcript_text="test",
            semantic_segments=[],
            topic_labels=[],
        )
        
        assert result["used_fallback"] is True
        assert "Expecting value" in result["failure_reason"]
        assert result["thematic_summary"] == ""


def test_gemini_enhance_derivation_success_json():
    with mock.patch("signal_agent.media.derivation_augment._call_gemini_google_genai") as mock_call:
        mock_call.return_value = json.dumps({
            "thematic_summary": "This is a great specific theme.",
            "audience_hooks": ["Hook 1", "Hook 2"],
            "semantic_topics": ["leadership", "innovation"],
            "voice_drift_score": 0.42,
            "voice_notes": ["Keep it punchy"],
            "repurposing_risks": []
        })
        
        result = gemini_enhance_derivation(
            transcript_text="test",
            semantic_segments=[],
            topic_labels=[],
        )
        
        assert result["used_fallback"] is False
        assert result["failure_reason"] is None
        assert result["thematic_summary"] == "This is a great specific theme."
        assert result["audience_hooks"] == ["Hook 1", "Hook 2"]
        assert result["semantic_topics"] == ["leadership", "innovation"]
        assert result["voice_drift_score"] == 0.42


def test_fallback_on_missing_api_key():
    with mock.patch("signal_agent.media.derivation_augment._call_gemini_google_genai") as mock_call:
        mock_call.side_effect = RuntimeError("GEMINI_API_KEY is not set")

        result = gemini_enhance_derivation(
            transcript_text="real transcript content here",
            semantic_segments=[{"text": "segment"}],
            topic_labels=["topic"],
        )

        assert result["used_fallback"] is True
        assert "GEMINI_API_KEY" in result["failure_reason"]
        assert result["thematic_summary"] == ""
        assert result["audience_hooks"] == []
        assert result["semantic_topics"] == []


def test_fallback_on_timeout():
    with mock.patch("signal_agent.media.derivation_augment._call_gemini_google_genai") as mock_call:
        mock_call.side_effect = TimeoutError("Gemini request timed out after 20s")

        result = gemini_enhance_derivation(
            transcript_text="real transcript content here",
            semantic_segments=[{"text": "segment"}],
            topic_labels=["topic"],
        )

        assert result["used_fallback"] is True
        assert "timed out" in result["failure_reason"]
        assert result["thematic_summary"] == ""
        assert result["latency_ms"] >= 0


def test_fallback_on_malformed_json():
    with mock.patch("signal_agent.media.derivation_augment._call_gemini_google_genai") as mock_call:
        mock_call.return_value = "{ broken json here"

        result = gemini_enhance_derivation(
            transcript_text="real transcript content here",
            semantic_segments=[{"text": "segment"}],
            topic_labels=["topic"],
        )

        assert result["used_fallback"] is True
        assert result["failure_reason"] is not None
        assert result["thematic_summary"] == ""
        assert result["audience_hooks"] == []
