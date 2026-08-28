# PANTA V19.B Change Specification

## Status and precedence

This document is the authoritative product-experience addendum to the V19 professional delivery for the V19.B corrections. It does not replace the V19 room architecture, visual system, information architecture or user journey except where expressly stated below.

Frozen machine contracts and conformance tests continue to outrank this document. The Engineering Source of Truth outranks prototype behavior and screenshots.

## Changed product contracts

### Generalization contract

A second case may be shown as evidence of generalization only when it is structurally and semantically distinct, or when it is visibly labelled as a structural clone for navigation testing. V19.B uses the first route: Orion is a distinct growth-equity case.

The same frontend renders Keystone and Orion without a case-specific component fork. Generic components respond to projection-provided object types, metrics, questions, scenarios, authority verbs and transition objects.

### Temporal contract

Every material claim, source event and Registry event must expose `effective_date` and `known_at`.

The global as-of selector is a date selector over the knowledge axis. Selecting a past date reconstructs the case using only records whose `known_at` is no later than the selected cutoff. Current institutional state identity and historical knowledge projection remain separate concepts.

Replay is read-only and event-derived. A replay step resolves to an immutable Registry event, both dates, source and result state identifiers where present, and a stable hash. Rendering replay cannot append a new institutional event.

### Epistemic contract

`institutional_act` is the fifth class and is mandatory for the firm's own:

- underwriting judgment;
- approved ceiling or constraint;
- IC decision;
- condition, direction or mandate;
- formal adoption or rejection;
- authority act and settlement act.

`attested` is reserved for an independently attested source fact, executed contractual definition, audited figure or comparable external attestation. Institutional acts may depend on attested evidence, but they are not themselves attested facts.

### Transition mapping contract

The frontend consumes the frozen Transition Engine output through a pure mapping boundary. The mapper:

- requires all 18 frozen output fields;
- requires `source_event_id` as the integration binding field;
- preserves engine ordering and typed transition objects;
- may add display aliases derived directly from explicit engine values;
- may not compute economics, causal closure, authority, materiality or settlement;
- may not mutate its input.

### Human Stop contract

A Human Stop must be visible when returned by the transition output. It must show:

- stop ID;
- reason;
- required role or authority level;
- authority verb;
- affected downstream scope.

Settlement is unavailable until a valid authority record is scoped to the same run, Candidate and Human Stop.

### Blocked-component contract

A blocked component must remain visible with:

- component ID;
- reason code;
- human-readable reason;
- downstream scope;
- resolution route.

The blocked scope does not disappear when an independent region settles. Partial settlement must be explicit and preserve the blocked region in the result.

### Language contract

The product term is **approved EV ceiling**. The retired pricing phrase is forbidden in code, fixtures, UI copy and generated documents.

## Unchanged product contracts

V19.B retains:

- one persistent Live Investment Case;
- Underwrite and Re-underwrite as lifecycle expressions of the same object;
- Source to Claim to Question to Case Position to Model/Economic Object to Decision/Condition to Outcome;
- Candidate, Current and Approved separation;
- universal shell, Object Aperture and Causal Rail;
- Change Arrival, Professional Review, Change Impact and Action Frontier;
- gated Decision Room and externality-boundary Execution Room;
- Registry and Causal Replay as separate surfaces;
- explicit Connected, Mock Connected and Offline Demo modes;
- fixture-free Connected frontend core;
- no silent fallback and no optimistic external success.

## Acceptance evidence

The binding release evidence is the 22-check V19.B suite and its browser captures under `08_TEST_EVIDENCE/`.
