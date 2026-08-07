"""A concise native-Python walkthrough of MANNERS."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from .engine import MannersEngine, demo_devices, demo_proposals
from .models import Context


SCENES = (
    (
        "leaving quietly",
        Context(at_doorway=True, hands_full=True, partner_asleep=True),
    ),
    (
        "house awake",
        Context(at_doorway=True, hands_full=True, partner_asleep=False),
    ),
    (
        "away from doorway",
        Context(at_doorway=False, hands_full=True, partner_asleep=True),
    ),
)


def run_scenes():
    now = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    engine = MannersEngine()
    proposals = demo_proposals(now)
    devices = demo_devices()
    decisions = [
        (label, engine.arbitrate(proposals, devices, context, now=now))
        for label, context in SCENES
    ]
    return engine, decisions


def main() -> None:
    parser = argparse.ArgumentParser(description="Run three MANNERS arbitration scenes.")
    parser.add_argument("--fast", action="store_true", help="Print without pauses.")
    args = parser.parse_args()
    _, decisions = run_scenes()

    print("\nMANNERS / attention scheduling for Era objects\n")
    print("Three agents propose. One physical object may act.\n")
    for label, decision in decisions:
        if decision.kind.value == "act":
            print(
                f"{label.upper():<20} ACT  {decision.proposal_id} -> "
                f"{decision.device_id}.{decision.modality}  score={decision.score:.3f}"
            )
            print(f"{'':20} cue={decision.cue!r}")
        else:
            print(f"{label.upper():<20} SILENCE  {decision.reason}")
        for outcome in decision.outcomes:
            print(f"{'':20} {outcome.proposal_id:<10} {outcome.kind.value:<6} {outcome.reason_code}")
        print()
        if not args.fast:
            time.sleep(0.8)


if __name__ == "__main__":
    main()

