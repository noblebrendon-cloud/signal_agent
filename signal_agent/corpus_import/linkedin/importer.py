from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit

from signal_agent.corpus_import.hashing import canonical_json, sha256_canonical_json, sha256_file
from signal_agent.corpus_import.preservation import preserve_source_file
from signal_agent.corpus_import.receipts import seal_receipt, utc_now_iso
from signal_agent.transport.schemas import derive_id

from .key_verifier import KeyContext


RELATIONSHIP_SCHEMA_VERSION = "signal_agent.relationship_record.v1"
MATCH_REPORT_SCHEMA_VERSION = "signal_agent.unresolved_relationship_matches.v1"
SOURCE_RECEIPT_SCHEMA_VERSION = "signal_agent.linkedin_source_receipt.v1"
SOURCE_TYPE = "linkedin_connections_csv"
PRESERVED_FILENAME = "Connections.csv"
HASH_RECORD_FILENAME = "Connections.csv.sha256.txt"
PRESERVED_RELATIVE_PATH = "00_original/Connections.csv"
HASH_RELATIVE_PATH = "00_original/Connections.csv.sha256.txt"
SOURCE_RECEIPT_RELATIVE_PATH = "05_receipts/source_receipt.json"

_REQUIRED_HEADERS = {
    "first_name",
    "last_name",
    "url",
    "email_address",
    "company",
    "position",
    "connected_on",
}
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LinkedInImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class LinkedInImportPlan:
    source_path: Path
    source_sha256: str
    source_size_bytes: int
    source_stat: Any
    source_receipt: dict[str, Any]
    records: tuple[dict[str, Any], ...]
    unresolved_matches: dict[str, Any]
    header_line_start: int
    header_line_end: int
    preamble_row_count: int
    blank_row_count: int


def _header_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def _clean(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _canonical_email(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return normalized if _EMAIL_PATTERN.fullmatch(normalized) else None


def _canonical_linkedin_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    if host != "linkedin.com":
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2 or segments[0].casefold() != "in":
        return None
    slug = unicodedata.normalize("NFKC", unquote(segments[1])).strip().casefold()
    if not slug:
        return None
    return f"https://linkedin.com/in/{quote(slug, safe='-._~')}"


def _connected_date(value: str) -> tuple[str | None, str]:
    normalized = value.strip()
    if not normalized:
        return None, "missing"
    for pattern in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(normalized, pattern).date().isoformat(), "parsed"
        except ValueError:
            continue
    return None, "unparsed"


def _identifier_records(
    *,
    email: str,
    profile_url: str,
    key_context: KeyContext,
    issues: list[str],
) -> list[dict[str, Any]]:
    identifiers: list[dict[str, Any]] = []
    if email:
        canonical_email = _canonical_email(email)
        if canonical_email is None:
            issues.append("invalid_email")
        else:
            token = hmac.new(
                key_context.key_bytes,
                canonical_email.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            identifiers.append(
                {
                    "kind": "email_hmac",
                    "value": f"hmac-sha256:{token}",
                    "key_id": key_context.key_id,
                    "algorithm": key_context.algorithm,
                    "version": key_context.token_version,
                    "personal_data": True,
                    "export_policy": "restricted_local_only",
                }
            )
    if profile_url:
        canonical_url = _canonical_linkedin_url(profile_url)
        if canonical_url is None:
            issues.append("invalid_linkedin_profile_url")
        else:
            identifiers.append(
                {
                    "kind": "linkedin_profile_url",
                    "canonical_value": canonical_url,
                    "value_sha256": "sha256:"
                    + hashlib.sha256(canonical_url.encode("utf-8")).hexdigest(),
                    "personal_data": True,
                    "export_policy": "restricted_local_only",
                }
            )
    return identifiers


def _build_record(
    *,
    raw_row: dict[str, str],
    source_sha256: str,
    receipt_id: str,
    record_number: int,
    line_start: int,
    line_end: int,
    key_context: KeyContext,
) -> dict[str, Any]:
    raw_row_sha256 = "sha256:" + sha256_canonical_json(raw_row)
    evidence_ref = (
        f"linkedin-source:sha256:{source_sha256}:record:{record_number}:"
        f"row-sha256:{raw_row_sha256.removeprefix('sha256:')}"
    )
    record_id = derive_id(
        "rel",
        SOURCE_TYPE,
        source_sha256,
        record_number,
        raw_row_sha256,
        length=20,
    )
    first = _clean(raw_row.get("first_name"))
    middle = _clean(raw_row.get("middle_name"))
    last = _clean(raw_row.get("last_name"))
    company = _clean(raw_row.get("company"))
    position = _clean(raw_row.get("position"))
    connected_raw = _clean(raw_row.get("connected_on"))
    connected_date, date_state = _connected_date(connected_raw)
    issues: list[str] = []
    identifiers = _identifier_records(
        email=_clean(raw_row.get("email_address")),
        profile_url=_clean(raw_row.get("url")),
        key_context=key_context,
        issues=issues,
    )
    if not first and not last:
        issues.append("name_missing")
    if not company:
        issues.append("company_missing")
    if not position:
        issues.append("position_missing")
    if date_state == "unparsed":
        issues.append("connected_on_unparsed")
    identifier_kinds = [item["kind"] for item in identifiers]
    field_presence = {
        field: bool(_clean(raw_row.get(field)))
        for field in (
            "first_name",
            "middle_name",
            "last_name",
            "url",
            "email_address",
            "company",
            "position",
            "connected_on",
        )
    }
    return {
        "schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "relationship_record_id": record_id,
        "source_provenance": {
            "source_type": SOURCE_TYPE,
            "source_sha256": f"sha256:{source_sha256}",
            "source_receipt_id": receipt_id,
            "record_number": record_number,
            "line_start": line_start,
            "line_end": line_end,
            "raw_row_sha256": raw_row_sha256,
            "evidence_ref": evidence_ref,
        },
        "person": {
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "display_name": " ".join(value for value in (first, middle, last) if value),
        },
        "professional_context": {"company": company, "position": position},
        "relationship": {
            "platform": "linkedin",
            "kind": "connection",
            "connected_on_raw": connected_raw,
            "connected_on_date": connected_date,
            "connected_on_state": date_state,
        },
        "identifiers": identifiers,
        "deterministic_classification": {
            "source_platform": "linkedin",
            "source_format": SOURCE_TYPE,
            "relationship_kind": "connection",
            "field_presence": field_presence,
            "identifier_kinds_present": identifier_kinds,
            "company_state": "present" if company else "missing",
            "position_state": "present" if position else "missing",
            "connected_on_state": date_state,
        },
        "data_quality_issues": sorted(set(issues)),
        "privacy": {
            "contains_personal_data": True,
            "clear_email_retained": False,
            "clear_linkedin_url_local_only": "linkedin_profile_url" in identifier_kinds,
            "public_export_allowed": False,
        },
    }


def _candidate_report(
    records: list[dict[str, Any]],
    source_sha256: str,
    *,
    blank_row_count: int,
    preamble_row_count: int,
    header_line_start: int,
    header_line_end: int,
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    values: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        values[("repeated_source_row", record["source_provenance"]["raw_row_sha256"])].append(record)
        for identifier in record["identifiers"]:
            if identifier["kind"] == "email_hmac":
                fingerprint = f"{identifier['key_id']}:{identifier['value']}"
                values[("email_hmac_exact", fingerprint)].append(record)
            elif identifier["kind"] == "linkedin_profile_url":
                values[("linkedin_profile_url_exact", identifier["value_sha256"])].append(record)

    for (basis, fingerprint), matched in sorted(values.items()):
        unique = {record["relationship_record_id"]: record for record in matched}
        if len(unique) < 2:
            continue
        record_ids = sorted(unique)
        groups.append(
            {
                "candidate_group_id": derive_id(
                    "rcg", source_sha256, basis, fingerprint, record_ids, length=20
                ),
                "state": "review_required",
                "match_strength": "exact",
                "match_basis": basis,
                "identifier_fingerprint": fingerprint,
                "personal_data": basis != "repeated_source_row",
                "relationship_record_ids": record_ids,
                "evidence_refs": sorted(
                    unique[record_id]["source_provenance"]["evidence_ref"]
                    for record_id in record_ids
                ),
                "automatic_merge_performed": False,
            }
        )
    groups.sort(key=lambda item: (item["match_basis"], item["candidate_group_id"]))
    involved = sorted(
        {
            record_id
            for group in groups
            for record_id in group["relationship_record_ids"]
        }
    )
    return {
        "schema_version": MATCH_REPORT_SCHEMA_VERSION,
        "state": "review_required",
        "source_sha256": f"sha256:{source_sha256}",
        "relationship_record_count": len(records),
        "source_parse_summary": {
            "nonblank_data_row_count": len(records),
            "blank_row_count": blank_row_count,
            "preamble_row_count": preamble_row_count,
            "header_line_start": header_line_start,
            "header_line_end": header_line_end,
        },
        "candidate_group_count": len(groups),
        "records_in_candidate_groups": involved,
        "unresolved_record_ids": sorted(record["relationship_record_id"] for record in records),
        "candidate_groups": groups,
        "excluded_match_methods": [
            "fuzzy_matching",
            "name_similarity",
            "organization_similarity",
            "position_similarity",
        ],
        "automatic_merge_performed": False,
        "canonical_identity_selected": False,
    }


def _source_receipt(
    *,
    source_path: Path,
    source_sha256: str,
    source_size: int,
    source_mtime_ns: int,
    created_at: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": SOURCE_RECEIPT_SCHEMA_VERSION,
        "receipt_id": f"linkedin-source.{source_sha256[:16]}",
        "created_at": created_at,
        "preservation_timestamp": created_at,
        "status": "completed",
        "operation": "preserve_linkedin_connections_source",
        "source": {
            "source_type": SOURCE_TYPE,
            "observed_name": source_path.name,
            "observed_path": str(source_path),
            "sha256": f"sha256:{source_sha256}",
            "size_bytes": source_size,
            "observed_mtime_ns": source_mtime_ns,
            "preserved_path": PRESERVED_RELATIVE_PATH,
            "preserved_sha256": f"sha256:{source_sha256}",
            "original_preserved": True,
            "hash_verified": True,
            "byte_for_byte_equal": True,
            "source_stat_stable": True,
            "source_stat_stability_fields": ["size_bytes", "mtime_ns"],
        },
        "overwrite_policy": "refuse",
        "authorizations": {
            "authorization_scope": "none",
            "contact_allowed": False,
            "external_action_allowed": False,
            "message_allowed": False,
            "network_allowed": False,
            "publication_allowed": False,
            "routing_allowed": False,
        },
    }
    return seal_receipt(receipt)


def build_linkedin_import_plan(
    source: str | Path,
    *,
    key_context: KeyContext,
    clock: Callable[[], str] = utc_now_iso,
) -> LinkedInImportPlan:
    try:
        source_path = Path(source).expanduser().resolve(strict=True)
    except OSError as exc:
        raise LinkedInImportError("linkedin_source_unreadable") from exc
    if not source_path.is_file():
        raise LinkedInImportError("linkedin_source_not_regular_file")
    source_stat = source_path.stat()
    raw_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LinkedInImportError("linkedin_csv_utf8_required") from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    header: list[str] | None = None
    header_start = 0
    header_end = 0
    previous_end = 0
    preamble_count = 0
    parsed_rows: list[tuple[dict[str, str], int, int]] = []
    blank_count = 0
    for row in reader:
        line_start = previous_end + 1
        line_end = reader.line_num
        previous_end = line_end
        keys = [_header_key(value) for value in row]
        if header is None:
            if not any(_clean(value) for value in row):
                blank_count += 1
                continue
            if _REQUIRED_HEADERS.issubset(set(keys)):
                if len(set(keys)) != len(keys):
                    raise LinkedInImportError("linkedin_csv_duplicate_headers")
                header = keys
                header_start = line_start
                header_end = line_end
            else:
                preamble_count += 1
            continue
        if not any(_clean(value) for value in row):
            blank_count += 1
            continue
        if len(row) > len(header):
            raise LinkedInImportError("linkedin_csv_row_width_exceeds_header")
        padded = [*row, *([""] * (len(header) - len(row)))]
        parsed_rows.append((dict(zip(header, padded)), line_start, line_end))

    if header is None:
        raise LinkedInImportError("linkedin_csv_required_header_missing")
    receipt_id = f"linkedin-source.{source_sha256[:16]}"
    records = [
        _build_record(
            raw_row=raw_row,
            source_sha256=source_sha256,
            receipt_id=receipt_id,
            record_number=index,
            line_start=line_start,
            line_end=line_end,
            key_context=key_context,
        )
        for index, (raw_row, line_start, line_end) in enumerate(parsed_rows, start=1)
    ]
    receipt = _source_receipt(
        source_path=source_path,
        source_sha256=source_sha256,
        source_size=len(raw_bytes),
        source_mtime_ns=source_stat.st_mtime_ns,
        created_at=clock(),
    )
    return LinkedInImportPlan(
        source_path=source_path,
        source_sha256=source_sha256,
        source_size_bytes=len(raw_bytes),
        source_stat=source_stat,
        source_receipt=receipt,
        records=tuple(records),
        unresolved_matches=_candidate_report(
            records,
            source_sha256,
            blank_row_count=blank_count,
            preamble_row_count=preamble_count,
            header_line_start=header_start,
            header_line_end=header_end,
        ),
        header_line_start=header_start,
        header_line_end=header_end,
        preamble_row_count=preamble_count,
        blank_row_count=blank_count,
    )


def preserve_linkedin_source(plan: LinkedInImportPlan, run_root: str | Path) -> None:
    result = preserve_source_file(
        plan.source_path,
        Path(run_root),
        expected_sha256=plan.source_sha256,
        expected_stat=plan.source_stat,
        preserved_filename=PRESERVED_FILENAME,
        hash_record_filename=HASH_RECORD_FILENAME,
    )
    if result.preserved_sha256 != plan.source_sha256:
        raise LinkedInImportError("linkedin_preserved_source_hash_mismatch")
