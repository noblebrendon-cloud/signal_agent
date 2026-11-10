"""Evidence-linked campaign proposals and provisional production handoffs."""
from .core import CampaignValidationError, evaluate_campaign, load_principles, validate_campaign
from .service import CampaignNotReadyError, build_handoff, write_handoff

__all__ = [
    "CampaignValidationError", "CampaignNotReadyError", "evaluate_campaign",
    "load_principles", "validate_campaign", "build_handoff", "write_handoff",
]
