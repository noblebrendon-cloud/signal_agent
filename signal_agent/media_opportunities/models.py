from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from signal_agent.transport.schemas import derive_id, stable_digest


SCHEMA_VERSION = "media_opportunity_v1"

OPPORTUNITY_TYPES = (
    "podcast_or_interview",
    "guest_essay",
    "review",
    "local_reporting",
    "organizational_feature",
    "academic_or_writer_citation",
    "speaking_invitation",
    "other",
)

ACTIVE_STATES = (
    "captured",
    "qualified",
    "response_ready",
    "awaiting_outcome",
    "published_candidate",
    "independently_verified",
    "approved_for_public_reference",
)

TERMINAL_STATES = (
    "declined",
    "private",
    "self_published",
    "insufficient_independence",
    "unverified",
    "archived",
)

ALL_STATES = (*ACTIVE_STATES, *TERMINAL_STATES)

RELATIONSHIP_CLASSIFICATIONS = ("independent", "affiliated", "self", "unknown")
VISIBILITIES = ("private", "embargoed", "public")

PUBLIC_REFERENCE_COVERAGE_TYPES = (
    "podcast_or_interview",
    "article",
    "profile",
    "review",
    "local_reporting",
    "organizational_feature",
    "academic_or_writer_citation",
    "guest_essay",
    "speaking_coverage",
    "other",
)

NON_INDEPENDENT_COVERAGE_TYPES = (
    "self_published",
    "repost",
    "directory",
    "paid_placement",
    "announcement",
)

PUBLIC_EXPORT_KEYS = (
    "title",
    "outlet",
    "author",
    "date",
    "type",
    "public_url",
    "short_neutral_description",
    "verification_status",
    "approved_timestamp",
)

OWNED_PUBLIC_DOMAINS = {
    "brendonrcoleman.com",
    "www.brendonrcoleman.com",
}

OWNED_PROFILE_URL_PREFIXES = (
    "https://github.com/noblebrendon-cloud",
    "https://www.facebook.com/brendon.coleman.524",
    "https://www.instagram.com/thewaywordgent",
    "https://www.threads.com/@thewaywordgent",
    "https://x.com/BrendonRColeman",
    "https://substack.com/@bcoleman93",
    "https://www.youtube.com/channel/UCZacy_61PeA3g2CDZWbwCBQ",
    "https://music.youtube.com/@BrendonRColeman",
)

ALLOWED_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"captured"},
    "captured": {"qualified", "declined", "private", "archived"},
    "qualified": {"response_ready", "declined", "private", "archived"},
    "response_ready": {"awaiting_outcome", "declined", "private", "archived"},
    "awaiting_outcome": {
        "published_candidate",
        "self_published",
        "insufficient_independence",
        "unverified",
        "private",
        "archived",
    },
    "published_candidate": {
        "independently_verified",
        "self_published",
        "insufficient_independence",
        "unverified",
        "private",
        "archived",
    },
    "independently_verified": {"approved_for_public_reference", "private", "archived"},
    "approved_for_public_reference": {"archived"},
    "declined": set(),
    "private": set(),
    "self_published": set(),
    "insufficient_independence": set(),
    "unverified": set(),
    "archived": set(),
}

SAFETY_FLAGS = {
    "external_action_allowed": False,
    "network_allowed": False,
    "irreversible_action_allowed": False,
    "live_action_allowed": False,
}

DEFAULT_IDENTITY_PACKET: dict[str, Any] = {
    "schema_version": "canonical_identity_packet_v1",
    "canonical_site": "https://brendonrcoleman.com/",
    "about_page": "https://brendonrcoleman.com/about/",
    "public_work_links": {
        "Letters": "https://brendonrcoleman.com/letters-of-light/",
        "Essays": "https://brendonrcoleman.com/essays/",
        "Books": "https://brendonrcoleman.com/books/",
        "Speaking": "https://brendonrcoleman.com/speaking/",
        "Services": "https://brendonrcoleman.com/services/",
        "Projects": "https://brendonrcoleman.com/mini-sites/",
        "Whitepapers": "https://brendonrcoleman.com/whitepapers/",
    },
    "verified_public_profile_urls": [
        "https://github.com/noblebrendon-cloud",
        "https://www.facebook.com/brendon.coleman.524",
        "https://www.instagram.com/thewaywordgent/",
        "https://www.threads.com/@thewaywordgent",
        "https://x.com/BrendonRColeman",
        "https://substack.com/@bcoleman93",
        "https://www.youtube.com/channel/UCZacy_61PeA3g2CDZWbwCBQ",
        "https://music.youtube.com/@BrendonRColeman",
    ],
    "github_profile": "https://github.com/noblebrendon-cloud",
    "portrait_asset_reference": "https://brendonrcoleman.com/assets/images/brendon-r-coleman-portrait.jpg",
    "concise_grounded_bio": (
        "Brendon R. Coleman is a writer, speaker, and practical systems worker whose public home "
        "connects Letters of Light, essays, books in development, Scripture-rooted speaking topics, "
        "services, projects, and operational artifacts."
    ),
    "longer_grounded_bio": (
        "Brendon R. Coleman publishes from BrendonRColeman.com. His public work is organized around "
        "Letters of Light, public essays, book projects in development, Scripture-rooted speaking paths, "
        "practical service routes, projects, and whitepaper-style operational notes on deterministic "
        "publishing, runtime governance, and service protocols. The public framing is intentionally "
        "conservative: books are described as in development, speaking routes point to current topics and "
        "invitation paths, and service pages avoid unsupported claims about clients, credentials, or endorsements."
    ),
    "prohibited_claims": [
        "awards",
        "clients",
        "follower counts",
        "media claims",
        "credentials",
        "endorsements",
        "notable language",
    ],
}


@dataclass(frozen=True)
class OpportunityRecord:
    opportunity_id: str
    created_at: str
    current_state: str
    opportunity_type: str
    outlet_or_organization: str | None
    contact_or_source_name: str | None
    originating_url_or_source_ref: str | None
    original_request_text: str
    topic_or_subject: str | None
    deadline: str | None
    relationship_classification: str
    visibility: str
    next_action: str | None
    notes: str | None
    artifact_links: Mapping[str, str] = field(default_factory=dict)
    published_url: str | None = None
    verification_evidence: tuple[Mapping[str, Any], ...] = ()
    coverage_metadata: Mapping[str, Any] = field(default_factory=dict)
    source_metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        created_at: str,
        opportunity_type: str,
        original_request_text: str,
        outlet_or_organization: str | None = None,
        contact_or_source_name: str | None = None,
        originating_url_or_source_ref: str | None = None,
        topic_or_subject: str | None = None,
        deadline: str | None = None,
        relationship_classification: str = "unknown",
        visibility: str = "private",
        next_action: str | None = None,
        notes: str | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        source_fingerprint: str | None = None,
    ) -> "OpportunityRecord":
        validate_opportunity_type(opportunity_type)
        validate_relationship(relationship_classification)
        validate_visibility(visibility)
        body = normalize_text(original_request_text)
        if not body:
            raise ValueError("media_opportunity_original_request_text_required")
        material = {
            "created_at": None if source_fingerprint else created_at,
            "opportunity_type": opportunity_type,
            "outlet_or_organization": optional(outlet_or_organization),
            "originating_url_or_source_ref": optional(originating_url_or_source_ref),
            "original_request_hash": text_hash(body),
            "source_fingerprint": optional(source_fingerprint),
            "topic_or_subject": optional(topic_or_subject),
        }
        return cls(
            opportunity_id=derive_id("opp", SCHEMA_VERSION, material, length=20),
            created_at=created_at,
            current_state="captured",
            opportunity_type=opportunity_type,
            outlet_or_organization=optional(outlet_or_organization),
            contact_or_source_name=optional(contact_or_source_name),
            originating_url_or_source_ref=optional(originating_url_or_source_ref),
            original_request_text=body,
            topic_or_subject=optional(topic_or_subject),
            deadline=optional(deadline),
            relationship_classification=relationship_classification,
            visibility=visibility,
            next_action=optional(next_action) or "Review opportunity and decide whether to qualify.",
            notes=optional(notes),
            artifact_links={},
            source_metadata=dict(source_metadata or {}),
        )

    @classmethod
    def from_record(cls, payload: Mapping[str, Any]) -> "OpportunityRecord":
        return cls(
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
            opportunity_id=str(payload["opportunity_id"]),
            created_at=str(payload["created_at"]),
            current_state=str(payload["current_state"]),
            opportunity_type=str(payload["opportunity_type"]),
            outlet_or_organization=optional(payload.get("outlet_or_organization")),
            contact_or_source_name=optional(payload.get("contact_or_source_name")),
            originating_url_or_source_ref=optional(payload.get("originating_url_or_source_ref")),
            original_request_text=str(payload["original_request_text"]),
            topic_or_subject=optional(payload.get("topic_or_subject")),
            deadline=optional(payload.get("deadline")),
            relationship_classification=str(payload.get("relationship_classification") or "unknown"),
            visibility=str(payload.get("visibility") or "private"),
            next_action=optional(payload.get("next_action")),
            notes=optional(payload.get("notes")),
            artifact_links=dict(payload.get("artifact_links") or {}),
            published_url=optional(payload.get("published_url")),
            verification_evidence=tuple(dict(item) for item in (payload.get("verification_evidence") or ())),
            coverage_metadata=dict(payload.get("coverage_metadata") or {}),
            source_metadata=dict(payload.get("source_metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "opportunity_id": self.opportunity_id,
            "created_at": self.created_at,
            "current_state": self.current_state,
            "opportunity_type": self.opportunity_type,
            "outlet_or_organization": self.outlet_or_organization,
            "contact_or_source_name": self.contact_or_source_name,
            "originating_url_or_source_ref": self.originating_url_or_source_ref,
            "original_request_text": self.original_request_text,
            "topic_or_subject": self.topic_or_subject,
            "deadline": self.deadline,
            "relationship_classification": self.relationship_classification,
            "visibility": self.visibility,
            "next_action": self.next_action,
            "notes": self.notes,
            "artifact_links": dict(self.artifact_links),
            "published_url": self.published_url,
            "verification_evidence": [dict(item) for item in self.verification_evidence],
            "coverage_metadata": dict(self.coverage_metadata),
            "source_metadata": dict(self.source_metadata),
        }


def transition_allowed(from_state: str | None, to_state: str) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


def validate_opportunity_type(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in OPPORTUNITY_TYPES:
        raise ValueError(f"media_opportunity_type_invalid:{normalized}")
    return normalized


def validate_state(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in ALL_STATES:
        raise ValueError(f"media_opportunity_state_invalid:{normalized}")
    return normalized


def validate_relationship(value: str) -> str:
    normalized = str(value or "").strip() or "unknown"
    if normalized not in RELATIONSHIP_CLASSIFICATIONS:
        raise ValueError(f"media_opportunity_relationship_invalid:{normalized}")
    return normalized


def validate_visibility(value: str) -> str:
    normalized = str(value or "").strip() or "private"
    if normalized not in VISIBILITIES:
        raise ValueError(f"media_opportunity_visibility_invalid:{normalized}")
    return normalized


def normalized_text_items(values: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in (values or ()) if str(value).strip()}))


def normalize_text(text: object) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def optional(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def text_hash(text: str) -> str:
    return f"sha256:{stable_digest(normalize_text(text))}"


def is_public_http_url(value: str | None) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_owned_public_reference_url(value: str | None) -> bool:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.netloc.lower() in OWNED_PUBLIC_DOMAINS:
        return True
    lowered = normalized.lower()
    return any(lowered.startswith(prefix.lower().rstrip("/")) for prefix in OWNED_PROFILE_URL_PREFIXES)
