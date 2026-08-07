from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from manners import (
    Context,
    DecisionKind,
    Device,
    MannersEngine,
    OutcomeKind,
    Proposal,
    demo_devices,
    demo_proposals,
)


class MannersEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
        self.engine = MannersEngine()
        self.devices = demo_devices()
        self.proposals = demo_proposals(self.now)

    def arbitrate(self, context: Context):
        return self.engine.arbitrate(
            self.proposals,
            self.devices,
            context,
            now=self.now,
        )

    def test_quiet_departure_selects_co_located_door_charm(self) -> None:
        decision = self.arbitrate(
            Context(at_doorway=True, hands_full=True, partner_asleep=True)
        )
        self.assertEqual(decision.kind, DecisionKind.ACT)
        self.assertEqual(decision.proposal_id, "weather")
        self.assertEqual(decision.device_id, "door_charm")
        self.assertEqual(decision.modality, "glow")

    def test_awake_home_reroutes_hands_full_action_to_speech(self) -> None:
        decision = self.arbitrate(
            Context(at_doorway=True, hands_full=True, partner_asleep=False)
        )
        self.assertEqual(decision.proposal_id, "weather")
        self.assertEqual(decision.device_id, "hall_speaker")
        self.assertEqual(decision.modality, "speech")

    def test_leaving_context_gates_weather_and_calendar_wins_next(self) -> None:
        decision = self.arbitrate(
            Context(at_doorway=False, hands_full=True, partner_asleep=True)
        )
        self.assertEqual(decision.proposal_id, "calendar")
        self.assertEqual(decision.device_id, "worn_pin")
        weather = next(item for item in decision.outcomes if item.proposal_id == "weather")
        self.assertEqual(weather.kind, OutcomeKind.DEFER)
        self.assertEqual(weather.reason_code, "REQUIRED_CONTEXT_MISSING")

    def test_quiet_context_hard_blocks_every_speech_route(self) -> None:
        decision = self.arbitrate(
            Context(at_doorway=True, hands_full=True, partner_asleep=True)
        )
        speech_rejections = [
            route
            for route in decision.rejected_routes
            if route.device_id == "hall_speaker"
        ]
        self.assertTrue(speech_rejections)
        self.assertTrue(
            all(route.reason_code == "QUIET_HOME_CONSTRAINT" for route in speech_rejections)
        )

    def test_personal_proposal_never_widens_to_public_speaker(self) -> None:
        decision = self.arbitrate(
            Context(at_doorway=False, hands_full=True, partner_asleep=False)
        )
        self.assertEqual(decision.proposal_id, "calendar")
        self.assertEqual(decision.device_id, "worn_pin")
        self.assertTrue(
            any(
                route.proposal_id == "calendar"
                and route.device_id == "hall_speaker"
                and route.reason_code == "AUDIENCE_TOO_WIDE"
                for route in decision.rejected_routes
            )
        )

    def test_one_attention_slot_produces_exactly_one_action(self) -> None:
        decision = self.arbitrate(Context())
        actions = [item for item in decision.outcomes if item.kind is OutcomeKind.ACT]
        self.assertEqual(len(actions), 1)
        self.assertTrue(
            any(item.reason_code == "HIGHER_VALUE_PROPOSAL_WON" for item in decision.outcomes)
        )

    def test_closed_attention_budget_returns_silence(self) -> None:
        decision = self.arbitrate(Context(attention_budget=0))
        self.assertEqual(decision.kind, DecisionKind.SILENCE)
        self.assertTrue(
            all(item.reason_code == "ATTENTION_BUDGET_CLOSED" for item in decision.outcomes)
        )

    def test_closed_budget_still_drops_foreign_and_expired_input(self) -> None:
        foreign = replace(self.proposals[0], id="foreign", principal_id="visitor")
        expired = replace(
            self.proposals[1], id="expired", expires_at=self.now - timedelta(seconds=1)
        )
        decision = self.engine.arbitrate(
            (foreign, expired, self.proposals[2]),
            self.devices,
            Context(attention_budget=0),
            now=self.now,
        )
        codes = {item.proposal_id: item.reason_code for item in decision.outcomes}
        self.assertEqual(codes["foreign"], "WRONG_PRINCIPAL")
        self.assertEqual(codes["expired"], "EXPIRED")
        self.assertEqual(codes["social"], "ATTENTION_BUDGET_CLOSED")

    def test_cross_principal_proposal_and_device_never_route(self) -> None:
        foreign = replace(self.proposals[0], id="foreign", principal_id="visitor")
        foreign_device = Device(
            id="visitor_speaker",
            name="Visitor speaker",
            zone="doorway",
            modalities=("speech",),
            audience="public",
            interruption_cost=0.0,
            principal_id="visitor",
        )
        decision = self.engine.arbitrate(
            (foreign,),
            self.devices + (foreign_device,),
            Context(),
            now=self.now,
        )
        self.assertEqual(decision.kind, DecisionKind.SILENCE)
        self.assertEqual(decision.outcomes[0].reason_code, "WRONG_PRINCIPAL")

    def test_expired_proposal_is_dropped_before_scoring(self) -> None:
        expired = Proposal(
            id="expired",
            agent_id="test_agent",
            title="Old information",
            cue="Old cue",
            urgency=1.0,
            relevance=1.0,
            allowed_modalities=("glow",),
            expires_at=self.now - timedelta(seconds=1),
        )
        decision = self.engine.arbitrate(
            (expired,),
            self.devices,
            Context(),
            now=self.now,
        )
        self.assertEqual(decision.kind, DecisionKind.SILENCE)
        self.assertEqual(decision.outcomes[0].reason_code, "EXPIRED")

    def test_audit_contains_policy_facts_but_never_cue_content(self) -> None:
        self.arbitrate(Context())
        serialized = json.dumps(self.engine.audit_log)
        self.assertIn("weather", serialized)
        self.assertIn("door_charm", serialized)
        self.assertNotIn("Take the umbrella", serialized)
        self.assertNotIn("Design review soon", serialized)
        self.assertNotIn("partner_asleep", serialized)
        self.assertNotIn("weather agent won", serialized)

    def test_duplicate_proposal_and_device_ids_are_rejected(self) -> None:
        duplicate_proposal = replace(self.proposals[0], urgency=0.01)
        with self.assertRaisesRegex(ValueError, "duplicate proposal id"):
            self.engine.arbitrate(
                self.proposals + (duplicate_proposal,), self.devices, Context(), now=self.now
            )
        with self.assertRaisesRegex(ValueError, "duplicate device id"):
            self.engine.arbitrate(
                self.proposals, self.devices + (self.devices[0],), Context(), now=self.now
            )

    def test_unbounded_or_unknown_policy_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "urgency"):
            replace(self.proposals[0], urgency=float("nan"))
        with self.assertRaisesRegex(ValueError, "privacy"):
            replace(self.proposals[0], privacy="secret")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            replace(self.proposals[0], expires_at=datetime(2026, 8, 8, 9, 0))


if __name__ == "__main__":
    unittest.main()
