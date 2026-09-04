# PANTA dynamics backend

This directory is the backend-owned, deployable copy of the state-transition
runtime. Production pipeline and API code import it directly; no downloaded
validator kit is needed to build a Candidate.

Backend entry point:

```python
from backend.dynamics import load_event_batch, run_bundle_transition

events = load_event_batch(bundle_dir, event_id)
result = run_bundle_transition(bundle_dir, events, persist_outputs=True)
```

``persist_outputs=True`` writes the exact runtime-produced Candidate state,
Candidate graph and transition output atomically. Promotion to Current is a
separate call to ``settle_candidate_state`` after the API has satisfied the
human stops returned by the engine.

## Governed settlement boundary

The V20 API promotes a Candidate only through the explicit sequence
`admit -> prepare -> attest (when required) -> settle`:

- `prepare` accepts one or more IDs emitted in `artifact_change_sets`; empty,
  duplicate, unknown or Candidate-mismatched selections are rejected;
- authority records are bound to the run, Candidate, replay hash, normalized
  Human Stop, policy references, selected authority rule, authenticated
  server-session principal, server-owned actor assignment, authority verb,
  admissible course and prepared selection. The
  immutable record payload is content-hashed, signed with Ed25519 and appended
  transactionally to a SQLite hash-chain ledger before it is embedded in the
  run registry;
- each act carries a bitemporal authority-assignment snapshot (assignment ID
  and version, granted roles and verbs, effective interval, knowledge time and
  revocation facts). Later execution and settlement validate that signed
  historical snapshot rather than depending on the actor's current directory
  entry. A ledger entry missing from the JSON run registry is recovered on
  restart;
- `actor_id` remains in the request contract for explicitness, but it is never
  trusted as identity. Authority attestation requires a high-entropy,
  server-issued `X-Panta-Session` token (the legacy `session_id` query parameter
  remains accepted); the token must resolve to the same actor and case. Only
  its SHA-256 digest and validity interval enter the signed record, never the
  bearer token itself. Sessions expire after eight hours by default; configure
  `PANTA_AUTH_SESSION_TTL_SECONDS` to change that lifetime;
- correction-only, unresolved-policy and non-waivable Human Stops are marked
  non-attestable by the server and cannot be bypassed with an authority record;
- `settle` must repeat the exact prepared Candidate and selection. A
  compare-and-swap checks both the prior state ID and graph hash, plus the
  persisted Candidate graph and state-envelope hashes;
- partial settlement requires an explicit opt-in and overlays only the selected
  unblocked object scope. Blocked components and unrelated Human Stops remain
  in `pending_settlement` for replay;
- a durable settlement journal makes a multi-file Current/runtime commit
  recoverable by replaying the same idempotency key after interruption.

The legacy direct event-settlement route is intentionally disabled because it
cannot prove the prepared selection or scoped authority records.

Production deployments should provide `PANTA_AUTHORITY_SIGNING_KEY` as either
an Ed25519 PKCS8 PEM value or a base64url-encoded 32-byte private key. Local
development generates a mode-`0600` key beside `runs.json`. The signing key ID
is the SHA-256 fingerprint of the public key. Trusted public keys are kept in
the mode-`0600`, versioned `authority_trusted_keys.json` keyring beside
`runs.json`. When a new private key signs for the first time, the prior active
key is atomically marked `RETIRED`; historical records at or before its
retirement remain verifiable, while new signatures under the retired key fail
closed. A `REVOKED` key fails from its declared `revoked_effective_at`.

Stateless or ephemeral deployments can additionally provide
`PANTA_AUTHORITY_TRUSTED_PUBLIC_KEYS` as a JSON object mapping each
`sha256:<public-key-fingerprint>` to its PEM or base64url-encoded 32-byte
Ed25519 public key. Verification uses the record's `signing_key_id` and never
requires access to a historical private key. Unknown, malformed, conflicting,
post-retirement or effectively revoked keys fail closed.
The persisted shape is defined by
`schemas/authority_keyring.schema.json`.

Unsigned pre-`authority-record/2.0` records are deliberately not promoted into
the ledger. Any still-PREPARED legacy run must be explicitly migrated or
re-attested; settlement never silently upgrades an old authority act.

The runtime consumes a conforming Live Investment Case graph. It does not
consume or mutate the raw extraction database.

```python
from runtime import apply_state_transition

result = apply_state_transition(
    prior_state=current_live_case,
    event_batch=events,
    execution_mapping=execution_mapping,
    materiality_policy=materiality_policy,
    authority_policy=authority_policy,
)

candidate = result["candidate_state"]
delta = result["transition_output"]
```

For compiler extraction output (`nodes` + `edges`), use the stable admission
adapter first:

```python
from runtime import apply_extraction_transition

result = apply_extraction_transition(
    extraction_graph,
    events,
    admission_manifest,
    materiality_policy,
    authority_policy,
)
```

The admission manifest must declare exactly one `admission_mode`:
`AUTO_POLICY`, `HUMAN_CONFIRMED`, or `AUTHORITY_RECORDED`. There is no implicit
default and the adapter never infers a human mode from an actor field.

For the compiled Financial Gold mapping, use the Gold boundary adapter:

```python
from runtime import apply_gold_transition

result = apply_gold_transition(
    gold_mapping,
    events,
    materiality_policy,
    authority_policy,
    semantic_graph=gold_semantic_graph,
)
```

The Gold adapter translates the exact Excel grammar used by the supplied
mapping (`IF`, `MIN`, `MAX`, `SUM`, ranges, percentages and comparisons),
normalizes a formula-consistent executable baseline while retaining each
source value, builds typed dated cash-flow vectors and evaluates XIRR with a
deterministic ACT/365 solver. Non-conventional cash flows with multiple sign
changes are exposed as ambiguous rather than assigned an arbitrary root.

The manifest is mandatory. Extracted claims not explicitly admitted remain
`validation_only`; claim-to-claim relations are reported but are not converted
into canonical dependencies. Missing formulas, directions, solver configs and
institutional state remain explicit `coverage_limits`.

Implemented:

- event validation, normalization and deterministic batching;
- conflict merge with no arbitrary winner;
- semantic applicability checks;
- immutable Candidate construction;
- conservative affected-set closure;
- SCC condensation ordering;
- three-valued support-route evaluation (`TRUE` / `FALSE` / `UNKNOWN`);
- `OR` between alternative routes, preserving each route's internal logic;
- circular-support invalidation without invoking a numerical solver;
- deterministic Decimal formula recomputation in the Candidate;
- deterministic topological recomputation of large acyclic formula graphs;
- typed dated-cash-flow construction and deterministic XIRR evaluation;
- applicable/material contradiction handling without changing decision status;
- materiality classification from versioned M0-M3 policy inputs;
- fail-closed materiality coverage: an unmatched or unevaluable delta is never
  auto-reconciled into Current;
- policy-driven Current/Approved authority routing and separation of duties;
- cumulative materiality against `K_t`, including sub-tolerance audit;
- first-class rule switches with provenance and dependent requeue;
- deterministic numerical SCC classification and solving;
- deterministic inverse solving with binding-constraint disclosure;
- incremental/global projection oracle;
- workflow loops as ordered events rather than numerical cycles;
- Candidate / Current / Approved separation;
- append-only history records and deterministic replay hash.

All 22 frozen normative TCE cases have explicit executable coverage in the
included test suite. Six additional tests cover the extraction/admission
boundary, four integration tests cover the real Financial Gold mapping and two
tests cover typed dated cash flows/XIRR.
Unmapped residual scope is always reported explicitly in
`coverage_limits`; it is never guessed.

### Materiality coverage contract

`classification_coverage` is an optional additive object in the materiality
policy input. It may declare `unmatched_delta_class`, `unmatched_rule_id`, and
versioned `m0_safe_harbors`. Each safe harbor uses the existing selector
grammar plus `fields` and optional `delta_reason_codes`.
Conditions on a safe harbor are closed vocabulary: the runtime currently
supports `DETERMINISTIC_DERIVED_CHANGE` and
`TARGET_REMAINS_SUPPORTED_BY_ALTERNATIVE_ROUTE`; an unknown condition fails
closed.
Coverage alone does not authorize Current adoption. An M0 result is reconciled
only after every declared `m0_auto_reconciliation_guards` condition passes;
the per-condition result is returned in
`materiality_assessment.m0_auto_reconciliation_guards`.

For backward compatibility, policies without this object are still accepted.
They are intentionally safe by default: every delta not covered by an economic
threshold is classified at least `M1_PROFESSIONAL_REVIEW`. A policy cannot set
the unmatched fallback to `M0_LOCAL`. The transition output retains all prior
fields and adds `materiality_assessment.classification_coverage`; uncovered or
unevaluable scope is also emitted through `coverage_limits` and a Human Stop.
The additive input contract is defined by
`schemas/materiality_policy.schema.json`; the corresponding output extension
is defined by `schemas/state_transition_engine_output.schema.json`. The engine
version participates in the replay hash, so identical inputs cannot collide
across materiality-semantics revisions.

`LIMIT_CROSSING` is executable when its threshold test contains a non-empty
`limits` array. Every limit declares `limit_id`, `limit_type`, compliance
`operator`, `value`, `unit`, and `source_ref`. The `any_crossing` operator fires
only when the old and Candidate values lie on opposite compliance states and
reports `INTO_BREACH` or `OUT_OF_BREACH` with the exact limit provenance.
Missing, malformed, unit-incompatible, or non-applicable limits leave the test
unevaluable and therefore fail closed at the rule's minimum class.

### Authority routing contract

Authority routing is resolved from the versioned authority-policy input; roles
and rule IDs are not embedded in the materiality branches. Routing context is
derived from Candidate deltas, materiality-rule annotations, rule-switch
annotations, and the optional event-level `authority_change_types` array. These
tags only select applicable policy routes and never constitute an authority
act, alter a decision status, or rewrite Approved.

With `MOST_RESTRICTIVE_MATCH`, every matching rule is disclosed and the unique
highest-priority rule is selected. No match, duplicate rule IDs, an equal
highest-priority tie, unsupported criteria, or an incomplete selected action
fails closed with `STOP-AUTHORITY-ROUTING`; the engine never falls through to a
less restrictive rule. This transition stage treats delegation as unproven, so
the policy's escalation role is used where required.

The additive authority input contract is
`schemas/authority_policy.schema.json`. Event routing tags are defined in
`schemas/state_transition_event.schema.json`, and rule-switch tags in
`schemas/state_transition_execution_mapping.schema.json`. Every transition
output now includes `authority_resolution`, containing the deterministic
context, all matched rule IDs, selected priority and action modes, or the exact
fail-closed reason. Its required shape is defined by
`schemas/state_transition_engine_output.schema.json` and is also compared by
the incremental/global oracle.

The Financial Gold formula set now runs end to end: 11,371 scalar formulas,
five dated-cash-flow builders and five XIRR evaluators. Residual Gold coverage
limits are preserved from the source mapping; three reachable downstream
alias/check nodes still have no executable rule and therefore keep the tested
Candidate partial.

Run the executable suite with:

```bash
python3 -m unittest discover -s tests -v
```

### Case Journal contract

`GET /api/v20/cases/{case_id}/journal` exposes one read-only history across the
runtime ledger, institutional vault events, and immutable Current graph
versions. Every normalized event carries `effective_date`, `known_at`,
server-owned `recorded_at`, and an explicit actor (legacy records without one
are visibly attributed to `PANTA_SYSTEM`). The runtime ledger adds sequence and
SHA-256 chain fields, and a corrupt chain makes the endpoint fail closed.

The endpoint accepts `since`, `until`, `as_of_date`, `workstream`, and `kind`
filters. `baseline_state_id` and `current_state_id` select an exact graph delta;
without them, `since` selects the latest Current known at that cutoff and the
current side resolves to the latest eligible Current. `close_state_id` is
required to compute post-close drift, so a normal current-state change cannot
be mistaken for drift from an implicit close date. The response contract is
defined in `schemas/case_journal.schema.json` and the deterministic direction
rules are versioned as `journal-change-rules/1.1`. Version 1.1 fails closed on
missing or duplicate graph identities, ignores audited serialization metadata
when computing semantic hashes, evaluates every status dimension independently,
and never treats disappearance of an unresolved item as proof of resolution.
Canonical relationship endpoints form compound identities, so legacy shortened
edge IDs cannot silently collapse distinct graph relationships.

Settlement uses `settlement_journal.json` as a durable outbox: Current is
committed, its `CASE_SETTLED` ledger event is appended idempotently, and only
then is the recovery marker removed. Retrying an interrupted settlement repairs
the ledger row without adopting the Candidate twice.
