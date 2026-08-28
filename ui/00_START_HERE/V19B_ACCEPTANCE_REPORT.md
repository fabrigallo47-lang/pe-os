# PANTA V19.B Acceptance Report

## Result

**PASS - 22 of 22 V19.B acceptance and regression checks passed.**

The executable suite is `08_TEST_EVIDENCE/run_v19b_tests.py`. Machine-readable and human-readable results are stored beside it.

## Acceptance matrix

| Requirement | Implemented evidence | Executable proof | Result |
|---|---|---|---|
| Orion statement overlap below 20% | Rebuilt 42-claim growth case | Normalized exact overlap test: 0.0% | PASS |
| No buyout quantities in Orion | Growth-only projection, Registry and transitions | Fixture vocabulary scan | PASS |
| Both dates on claims/events/Registry | V19.B fixture patch and typed schemas | 75 + 42 claims, 4 source events and 26 fixture Registry events checked | PASS |
| Date-driven historical rendering | API and offline projection filters | 6 Orion claims on 12 May vs 42 on 26 August | PASS |
| Replay derived from event list | Empty fixture snapshots; runtime derivation | Exact event/date/hash replay assertions | PASS |
| Fifth epistemic class | `institutional_act` vocabulary and reclassification | No detected firm act may be `attested` | PASS |
| Typed eight-schema package | Nested types and enums | Schema self-check and sample validation | PASS |
| Engine output mapping | Pure Python and JavaScript adapters | Same sample maps twice identically; zero schema errors | PASS |
| Populated Human Stop | Orion retention transition | UI rendering and API gate | PASS |
| Settlement refused without authority | Server settlement invariant | HTTP 409 negative-path test | PASS |
| Populated blocked component | Orion pipeline coverage transition | UI rendering and API gate | PASS |
| Blocked scope remains explicit | Partial settlement contract | Refused without flag, accepted with bounded partial flag | PASS |
| Canonical pricing term | Package-wide text and PDF scan | Zero retired-phrase hits | PASS |

## Additional integrity checks

The same suite also verifies:

- fixture-backed Connected mode is refused;
- authority cannot be attested before preparation;
- a wrong Candidate is refused;
- a change outside the transition output is refused;
- course-specific external packages validate and require server acknowledgment;
- Python and browser runtime files pass syntax checks;
- browser rendering produces no console errors in the tested V19.B paths.

## Browser evidence

- `08_TEST_EVIDENCE/browser/orion_growth_bitemporal_replay.png`
- `08_TEST_EVIDENCE/browser/orion_human_stop.png`
- `08_TEST_EVIDENCE/browser/orion_blocked_component.png`
- `08_TEST_EVIDENCE/browser/orion_deal_bitemporal.png`

## Scope limit

This evidence certifies the bundled V19.B product build, explicit synthetic fixtures, public schemas, pure mapping adapters and stateful mock API. It does not certify production identity, external effects, enterprise persistence, Fabrizio's production compiler or Anto's separate production runtime.
