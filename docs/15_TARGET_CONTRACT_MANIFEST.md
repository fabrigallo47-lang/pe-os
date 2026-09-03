# PANTA Frontend V4 — Target Contract Manifest

## Authority order

1. **Existing versioned runtime contracts and conformance tests remain binding until explicitly versioned/migrated.**
2. Target semantic design contract: `panta.universal_investment_kernel@0.1.0` — `DESIGN_HANDOFF`.
3. Target relation/update contract: `panta.relation_and_update_contract@0.1.0` — `DESIGN_HANDOFF`.
4. Archetype / Fund Lens / Deal Frame / Question Spine configure the case but never override kernel identity, lineage, attribution or authority rules.
5. `src/types/domain.ts` is a **frontend projection contract only**. It never defines ontology or source-of-truth semantics.

## Frozen principles represented in this frontend

- append-only ledger is source of truth;
- current state and dependency graph are derived/replayable projections;
- HumanPosition is attributed human content; CaseReading is system synthesis;
- Decision state comes only from authorized Decision events;
- Candidate objects/relations do not propagate into Current;
- affected does not mean changed; survivors remain explicit;
- propagation is bounded by typed relations / formulas / rules / authority;
- missing executable logic produces stale/review/coverage limitation, not guessed values;
- UI labels are investor-facing projections, never object identity.

## Canonical target relations

`ABOUT · BEARS_ON · SUPPORTS · CHALLENGES · CONTRADICTS · CORROBORATES · DERIVES_FROM · DRIVES · CONDITIONS · RESOLVES · ADOPTS · SUPERSEDES · PRODUCES`

## Canonical target state axes used by the UI projection

- institutional: `CANDIDATE · CURRENT · APPROVED · REJECTED · RETIRED`
- epistemic: `UNEXAMINED · INSUFFICIENT · SUPPORTED · CONTESTED · INVALIDATED · STALE`
- freshness: `CURRENT · STALE · EXPIRED · UNKNOWN`
- question: `OPEN · PARTIALLY_RESOLVED · RESOLVED · RISK_ACCEPTED · BLOCKED · RETIRED · STALE`
- work: `PROPOSED · PLANNED · ACTIVE · BLOCKED · COMPLETED · CANCELLED · REOPENED`
- condition: `PROPOSED · OPEN · SATISFIED · FAILED · WAIVED · EXPIRED · STALE`
- decision-link: `NO_DECISION · DECIDED · DECIDED_WITH_CONDITIONS · SUPERSEDED · BASIS_STALE`

## Important projection-only names

`Workstream`, `Finding`, `Quantity`, `ArtifactBlock` and `CaseEvent` are UI/runtime projection conveniences. They are not new universal-kernel ontology objects.

- Workstream = grouping/projection over active Question Spine / archetype structure.
- Finding = review projection over a machine-proposed object/relation/reading change.
- Quantity = UI view over MetricObservation / ModelNode.
- ArtifactBlock = addressable UI region of an Artifact version.
- CaseEvent = UI view of ledger events.
