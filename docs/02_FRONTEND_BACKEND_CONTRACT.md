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

The optional `simulationScope` projection uses `simulation/1.0`. Numeric
`SimulationRequest` fields add `value`, `caseVersion` and `scopeVersion` to the
existing option/origin contract. The authenticated `/simulations` endpoint
returns exact numeric magnitudes and explicit limitations. `CHANGES` is neutral
UI impact language, not a new kernel state. Older qualitative adapters retain
their original interface. See `PAN-132_SIMULATION_ACCEPTANCE.md` for the
supported executable perimeter and acceptance boundaries.

## Commands

Commands express user intent; the backend translates allowed commands into authoritative canonical events/relations under current runtime contracts. The frontend does not prescribe raw ledger mutation.


## Extended simulation modes

Simulation V1 also accepts `mode: event | inverse | compare` through the same
adapter method. Event requests carry a server-prepared `scenarioId`; inverse
requests carry output/target/input bounds; comparisons pin both cases/scopes
and pass a percentage shock. Peer credentials are injected only by the transport.
`simulationScenarios` and `simulationEventLimits` are read projections over
admitted ledger evidence and explicit execution rules. Event scenario archives
retain frozen evidence/model/result envelopes; no hypothetical changes Current.
The production entry now obtains server-issued sessions through V20 bootstrap.
Detailed field requirements, comparison identity and solver boundaries are in
`PAN-132_SIMULATION_ACCEPTANCE.md`.

### General graph simulation projection

The simulation GET can expose `graphSimulationScope`, `graphSimulationScenarios`
and event limits, or an explicit `graphSimulationUnavailable` reason. The scope
catalog projects existing runtime objects and fields; it does not extend kernel
ObjectKind. POST modes `graph` and `graph_event` require `caseVersion` and
`graphVersion`. The manual body supplies only declared mutations; the event body
supplies `eventId` and `eventHash` for a server-owned admitted event. The graph
version pins full prior state, mapping, both policies and engine version.

`SimulationResult.graph` contains changed/held rows with an independent unresolved
flag, actual Current/hypothetical edges, witness labels, runtime stops, evaluated
baseline support and the full transition result. Counts of unresolved items may
overlap changed items. Frontend validation checks case, mode, versions, requested
mutations, executed event, object references and coverage counts. No simulation
result replaces the live snapshot. The authenticated immutable archive freezes
`transitionInputs`, evidence and result for reproducibility. See
`docs/PAN-111_GRAPH_SIMULATION_ACCEPTANCE.md` for runtime/authority boundaries and
verification.

### Text-to-scenario proposal

An optional `proposeSimulation` adapter method calls the authenticated simulation
`/propose` subroute with `text`, `caseVersion`, `graphVersion`. The GET projection
advertises `simulationTextInput` (GUIDED/ASSISTED and case-derived examples).
`SimulationProposal` is a disposable interpretation, never a kernel event. Its
items resolve to current canonical objects and include validated mutations,
source-text quotes, before/after values and rationale. Questions keep a partial
proposal in NEEDS_CLARIFICATION. Creating a proposal never executes the transition.
The frontend validates scope, description, references and readiness, then an
explicit review action sends mutations to the existing graph POST. That request's
`assumption` preserves the reviewed text in the immutable scenario archive.
