"""Deterministic attention arbitration and physical-object routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import (
    Context,
    Decision,
    DecisionKind,
    Device,
    Outcome,
    OutcomeKind,
    Proposal,
    Route,
    RouteRejection,
)


ACTION_THRESHOLD = 0.58

PRIVACY_RANK = {"private": 0, "personal": 1, "public": 2}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def demo_devices() -> tuple[Device, ...]:
    return (
        Device(
            id="door_charm",
            name="Door charm",
            zone="doorway",
            modalities=("glow",),
            audience="personal",
            interruption_cost=0.08,
        ),
        Device(
            id="worn_pin",
            name="Worn pin",
            zone="worn",
            modalities=("haptic",),
            audience="private",
            interruption_cost=0.18,
        ),
        Device(
            id="hall_speaker",
            name="Hall speaker",
            zone="hall",
            modalities=("speech",),
            audience="public",
            interruption_cost=0.65,
        ),
    )


def demo_proposals(now: datetime | None = None) -> tuple[Proposal, ...]:
    created_at = now or utc_now()
    return (
        Proposal(
            id="weather",
            agent_id="weather_agent",
            title="Rain starts in 12 minutes",
            cue="Take the umbrella",
            urgency=0.78,
            relevance=0.92,
            allowed_modalities=("glow", "haptic", "speech"),
            privacy="public",
            required_context=("at_doorway",),
            expires_at=created_at + timedelta(minutes=12),
        ),
        Proposal(
            id="calendar",
            agent_id="calendar_agent",
            title="Design review begins in 25 minutes",
            cue="Design review soon",
            urgency=0.62,
            relevance=0.86,
            allowed_modalities=("haptic", "speech"),
            privacy="personal",
            expires_at=created_at + timedelta(minutes=25),
        ),
        Proposal(
            id="social",
            agent_id="social_agent",
            title="Maya sent three photos",
            cue="New photos from Maya",
            urgency=0.16,
            relevance=0.40,
            allowed_modalities=("glow", "speech"),
            privacy="personal",
            expires_at=created_at + timedelta(hours=2),
        ),
    )


class MannersEngine:
    """The system-call boundary between agent intelligence and human attention."""

    def __init__(self) -> None:
        self._audit: list[dict[str, object]] = []

    @property
    def audit_log(self) -> tuple[dict[str, object], ...]:
        return tuple(self._audit)

    def arbitrate(
        self,
        proposals: Iterable[Proposal],
        devices: Iterable[Device],
        context: Context,
        *,
        now: datetime | None = None,
    ) -> Decision:
        moment = now or utc_now()
        proposal_list = tuple(sorted(proposals, key=lambda item: item.id))
        device_list = tuple(sorted(devices, key=lambda item: item.id))
        self._require_unique_ids(proposal_list, "proposal")
        self._require_unique_ids(device_list, "device")
        rejected_routes: list[RouteRejection] = []
        proposal_routes: dict[str, list[Route]] = {}
        gated: dict[str, tuple[str, str]] = {}

        if context.attention_budget <= 0:
            outcomes = []
            for proposal in proposal_list:
                gate = self._proposal_gate(proposal, context, moment)
                if gate:
                    code, reason = gate
                    outcomes.append(Outcome(proposal.id, OutcomeKind.DROP, code, reason))
                else:
                    outcomes.append(
                        Outcome(
                            proposal.id,
                            OutcomeKind.DEFER,
                            "ATTENTION_BUDGET_CLOSED",
                            "The person's attention budget is closed for this moment.",
                        )
                    )
            return self._finish(
                Decision(
                    kind=DecisionKind.SILENCE,
                    reason="No proposal may spend attention in this moment.",
                    outcomes=tuple(outcomes),
                ),
                context,
            )

        for proposal in proposal_list:
            gate = self._proposal_gate(proposal, context, moment)
            if gate:
                gated[proposal.id] = gate
                continue

            routes: list[Route] = []
            for device in device_list:
                for modality in device.modalities:
                    rejection = self._route_gate(proposal, device, modality, context)
                    if rejection:
                        rejected_routes.append(
                            RouteRejection(proposal.id, device.id, modality, rejection)
                        )
                        continue
                    routes.append(self._score_route(proposal, device, modality, context))
            proposal_routes[proposal.id] = sorted(
                routes,
                key=lambda route: (-route.score, route.device_id, route.modality),
            )

        best_routes = [routes[0] for routes in proposal_routes.values() if routes]
        eligible = [route for route in best_routes if route.score >= ACTION_THRESHOLD]
        winner = min(
            eligible,
            key=lambda route: (
                -route.score,
                self._expiry_for(route.proposal_id, proposal_list),
                route.device_id,
                route.proposal_id,
            ),
            default=None,
        )

        outcomes: list[Outcome] = []
        for proposal in proposal_list:
            if proposal.id in gated:
                code, reason = gated[proposal.id]
                kind = OutcomeKind.DROP if code in {"EXPIRED", "WRONG_PRINCIPAL"} else OutcomeKind.DEFER
                outcomes.append(Outcome(proposal.id, kind, code, reason))
                continue

            routes = proposal_routes.get(proposal.id, [])
            best_score = routes[0].score if routes else 0.0
            if winner and proposal.id == winner.proposal_id:
                outcomes.append(
                    Outcome(
                        proposal.id,
                        OutcomeKind.ACT,
                        "HIGHEST_CONTEXTUAL_VALUE",
                        "This proposal earned the single available attention slot.",
                        best_score,
                    )
                )
            elif best_score < ACTION_THRESHOLD:
                code = "NO_SAFE_ROUTE" if not routes else "BELOW_ACTION_THRESHOLD"
                reason = (
                    "No authorized object can express this safely."
                    if not routes
                    else "The proposal is not valuable enough to interrupt now."
                )
                outcomes.append(Outcome(proposal.id, OutcomeKind.DROP, code, reason, best_score))
            else:
                outcomes.append(
                    Outcome(
                        proposal.id,
                        OutcomeKind.DEFER,
                        "HIGHER_VALUE_PROPOSAL_WON",
                        "Another proposal earned this moment; reconsider on the next tick.",
                        best_score,
                    )
                )

        if winner is None:
            return self._finish(
                Decision(
                    kind=DecisionKind.SILENCE,
                    reason="No safe proposal-route pair cleared the action threshold.",
                    outcomes=tuple(outcomes),
                    rejected_routes=tuple(rejected_routes),
                ),
                context,
            )

        selected = next(proposal for proposal in proposal_list if proposal.id == winner.proposal_id)
        target = next(device for device in device_list if device.id == winner.device_id)
        reason = self._selection_reason(selected, target, winner.modality, context)
        return self._finish(
            Decision(
                kind=DecisionKind.ACT,
                reason=reason,
                score=winner.score,
                proposal_id=selected.id,
                device_id=target.id,
                modality=winner.modality,
                cue=selected.cue,
                outcomes=tuple(outcomes),
                rejected_routes=tuple(rejected_routes),
                score_breakdown=winner.breakdown,
            ),
            context,
        )

    @staticmethod
    def _proposal_gate(
        proposal: Proposal,
        context: Context,
        moment: datetime,
    ) -> tuple[str, str] | None:
        if proposal.principal_id != context.principal_id:
            return "WRONG_PRINCIPAL", "Another person's proposal cannot spend this attention budget."
        if proposal.expires_at and moment >= proposal.expires_at:
            return "EXPIRED", "The proposal expired before it earned attention."
        missing = [flag for flag in proposal.required_context if not context.flag(flag)]
        if missing:
            return "REQUIRED_CONTEXT_MISSING", f"Waiting for context: {', '.join(missing)}."
        return None

    @staticmethod
    def _route_gate(
        proposal: Proposal,
        device: Device,
        modality: str,
        context: Context,
    ) -> str | None:
        if not device.online:
            return "DEVICE_OFFLINE"
        if device.principal_id != proposal.principal_id:
            return "WRONG_PRINCIPAL"
        if modality not in proposal.allowed_modalities:
            return "MODALITY_NOT_ALLOWED"
        if context.partner_asleep and modality == "speech":
            return "QUIET_HOME_CONSTRAINT"
        if PRIVACY_RANK[device.audience] > PRIVACY_RANK[proposal.privacy]:
            return "AUDIENCE_TOO_WIDE"
        return None

    @staticmethod
    def _score_route(
        proposal: Proposal,
        device: Device,
        modality: str,
        context: Context,
    ) -> Route:
        if context.at_doorway and device.zone == "doorway":
            route_fit = 1.0
        elif device.zone == "worn":
            route_fit = 0.70
        elif device.zone == "hall":
            route_fit = 0.70 if context.at_doorway else 0.45
        else:
            route_fit = 0.25

        if context.hands_full:
            modality_fit = {"speech": 1.0, "haptic": 0.40, "glow": 0.20}.get(modality, 0.0)
        else:
            modality_fit = {"glow": 1.0, "haptic": 0.65, "speech": 0.30}.get(modality, 0.0)

        breakdown = {
            "urgency": round(0.45 * proposal.urgency, 3),
            "relevance": round(0.30 * proposal.relevance, 3),
            "route_fit": round(0.20 * route_fit, 3),
            "modality_fit": round(0.25 * modality_fit, 3),
            "interruption_cost": round(-0.15 * device.interruption_cost, 3),
        }
        score = round(min(max(sum(breakdown.values()), 0.0), 1.0), 3)
        return Route(proposal.id, device.id, modality, score, breakdown)

    @staticmethod
    def _expiry_for(proposal_id: str, proposals: tuple[Proposal, ...]) -> datetime:
        proposal = next(item for item in proposals if item.id == proposal_id)
        return proposal.expires_at or datetime.max.replace(tzinfo=timezone.utc)

    @staticmethod
    def _selection_reason(
        proposal: Proposal,
        device: Device,
        modality: str,
        context: Context,
    ) -> str:
        if context.partner_asleep:
            return (
                f"{proposal.agent_id.replace('_', ' ')} won; {device.name} is co-located, "
                f"quiet, and can respond with {modality}."
            )
        if context.hands_full and modality == "speech":
            return (
                f"{proposal.agent_id.replace('_', ' ')} won; hands-full context makes "
                f"clear speech through {device.name} the most usable route."
            )
        return (
            f"{proposal.agent_id.replace('_', ' ')} won; {device.name} provides the "
            f"lowest-cost context-fit through {modality}."
        )

    def _finish(self, decision: Decision, context: Context) -> Decision:
        trace = decision.trace()
        trace["sequence"] = len(self._audit) + 1
        self._audit.append(trace)
        return decision

    @staticmethod
    def _require_unique_ids(items: tuple[Proposal, ...] | tuple[Device, ...], label: str) -> None:
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate {label} id")
