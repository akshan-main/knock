"""Typed contracts exchanged by agents, objects, and the MANNERS kernel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
import re
from typing import Any


SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MODALITIES = frozenset({"glow", "haptic", "speech"})
PRIVACY_LEVELS = frozenset({"private", "personal", "public"})
CONTEXT_FLAGS = frozenset({"at_doorway", "hands_full", "partner_asleep"})


def _require_safe_id(label: str, value: str) -> None:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase opaque identifier")


def _require_unit_interval(label: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be finite and between 0 and 1")


class DecisionKind(str, Enum):
    ACT = "act"
    SILENCE = "silence"


class OutcomeKind(str, Enum):
    ACT = "act"
    DEFER = "defer"
    DROP = "drop"


@dataclass(frozen=True)
class Context:
    """Human and social context shared across otherwise local agents."""

    principal_id: str = "person"
    at_doorway: bool = True
    hands_full: bool = True
    partner_asleep: bool = True
    attention_budget: int = 1

    def __post_init__(self) -> None:
        _require_safe_id("principal_id", self.principal_id)
        if self.attention_budget not in (0, 1) or isinstance(self.attention_budget, bool):
            raise ValueError("attention_budget is a per-tick gate and must be 0 or 1")

    def flag(self, name: str) -> bool:
        return bool(getattr(self, name, False))

    def as_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "at_doorway": self.at_doorway,
            "hands_full": self.hands_full,
            "partner_asleep": self.partner_asleep,
            "attention_budget": self.attention_budget,
        }


@dataclass(frozen=True)
class Device:
    """A physical object's output affordances and social exposure."""

    id: str
    name: str
    zone: str
    modalities: tuple[str, ...]
    audience: str
    interruption_cost: float
    principal_id: str = "person"
    online: bool = True

    def __post_init__(self) -> None:
        _require_safe_id("device id", self.id)
        _require_safe_id("principal_id", self.principal_id)
        if not self.modalities or any(item not in MODALITIES for item in self.modalities):
            raise ValueError("device modalities must be supported and non-empty")
        if self.audience not in PRIVACY_LEVELS:
            raise ValueError("device audience must be private, personal, or public")
        _require_unit_interval("interruption_cost", self.interruption_cost)


@dataclass(frozen=True)
class Proposal:
    """A request for attention. Agents propose; they never actuate directly."""

    id: str
    agent_id: str
    title: str = field(repr=False)
    cue: str = field(repr=False)
    urgency: float
    relevance: float
    allowed_modalities: tuple[str, ...]
    privacy: str = "personal"
    required_context: tuple[str, ...] = ()
    principal_id: str = "person"
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_safe_id("proposal id", self.id)
        _require_safe_id("agent_id", self.agent_id)
        _require_safe_id("principal_id", self.principal_id)
        _require_unit_interval("urgency", self.urgency)
        _require_unit_interval("relevance", self.relevance)
        if not self.allowed_modalities or any(
            item not in MODALITIES for item in self.allowed_modalities
        ):
            raise ValueError("allowed_modalities must be supported and non-empty")
        if self.privacy not in PRIVACY_LEVELS:
            raise ValueError("privacy must be private, personal, or public")
        if any(flag not in CONTEXT_FLAGS for flag in self.required_context):
            raise ValueError("required_context contains an unknown policy flag")
        if self.expires_at is not None and self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")


@dataclass(frozen=True)
class Route:
    proposal_id: str
    device_id: str
    modality: str
    score: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class RouteRejection:
    proposal_id: str
    device_id: str
    modality: str
    reason_code: str


@dataclass(frozen=True)
class Outcome:
    proposal_id: str
    kind: OutcomeKind
    reason_code: str
    reason: str
    best_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind.value,
            "reason_code": self.reason_code,
            "best_score": self.best_score,
        }


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str
    score: float = 0.0
    proposal_id: str | None = None
    device_id: str | None = None
    modality: str | None = None
    cue: str | None = None
    outcomes: tuple[Outcome, ...] = ()
    rejected_routes: tuple[RouteRejection, ...] = ()
    score_breakdown: dict[str, float] | None = None

    def trace(self) -> dict[str, Any]:
        """Return a content-free decision trace safe to persist."""

        return {
            "kind": self.kind.value,
            "score": self.score,
            "proposal_id": self.proposal_id,
            "device_id": self.device_id,
            "modality": self.modality,
            "outcomes": [outcome.as_dict() for outcome in self.outcomes],
            "rejected_routes": [
                {
                    "proposal_id": route.proposal_id,
                    "device_id": route.device_id,
                    "modality": route.modality,
                    "reason_code": route.reason_code,
                }
                for route in self.rejected_routes
            ],
            "score_breakdown": self.score_breakdown,
        }
