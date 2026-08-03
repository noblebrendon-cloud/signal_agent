from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signal_agent.evidence_sources.canonical import sha256_file


RELATED_WORK_SCHEMA_VERSION = "signal_agent.relationship_related_work.v1"
SEARCH_SCOPE = "content_library_teaching_atoms_only"
_EVENT_ID = re.compile(r"\bEVT-[A-Za-z0-9._-]+\b")


class ContentLibraryContextError(RuntimeError):
    pass


def _normalized(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def contextualize_teaching_atoms(
    topic_cluster: dict[str, Any],
    *,
    content_library_root: str | Path,
) -> dict[str, Any]:
    root = Path(content_library_root).resolve(strict=True)
    atom_dir = root / "teaching_atoms"
    if not atom_dir.is_dir():
        raise ContentLibraryContextError("teaching_atom_directory_missing")

    matched_terms = sorted(
        {item["matched_term"] for item in topic_cluster.get("deterministic_matches", [])}
    )
    query_tokens = sorted(
        {
            token
            for phrase in matched_terms
            for token in re.findall(r"[a-z0-9]+", _normalized(phrase))
            if len(token) >= 4
        }
    )
    candidates: list[dict[str, Any]] = []
    for path in sorted(atom_dir.glob("ATOM-*.md"), key=lambda item: item.name.casefold()):
        try:
            payload = path.read_bytes()
            text = payload.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContentLibraryContextError("teaching_atom_unreadable") from exc
        haystack = _normalized(text)
        phrase_hits = [term for term in matched_terms if term in haystack]
        token_hits = [term for term in query_tokens if re.search(rf"\b{re.escape(term)}\b", haystack)]
        score = (3 * len(phrase_hits)) + len(token_hits)
        if score == 0:
            continue
        atom_id = path.stem
        digest = sha256_file(path)
        confidence = "high" if phrase_hits else ("moderate" if score >= 2 else "low")
        candidates.append(
            {
                "atom_id": atom_id,
                "atom_path": f"teaching_atoms/{path.name}",
                "originating_event_ids": sorted(set(_EVENT_ID.findall(text))),
                "matched_terms": phrase_hits,
                "matched_lexical_tokens": token_hits,
                "score": score,
                "score_explanation": "three_points_per_exact_phrase_plus_one_per_distinct_query_token",
                "confidence_state": confidence,
                "file_sha256": f"sha256:{digest}",
                "evidence_refs": [f"content-library:{atom_id}:sha256:{digest}"],
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["atom_id"]))
    selected = candidates[:3]
    cluster = topic_cluster.get("inferred_cluster") or {}
    return {
        "schema_version": RELATED_WORK_SCHEMA_VERSION,
        "search_scope": SEARCH_SCOPE,
        "scope_complete": False,
        "result_characterization": "non_exhaustive_related_work_context",
        "query_cluster_id": cluster.get("cluster_id"),
        "query_confidence_state": cluster.get("confidence_state", "insufficient"),
        "confidence_state": selected[0]["confidence_state"] if selected else "insufficient",
        "evidence_refs": sorted(
            {
                evidence
                for result in selected
                for evidence in result["evidence_refs"]
            }
        ),
        "results": selected,
        "adapter_policy": {
            "read_only": True,
            "maximum_results": 3,
            "searched_glob": "teaching_atoms/ATOM-*.md",
            "library_mutation_performed": False,
        },
    }


@dataclass(frozen=True)
class TeachingAtomContextResolver:
    """Read-only relationship context resolver scoped to teaching atoms."""

    content_library_root: Path

    def resolve(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return contextualize_teaching_atoms(
            analysis,
            content_library_root=self.content_library_root,
        )
