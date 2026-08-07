"""Thin browser adapter for the same MANNERS kernel exercised by native tests."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

from js import document
from pyodide.ffi import create_proxy

from manners import Context, DecisionKind, MannersEngine, demo_devices, demo_proposals


NOW = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
PROPOSALS = demo_proposals(NOW)
DEVICES = demo_devices()

engine = MannersEngine()
state = {
    "at_doorway": True,
    "hands_full": True,
    "partner_asleep": True,
    "attention_open": True,
}
automatic = False
proxies = []

PROPOSAL_NAMES = {
    "weather": "Weather agent",
    "calendar": "Calendar agent",
    "social": "Social agent",
}
DEVICE_NAMES = {
    "door_charm": "Door charm",
    "worn_pin": "Worn pin",
    "hall_speaker": "Hall speaker",
}
DEVICE_ELEMENTS = {
    "door_charm": "object-charm",
    "worn_pin": "object-pin",
    "hall_speaker": "object-speaker",
}
ROUTE_ELEMENTS = {
    "door_charm": "route-charm",
    "worn_pin": "route-pin",
    "hall_speaker": "route-speaker",
}
TOGGLE_ELEMENTS = {
    "at_doorway": "toggle-doorway",
    "hands_full": "toggle-hands",
    "partner_asleep": "toggle-asleep",
    "attention_open": "toggle-attention",
}
OUTCOME_LABELS = {"act": "ACT NOW", "defer": "HELD", "drop": "SILENT"}
REASON_LABELS = {
    "QUIET_HOME_CONSTRAINT": "too loud while partner sleeps",
    "AUDIENCE_TOO_WIDE": "audience wider than proposal privacy",
    "MODALITY_NOT_ALLOWED": "proposal forbids this modality",
    "REQUIRED_CONTEXT_MISSING": "required doorway context is absent",
    "BELOW_ACTION_THRESHOLD": "not valuable enough to interrupt",
    "HIGHER_VALUE_PROPOSAL_WON": "attention already claimed",
}


def element(element_id):
    return document.getElementById(element_id)


def bind(element_id, event_name, handler):
    proxy = create_proxy(handler)
    proxies.append(proxy)
    element(element_id).addEventListener(event_name, proxy)


def set_text(element_id, value):
    element(element_id).textContent = value


def replace_list(element_id, lines):
    target = element(element_id)
    target.replaceChildren()
    for line in lines:
        item = document.createElement("li")
        item.textContent = line
        target.appendChild(item)


def current_context():
    return Context(
        at_doorway=state["at_doorway"],
        hands_full=state["hands_full"],
        partner_asleep=state["partner_asleep"],
        attention_budget=int(state["attention_open"]),
    )


def render_toggles():
    for key, element_id in TOGGLE_ELEMENTS.items():
        target = element(element_id)
        target.setAttribute("aria-pressed", str(state[key]).lower())
        target.disabled = automatic


def render_outcomes(decision):
    for outcome in decision.outcomes:
        card = element(f"proposal-{outcome.proposal_id}")
        card.dataset.outcome = outcome.kind.value
        set_text(f"outcome-{outcome.proposal_id}", OUTCOME_LABELS[outcome.kind.value])


def route_statuses(decision):
    if decision.proposal_id is None:
        return {device.id: "attention unavailable" for device in DEVICES}
    result = {device.id: "lower contextual score" for device in DEVICES}
    for rejection in decision.rejected_routes:
        if rejection.proposal_id != decision.proposal_id:
            continue
        label = REASON_LABELS.get(rejection.reason_code, rejection.reason_code.lower().replace("_", " "))
        result[rejection.device_id] = label
    if decision.device_id:
        result[decision.device_id] = "selected"
    return result


def render_devices(decision):
    statuses = route_statuses(decision)
    for device_id, element_id in DEVICE_ELEMENTS.items():
        target = element(element_id)
        selected = device_id == decision.device_id
        target.dataset.selected = str(selected).lower()
        set_text(ROUTE_ELEMENTS[device_id], statuses[device_id])


def render_breakdown(decision):
    target = element("score-breakdown")
    target.replaceChildren()
    if not decision.score_breakdown:
        return
    for name, value in decision.score_breakdown.items():
        term = document.createElement("dt")
        term.textContent = name.replace("_", " ")
        amount = document.createElement("dd")
        amount.textContent = f"{value:+.3f}"
        target.appendChild(term)
        target.appendChild(amount)


def render_trace(decision):
    outcome_facts = []
    for outcome in decision.outcomes:
        label = PROPOSAL_NAMES[outcome.proposal_id]
        outcome_facts.append(
            f"{label}: {OUTCOME_LABELS[outcome.kind.value].lower()} — "
            f"{REASON_LABELS.get(outcome.reason_code, outcome.reason.lower())}."
        )

    rejection_facts = []
    seen = set()
    rejected_devices = set()
    for rejection in decision.rejected_routes:
        if rejection.proposal_id != decision.proposal_id:
            continue
        if rejection.device_id == decision.device_id:
            continue
        key = (rejection.device_id, rejection.reason_code)
        if key in seen:
            continue
        seen.add(key)
        rejection_facts.append(
            f"{DEVICE_NAMES[rejection.device_id]}: "
            f"{REASON_LABELS.get(rejection.reason_code, rejection.reason_code.lower())}."
        )
        rejected_devices.add(rejection.device_id)
    if decision.proposal_id:
        for device in DEVICES:
            if device.id != decision.device_id and device.id not in rejected_devices:
                rejection_facts.append(f"{device.name}: legal route, but lower contextual score.")
    elif not rejection_facts:
        rejection_facts.append("Attention is unavailable, so no physical route was evaluated.")

    replace_list("decision-facts", outcome_facts)
    replace_list("rejection-facts", rejection_facts[:5])
    set_text("raw-trace", json.dumps(decision.trace(), indent=2))


def render_decision():
    decision = engine.arbitrate(PROPOSALS, DEVICES, current_context(), now=NOW)
    render_toggles()
    render_outcomes(decision)
    render_devices(decision)
    render_breakdown(decision)
    render_trace(decision)

    lab = element("lab")
    lab.dataset.ready = "true"
    lab.setAttribute("aria-busy", "false")
    lab.dataset.route = decision.device_id or "silence"
    lab.classList.remove("decision-shift")
    _ = lab.offsetWidth
    lab.classList.add("decision-shift")

    if decision.kind is DecisionKind.ACT:
        proposal = PROPOSAL_NAMES[decision.proposal_id]
        device = DEVICE_NAMES[decision.device_id]
        set_text("decision-kind", "ACT NOW")
        set_text("decision-agent", f"{proposal.upper()} → {device.upper()}")
        if decision.modality == "glow":
            cue = "Two quiet blue pulses."
        elif decision.modality == "haptic":
            cue = "One private haptic tap."
        else:
            cue = f'“{decision.cue}.”'
        set_text("decision-cue", cue)
    else:
        set_text("decision-kind", "SILENCE")
        set_text("decision-agent", "NO AGENT MAY ACT")
        set_text("decision-cue", "The world stays quiet.")

    set_text("decision-reason", decision.reason)
    set_text("decision-score", f"{decision.score:.3f}")
    element("score-fill").style.width = f"{decision.score * 100:.1f}%"
    return decision


def toggle_context(key):
    def handler(_event=None):
        if automatic:
            return
        state[key] = not state[key]
        render_decision()

    return handler


def reset_scene():
    state.update(
        at_doorway=True,
        hands_full=True,
        partner_asleep=True,
        attention_open=True,
    )
    render_decision()


async def play_scene():
    global automatic
    automatic = True
    element("hero-run").disabled = True
    element("run-scene").disabled = True
    reset_scene()
    element("lab").scrollIntoView({"behavior": "smooth", "block": "start"})
    await asyncio.sleep(2.6)
    state["partner_asleep"] = False
    render_decision()
    await asyncio.sleep(2.6)
    state["at_doorway"] = False
    render_decision()
    await asyncio.sleep(2.6)
    state["attention_open"] = False
    render_decision()
    await asyncio.sleep(2.4)
    state.update(at_doorway=True, partner_asleep=True, attention_open=True)
    render_decision()
    await asyncio.sleep(1.0)
    automatic = False
    render_toggles()
    element("hero-run").disabled = False
    element("run-scene").disabled = False


def start_scene(_event=None):
    asyncio.create_task(play_scene())


for context_key, toggle_id in TOGGLE_ELEMENTS.items():
    bind(toggle_id, "click", toggle_context(context_key))
bind("hero-run", "click", start_scene)
bind("run-scene", "click", start_scene)

render_decision()
element("runtime").classList.add("runtime-ready")
element("runtime").lastChild.textContent = f" CPython {sys.version.split()[0]} / kernel ready"
set_text("loading-note", "Ready. Every result below is produced by manners/engine.py.")
element("hero-run").disabled = False
element("run-scene").disabled = False
render_toggles()
