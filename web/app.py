"""Browser adapter for KNOCK's local few-shot acoustic learner."""

from __future__ import annotations

import asyncio
import json
import time

import numpy as np
from js import document, window
from pyodide.ffi import create_proxy

from knock import KnockEngine


PROFILE_KEY = "knock-profile-v1"
CALIBRATION_SECONDS = 1.8
CAPTURE_SECONDS = 2.8

engine: KnockEngine | None = None
mode = "idle"
capture_chunks: list[np.ndarray] = []
capture_started = 0.0
example_count = 0
proxies = []


def element(element_id: str):
    return document.getElementById(element_id)


def set_text(element_id: str, value: str) -> None:
    target = element(element_id)
    if target is not None:
        target.textContent = value


def set_disabled(element_id: str, disabled: bool) -> None:
    target = element(element_id)
    if target is not None:
        target.disabled = disabled


def set_progress(value: float) -> None:
    target = element("calibrate-progress")
    if target is not None:
        bounded = max(0.0, min(1.0, value))
        fill = target.querySelector("span")
        if fill is not None:
            fill.style.width = f"{bounded * 100:.1f}%"
        target.setAttribute("aria-valuenow", f"{bounded * 100:.0f}")


def bind(element_id: str, event_name: str, handler) -> None:
    target = element(element_id)
    if target is None:
        return
    proxy = create_proxy(handler)
    proxies.append(proxy)
    target.addEventListener(event_name, proxy)


def frame_to_numpy(frame) -> np.ndarray:
    values = frame.to_py() if hasattr(frame, "to_py") else frame
    try:
        return np.frombuffer(values, dtype=np.float32).copy()
    except (TypeError, ValueError):
        return np.asarray(values, dtype=np.float32).reshape(-1).copy()


def set_example_state(index: int, state: str) -> None:
    card = element(f"example-{index}")
    if card is None:
        return
    card.dataset.state = state
    label = card.querySelector("strong")
    if label is not None:
        label.textContent = {
            "empty": "waiting",
            "recording": "listening",
            "recorded": "learned",
        }.get(state, state)


def reset_example_cards() -> None:
    examples = element("examples")
    if examples is not None:
        examples.dataset.count = "0"
    for index in range(1, 4):
        set_example_state(index, "empty")


def update_training_ui(message: str | None = None) -> None:
    examples = element("examples")
    if examples is not None:
        examples.dataset.count = str(example_count)

    if engine is not None and engine.ready:
        set_text(
            "trainer-instruction",
            message or "Got it. Repeat your rhythm, then try to fool it with another sound.",
        )
        set_text("record-example", "rhythm learned")
        set_disabled("record-example", True)
        set_text("live-state", "listening for your rhythm")
        set_text("persistence-note", "This browser remembers the pattern. It does not keep the recording.")
    else:
        next_number = min(3, example_count + 1)
        set_text(
            "trainer-instruction",
            message or "Make the same short 2–6 hit knock, clap, or snap pattern inside each recording.",
        )
        set_text("record-example", f"record example {next_number} of 3")
        set_disabled("record-example", mode not in {"training", "idle"})
        set_text("live-state", "waiting for three takes")


def render_profile() -> None:
    if engine is None:
        return
    profile = engine.export_profile()
    threshold = float(profile.get("threshold", 0.0) or 0.0)
    set_text("live-threshold", f"{threshold:.3f}" if threshold else "not set")
    set_text("live-distance", "—")
    set_text("live-confidence", "—")
    set_text("live-latency", "—")


def append_event(result: dict) -> None:
    target = element("event-log")
    if target is None:
        return
    empty = target.querySelector(".empty-event")
    if empty is not None:
        empty.remove()
    item = document.createElement("li")
    moment = time.strftime("%H:%M:%S")
    name = document.createElement("span")
    score = document.createElement("strong")
    name.textContent = f"{moment}  rhythm matched"
    score.textContent = f"{result['confidence']:.0%}"
    item.appendChild(name)
    item.appendChild(score)
    target.prepend(item)
    while target.children.length > 5:
        target.removeChild(target.lastElementChild)


async def clear_detection_pulse() -> None:
    await asyncio.sleep(1.4)
    live = element("live-panel") or element("live-state")
    if live is not None:
        live.dataset.state = "listening"
    set_text("live-state", "listening for your rhythm")


def render_candidate(result: dict) -> None:
    detected = bool(result.get("detected", False))
    confidence = float(result.get("confidence", 0.0) or 0.0)
    distance = float(result.get("distance", 0.0) or 0.0)
    threshold = float(result.get("threshold", 0.0) or 0.0)
    latency = float(result.get("latency_ms", 0.0) or 0.0)

    set_text("live-confidence", f"{confidence:.0%}")
    set_text("live-distance", f"{distance:.3f}")
    set_text("live-threshold", f"{threshold:.3f}")
    set_text("live-latency", f"{latency:.0f} ms")

    live = element("live-panel") or element("live-state")
    if detected:
        if live is not None:
            live.dataset.state = "match"
        set_text("live-state", "rhythm matched")
        append_event(result)
        asyncio.create_task(clear_detection_pulse())
    else:
        if live is not None:
            live.dataset.state = "unknown"
        set_text("live-state", "unknown sound rejected")


def on_audio_frame(frame) -> None:
    global capture_chunks
    if engine is None:
        return
    audio = frame_to_numpy(frame)
    if audio.size == 0:
        return

    if mode in {"calibrating", "recording"}:
        capture_chunks.append(audio)
        return

    if mode == "listening" and engine.ready:
        result = engine.process(audio)
        if result is not None:
            render_candidate(dict(result))


frame_proxy = create_proxy(on_audio_frame)
proxies.append(frame_proxy)
window.knockFrameProxy = frame_proxy


async def collect_for(seconds: float, progress: bool = False) -> np.ndarray:
    global capture_chunks, capture_started
    capture_chunks = []
    capture_started = time.monotonic()
    while time.monotonic() - capture_started < seconds:
        elapsed = time.monotonic() - capture_started
        if progress:
            set_progress(elapsed / seconds)
        await asyncio.sleep(0.05)
    if progress:
        set_progress(1.0)
    if not capture_chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(capture_chunks)


async def calibrate_room(profile_loaded: bool = False) -> None:
    global mode
    if engine is None:
        return
    mode = "calibrating"
    set_disabled("record-example", True)
    set_text("mic-state", "Stay quiet for a moment while KNOCK learns this room.")
    set_text("trainer-instruction", "Calibrating the room noise. No audio leaves this page.")
    audio = await collect_for(CALIBRATION_SECONDS, progress=True)
    if audio.size:
        engine.set_noise(audio)
    set_progress(0.0)

    if profile_loaded and engine.ready:
        mode = "listening"
        set_text("mic-state", "Microphone live. Your saved signal is ready.")
    else:
        mode = "training"
        set_text("mic-state", "Room calibrated. Record the same signal three times.")
    update_training_ui()
    render_profile()


def restore_profile() -> bool:
    global example_count
    if engine is None:
        return False
    raw = window.localStorage.getItem(PROFILE_KEY)
    if not raw:
        return False
    try:
        engine.load_profile(json.loads(str(raw)))
        if not engine.ready:
            return False
        example_count = 3
        for index in range(1, 4):
            set_example_state(index, "recorded")
        examples = element("examples")
        if examples is not None:
            examples.dataset.count = "3"
        return True
    except Exception:
        window.localStorage.removeItem(PROFILE_KEY)
        return False


async def enable_microphone() -> None:
    global engine, mode
    set_disabled("enable-mic", True)
    set_text("enable-mic", "requesting microphone")
    set_text("mic-state", "Waiting for microphone permission.")
    try:
        sample_rate = int(await window.knockAudio.start())
        engine = KnockEngine(sample_rate)
        profile_loaded = restore_profile()
        set_text("enable-mic", "microphone enabled")
        mic_button = element("enable-mic")
        if mic_button is not None:
            mic_button.dataset.active = "true"
        set_disabled("reset-profile", False)
        await calibrate_room(profile_loaded)
    except Exception as error:
        mode = "error"
        set_disabled("enable-mic", False)
        set_text("enable-mic", "try microphone again")
        set_text("mic-state", f"Microphone unavailable: {error}")


def enable_handler(_event=None) -> None:
    asyncio.create_task(enable_microphone())


async def record_training_example() -> None:
    global mode, example_count
    if engine is None or mode != "training":
        return

    slot = min(3, example_count + 1)
    mode = "recording"
    set_example_state(slot, "recording")
    set_disabled("record-example", True)
    set_text("record-example", "recording now")
    set_text("trainer-instruction", "Perform the complete sound once, then leave a short silence.")
    try:
        audio = await collect_for(CAPTURE_SECONDS, progress=True)
        result = dict(engine.add_example(audio))
    except Exception:
        set_example_state(slot, "empty")
        mode = "training"
        set_progress(0.0)
        update_training_ui("That take could not be processed. The recorder is ready—try it again.")
        return
    set_progress(0.0)
    if not result.get("ok", False):
        set_example_state(slot, "empty")
        mode = "training"
        update_training_ui(str(result.get("reason", "No clear pattern found. Try again.")))
        return

    example_count = int(result.get("example_count", example_count + 1))
    set_example_state(slot, "recorded")
    if engine.ready:
        profile = engine.export_profile()
        window.localStorage.setItem(PROFILE_KEY, json.dumps(profile))
        mode = "listening"
        render_profile()
    else:
        mode = "training"
    if engine.ready:
        consistency = float(result.get("consistency", 1.0) or 0.0)
        if consistency < 0.35:
            update_training_ui(
                "All three examples are recorded, but they differ. Try the detector; reset if matches feel loose."
            )
        else:
            update_training_ui()
    else:
        update_training_ui(
            f"Example {example_count} learned. Click record for example {example_count + 1}."
        )


def record_handler(_event=None) -> None:
    asyncio.create_task(record_training_example())


async def reset_profile() -> None:
    global example_count, mode
    if engine is None:
        return
    window.localStorage.removeItem(PROFILE_KEY)
    engine.reset()
    example_count = 0
    mode = "calibrating"
    reset_example_cards()
    set_text("persistence-note", "No rhythm is remembered.")
    target = element("event-log")
    if target is not None:
        target.replaceChildren()
        empty = document.createElement("li")
        empty.className = "empty-event"
        empty.textContent = "Your matched sounds will appear here."
        target.appendChild(empty)
    await calibrate_room(False)


def reset_handler(_event=None) -> None:
    asyncio.create_task(reset_profile())


bind("enable-mic", "click", enable_handler)
bind("record-example", "click", record_handler)
bind("reset-profile", "click", reset_handler)

reset_example_cards()
set_disabled("enable-mic", False)
set_disabled("record-example", True)
set_disabled("reset-profile", True)
set_text("runtime-label", "detector ready")
set_text("mic-state", "KNOCK is ready. Enable your microphone to begin.")
set_text("persistence-note", "Nothing is stored until you teach a signal.")
