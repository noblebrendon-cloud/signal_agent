"""
Shared publisher primitives for Letters of Light release targets.

Publisher modules are intentionally platform-specific. They are called only
after a release has crossed the approval/export boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


VALID_PRIVACY_STATUSES = {"private", "unlisted", "public"}


class PublisherError(RuntimeError):
    """Base error for release publisher failures."""


class MissingReleaseError(PublisherError):
    """Raised when a release record does not exist."""


class ReleaseNotApprovedError(PublisherError):
    """Raised when a publisher is invoked before human approval."""


class VideoMissingError(PublisherError):
    """Raised when the publisher cannot find a non-empty video asset."""


class MissingCredentialsError(PublisherError):
    """Raised when local OAuth credentials are missing or unusable."""


class DependencyMissingError(PublisherError):
    """Raised when optional platform SDK dependencies are not installed."""


def validate_privacy_status(value: str) -> str:
    status = (value or "unlisted").strip().lower()
    if status not in VALID_PRIVACY_STATUSES:
        allowed = ", ".join(sorted(VALID_PRIVACY_STATUSES))
        raise PublisherError(f"privacy_status must be one of: {allowed}")
    return status


@dataclass(frozen=True)
class PublishResult:
    platform: str
    platform_id: str
    url: str
    status: str = "published"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "platform_id": self.platform_id,
            "url": self.url,
            "status": self.status,
            "metadata": dict(self.metadata),
        }
