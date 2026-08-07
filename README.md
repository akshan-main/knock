# KNOCK

## [Try the live prototype →](https://akshan.dev/knock/)

> Your intelligence should learn your signal—not make you learn its wake word.

KNOCK learns a short percussive signal from three examples through your actual
microphone. Teach it a desk knock, clap, or finger-snap pattern; repeat the
pattern at a different volume or tempo; KNOCK emits a typed event when the live
audio matches and stays silent when it does not.

There is no scripted assistant response or simulated object. The implemented
boundary is deliberately smaller: turn a personal acoustic gesture into a
reusable input event for an AI operating system.

## Try it in 60 seconds

1. Allow microphone access and remain quiet while KNOCK measures the room.
2. Perform the same 2–6 hit pattern three times.
3. Repeat it slightly faster, slower, softer, or louder.
4. Try ordinary speech or a different rhythm as a negative.

The page shows the live match score, learned threshold, decision latency, and
event log. The result is not known in advance: the profile is fitted in your
browser from the sound you choose after the page loads.

## What runs

```text
microphone PCM
    → adaptive room calibration
    → robust conditioning + RMS onset detection
    → interval-ratio + relative-amplitude features
    → three-example template set + pairwise-calibrated threshold
    → dynamic-time-warped feature distance + unknown rejection
    → silence closure + duplicate cooldown
    → PersonalSignalDetected(score, latency_ms)
```

The browser's AudioWorklet buffers microphone frames. CPython runs in the page
through Pyodide; NumPy-backed feature extraction, profile learning, threshold
calibration, and streaming decisions remain in Python. The JavaScript surface
provides browser audio, runtime bootstrapping, and presentation; it does not
implement learning or recognition.

Raw microphone samples stay in the current browser session and are not stored.
Only the learned numeric profile may persist in local storage, where reset can
remove it. KNOCK has no audio upload endpoint, backend, model API, Node project,
or TypeScript build.

## Architecture

```text
knock/audio.py     PCM conditioning and onset extraction
knock/features.py  tempo- and amplitude-normalized motif descriptors
knock/learner.py   template fitting, consistency, distance, threshold
knock/detector.py  streaming closure, decisions, and cooldown
web/app.py         Python adapter between the page and the detector
web/bootstrap.js   pinned Pyodide loader
web/audio-worklet.js
                   microphone capture and PCM buffering
index.html         static GitHub Pages shell
web/styles.css     interaction and responsive layout
```

The public prototype is a static site. To serve it locally:

```bash
python3 -m pip install -e .
python3 -m http.server 8000
```

Then open `http://localhost:8000`. Microphone access requires a secure browser
context; `localhost` and the HTTPS GitHub Pages deployment both qualify.

## Why this belongs in an AI OS

An operating system for physical intelligence needs to convert continuous,
noisy sensor streams into bounded events that higher-level agents can consume.
KNOCK explores one such primitive: a private input vocabulary learned from its
owner instead of selected from a fixed catalog.

This is relevant to [Era's](https://era.world/) work on an intelligence layer
through which chosen physical objects can listen, think, speak, act, and
remember. KNOCK focuses only on the listening boundary and makes no claim of
running on Era hardware.

## Honest limits

KNOCK is an independent browser prototype, not a hardware integration. It is
optimized for short, separated percussive motifs in the room where training
occurs; it is not general sound recognition, speech recognition, speaker
identification, authentication, or a secure acoustic password. Three examples
cannot cover microphones, rooms, users, and noise conditions encountered in
production. Pyodide also adds latency and startup cost that an embedded
implementation would not have.

The narrow claim is the one the live page lets you verify: **teach a new
percussive pattern locally, then recognize or reject subsequent microphone
input against what was just learned.**
