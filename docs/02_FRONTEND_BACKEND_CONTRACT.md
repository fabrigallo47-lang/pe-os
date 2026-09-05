# Frontend ↔ Backend Contract — V4 FINAL

## Authority

Read `15_TARGET_CONTRACT_MANIFEST.md` first.

The frontend is a projection layer. It does not define ontology. Existing versioned runtime contracts/conformance tests remain binding until migration; the target design interface is the Universal Investment Kernel 0.1.0 + Relation/Update Contract 0.1.0.

The adapter boundary is `src/providers/PantaBackendAdapter.ts`.

## Adapter methods

- `getSession()` — current Actor + entitlements
- `listCases()`
- `loadCase(caseId, { asOf? })` — materialized case projection at that cutoff
- `listCaseMoments(caseId)` — sparse temporal navigation only
- `loadJournal(caseId, { since?, until?, asOf?, workstream?, kind?, baselineStateId?, currentStateId?, closeStateId? })` — validated `case-journal/1.0` read projection from `GET /api/v20/cases/{caseId}/journal`
- `listJournalStates(caseId)` — immutable `CURRENT` state choices from `GET /api/v20/cases/{caseId}/graph-versions`
- `inspectObject(caseId, objectId, { excludeObjectIds? })`
- `searchCase(caseId, query)` — returns objects, never chatbot prose
- `runSimulation(caseId, request)`
- `execute(caseId, PantaCommand)`

## Canonical target relations

`ABOUT, BEARS_ON, SUPPORTS, CHALLENGES, CONTRADICTS, CORROBORATES, DERIVES_FROM, DRIVES, CONDITIONS, RESOLVES, ADOPTS, SUPERSEDES, PRODUCES`.

Only relations admitted under the authoritative runtime contract may affect Dynamic traversal. The frontend never infers missing edges.

## Object Lens

The backend returns structured facts/refs only:

- support object ids;
- independently corroborating support ids;
- Unknown ids;
- dependent object ids;
- last-change event id;
- related object ids;
- source locators;
- allowed actions.

The frontend composes investor language:

**Why we believe this · Still missing · Why it matters · What changed · Where else this appears**.

The backend must not return those sections as explanatory prose.

## Replay

`loadCase(caseId, { asOf })` is the replay interface. Same ledger + same contract/configuration versions + same cutoff must reproduce the same case projection/hash. `listCaseMoments` is only a navigation aid.

## Case Journal

The adapter validates `case-journal/1.0` and `journal-change-rules/1.1` before rendering. Events preserve effective, knowledge, and server recording time plus declared or visibly inferred actor attribution. State selectors pass stable ids back to the backend; the frontend never compares case objects or infers direction locally. HTTP 409 integrity conflicts fail closed and render no partial history.

## Actor / authority

Every governed mutation uses `PantaCommand.actorId`. The frontend may disable unavailable actions for clarity; backend AuthorityPolicy is the actual security/authority boundary.

`DecisionContext.requiredEntitlement` is UI guidance, not sufficient authorization.

## HumanPosition

A HumanPosition is attributed human content. It is immutable as an utterance and carries no system epistemic status. Contradictory evidence may change a CaseReading; it never rewrites the HumanPosition.

## Quantities

The `Quantity` type is a UI projection of MetricObservation / ModelNode. Before a number can participate in comparison/simulation it must preserve enough semantic perimeter to establish identity: concept/metric, entity, period, scope/perimeter, basis, measurement, scenario, unit/currency, source and formula/assumptions where relevant.

Unknown numbers remain unknown.

## Simulation coverage

Return numeric `Coverage`:

- `examinedCount`
- `changedCount`
- `heldCount`
- `unmappedCount`

Affected does not mean changed. Survivors are explicit.

## Commands

Commands express user intent; the backend translates allowed commands into authoritative canonical events/relations under current runtime contracts. The frontend does not prescribe raw ledger mutation.
