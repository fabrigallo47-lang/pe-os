# Kernel Alignment — V4 FINAL

## Non-negotiable rule

The frontend does **not** define PANTA's ontology.

Authority order is declared in `15_TARGET_CONTRACT_MANIFEST.md`: existing versioned runtime contracts/conformance tests remain binding until migration; the target design interface is `panta.universal_investment_kernel@0.1.0` plus `panta.relation_and_update_contract@0.1.0`; `src/types/domain.ts` is only the UI projection of that interface.

## Canonical nouns

The frontend projection uses the kernel's production identities where it addresses kernel objects:

`Case · Actor · Source · SourceVersion · Claim · MetricDefinition · MetricObservation · Question · Unknown · HumanPosition · CaseReading · Assumption · Risk · ModelNode · Condition · Decision · WorkItem · Artifact · Outcome`

UI-specific containers are explicitly separate:

- `Workstream` — Question Spine / archetype grouping shown to the investor;
- `Finding` — review projection over a machine proposal, not a new epistemic object;
- `Quantity` — UI projection of MetricObservation / ModelNode;
- `ArtifactBlock` — addressable artifact region;
- `CaseEvent` — ledger event projection.

This distinction prevents a room/card label from accidentally becoming backend ontology.

## HumanPosition / CaseReading boundary

`HumanPosition` is an immutable attributed view. It has actor/date/source lineage and may be Current/Approved/etc. in the institutional layer, but it carries **no system epistemic status** and PANTA never rewrites or invents it.

`CaseReading` is system synthesis for a Question. It carries computed epistemic/freshness/decision-link state and is never attributed to a human.

## State axes

V4 uses the target kernel's separate axes rather than one UI assessment enum:

- `InstitutionalState = CANDIDATE | CURRENT | APPROVED | REJECTED | RETIRED`
- `EpistemicStatus = UNEXAMINED | INSUFFICIENT | SUPPORTED | CONTESTED | INVALIDATED | STALE`
- `FreshnessStatus = CURRENT | STALE | EXPIRED | UNKNOWN`
- `QuestionStatus = OPEN | PARTIALLY_RESOLVED | RESOLVED | RISK_ACCEPTED | BLOCKED | RETIRED | STALE`
- `WorkStatus = PROPOSED | PLANNED | ACTIVE | BLOCKED | COMPLETED | CANCELLED | REOPENED`
- `ConditionStatus = PROPOSED | OPEN | SATISFIED | FAILED | WAIVED | EXPIRED | STALE`
- `DecisionLinkStatus = NO_DECISION | DECIDED | DECIDED_WITH_CONDITIONS | SUPERSEDED | BASIS_STALE`

Investor-facing terms such as “unproven”, “partial”, “weakened” or “qualified” are **display language composed from these states + relations + conditions**, never extra ontology states.

## Exact target relation vocabulary

V4 accepts only:

`ABOUT · BEARS_ON · SUPPORTS · CHALLENGES · CONTRADICTS · CORROBORATES · DERIVES_FROM · DRIVES · CONDITIONS · RESOLVES · ADOPTS · SUPERSEDES · PRODUCES`

Old frontend names such as `LIMITS`, `INFORMS`, `DERIVED_FROM`, `ANSWERS`, `FROM_SOURCE`, `ATTRIBUTED_TO`, `LOCATED_IN`, `ASSIGNED_TO` are forbidden in the relation enum.

## Ledger / replay

The append-only bitemporal ledger remains upstream of all current-state UI. `loadCase(caseId, { asOf })` requests a projection reduced from that ledger. A sparse list of case moments is only navigation; it is not history storage.

Ledger event projections keep `effectiveAt`, `knownAt`, and `recordedAt` separate.

## What this alignment proves — and does not prove

The static kernel gate proves frontend vocabulary/axes do not fork the target design contract. Runtime truth still belongs to the backend/kernel implementation and existing versioned conformance suite.

The shipped synthetic behavior test proves the adapter interface can execute the core UI loop deterministically. It does **not** substitute for the real kernel/runtime conformance tests.
