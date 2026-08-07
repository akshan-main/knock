# MANNERS

## [Open the live demo →](https://akshan-main.github.io/era-manners/)

> When every object can speak, something decides who should.

MANNERS is an attention scheduler for intelligent physical objects. Agents do
not address a person directly; they submit typed proposals to a shared kernel.
MANNERS decides which proposal may act, which object may carry it, and when the
right decision is silence.

It treats human attention like an operating-system resource: scarce,
contextual, private, and owned by the person.

## The 60-second scene

It is 08:00. A person is at the doorway with both hands full. Their partner is
asleep, and only one object may spend attention.

| Agent proposal | MANNERS decision | Reason |
| --- | --- | --- |
| Weather: “Rain starts in 12 minutes” | `ACT` through the door charm's quiet glow | Urgent, relevant, and useful at the doorway |
| Calendar: “Design review in 25 minutes” | `DEFER` | Valuable, but weather won the single attention slot |
| Social: “Maya sent three photos” | `DROP` | Not valuable enough to interrupt now |

Every speech route is rejected because the home must stay quiet. Change that
one fact and the same weather proposal moves to the hall speaker. Move away
from the doorway and weather waits while the calendar wins through a worn
pin's haptic output.

Close the `Attention open` gate and every otherwise valid proposal is held:
the kernel returns `SILENCE` and no object receives a route.

The demo shows the answer to four questions: **why this, why now, why this
object, and why not the others?**

## The OS primitive

Individual agents have local goals. They do not have a complete view of the
person, the room, or every other agent asking to act. MANNERS is the shared
policy boundary they cannot bypass:

```text
Proposal[] + Context + Device[]
              ↓
    principal / expiry / privacy / context gates
              ↓
       proposal × device × modality scoring
              ↓
         shared attention budget
              ↓
        ACT / DEFER / DROP / SILENCE
```

This is not a notification dashboard. It is closer to a process scheduler:
agents request attention instead of taking it, physical objects expose output
capabilities, and the kernel admits one safe action or none.

## Python architecture

All policy and interaction logic is Python 3.11+ with no application
dependencies:

```text
manners/
  models.py       proposals, context, devices, routes, outcomes
  engine.py       hard gates, scoring, arbitration, audit
  demo.py         deterministic three-context walkthrough
tests/
  test_engine.py  thirteen policy, determinism, and privacy tests
web/
  app.py          Python DOM adapter for the live page
  bootstrap.js    loads pinned CPython/WebAssembly; no policy logic
index.html        static GitHub Pages shell
```

The public page loads the repository's `manners` package into Pyodide and runs
the same engine as the native tests. There is no server, JavaScript policy
copy, model API key, Node project, or TypeScript build.

```bash
python3 -m manners.demo --fast
python3 -m unittest discover -v
```

## Decisions are inspectable

MANNERS first rejects routes that violate hard constraints: wrong principal,
expiry, missing required context, offline objects, disallowed modalities,
excessive audience, or quiet-home policy. It then scores legal routes from
urgency, relevance, location fit, modality fit, and interruption cost.

The decision trace records policy facts, scores, rejected routes, and reason
codes, but deliberately omits proposal cue content.

The tests verify that:

- a quiet departure selects the co-located door charm;
- waking the home reroutes the action to speech;
- leaving the doorway gates weather and lets calendar win;
- quiet-home policy blocks every speech route;
- personal content never widens to a public speaker;
- one attention slot produces exactly one action;
- a closed attention budget produces silence;
- cross-principal, expired, and unsafe proposals cannot route; and
- persisted audit traces contain no cue text or human-context fields;
- duplicate identities cannot corrupt proposal-to-route selection; and
- unbounded, unknown, or timezone-naive policy inputs are rejected.

## Why Era

[Era](https://era.world/) is building an intelligence layer through which
physical objects can listen, think, speak, act, and remember. Once many chosen
objects have agency, coordination becomes part of the operating system.

MANNERS explores that layer: intelligence that is coherent across objects,
socially aware in a room, and quiet enough to disappear when it has nothing
worth saying.

## Honest limits

MANNERS is an independent prototype, not an Era integration. Proposals,
devices, and physical context are simulated. The scorer is deterministic and
hand-tuned; it has not learned a person's interruptibility from longitudinal
behavior. This version handles one principal and one arbitration tick, with no
real sensor transport, durable queue, device authentication, or hardware
actuation. MANNERS governs proposals produced upstream; it does not generate
them with an LLM.

Those constraints are intentional for this submission: the implemented claim
is small and testable—**objects propose; policy decides; at most one acts.**
