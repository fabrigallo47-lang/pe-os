# Graph simulation V1 — 5 September 2026

Simulate now defaults to **Case changes**. An investor can combine qualitative,
quantitative and structural changes and inspect what the real state-transition
engine produces on an isolated copy of Current. **Financial sensitivities**
retains the numeric scenarios, thresholds and comparisons documented in
`PAN-132_SIMULATION_ACCEPTANCE.md`.

Within Case changes, **Describe a change** is the default input. Text proposals,
explicit review and execution, optional case references and English examples
are documented in [`SIMULATION_TEXT_INPUT_ACCEPTANCE.md`](SIMULATION_TEXT_INPUT_ACCEPTANCE.md).

## Visual presentation

Results use a dedicated simulation graph over actual case relationships.
**Current connections** and **Hypothetical connections** switch the displayed
edges; directly changed, changed, held and unresolved nodes remain inspectable.
The accompanying table shows field/value/support differences, and selecting a
node opens both states, the relevant evidence paths and recorded reasons. This
is a simulation comparison view, not a replacement of the live case graph.

## Delivered behavior

- A server-owned catalog declares the current objects, editable fields,
  evidence connections and protected attributed views before the run.
- One scenario accepts up to 50 changes: withdraw an existing item or evidence
  path; change usability, freshness, wording, model values or declared context;
  change the members, counterevidence and combination logic of an existing
  evidence path; add temporary hypothetical evidence linked to a conclusion.
- A batch runs once through `apply_state_transition`, using the complete prior
  runtime state, execution mapping, materiality policy and authority policy.
  There is no separate qualitative evaluator in the simulation adapter or UI.
- Results include the actual before/after connections, directly changed and
  reached items, changed values/fields/support, held items, independent surviving
  support, unresolved results, blocked components and required human reviews.
  A changed object can also be unresolved; this is counted and labelled.
- Every displayed node, including alternative support outside the affected set,
  can be inspected. The inspector separates stored Current from the hypothetical
  and exposes exact evidence paths, support calculations and provenance.
- Admitted ledger events automatically prepare graph scenarios on case
  load/refresh. Their recorded identity, evidence, dates and payload are retained.
  Existing numeric claim-to-input event rules are not required for graph events.
- Authenticated POST requests pin the exact case and graph version. That graph
  digest includes the entire runtime state, policies, mapping and engine version.
  Caller-supplied state, policies, authors, arbitrary event envelopes and
  decision edits are rejected. A split projection/runtime read fails closed.
- Both requested and event scenarios are archived separately from the case
  ledger. The immutable envelope retains all transition inputs, evidence and the
  complete engine result. It can be replayed after Current or policies change.
- Reset, refresh, case switch and workspace switch clear obsolete results.

## Existing engine corrections

Engine `0.10.1-conformance` fixes two defects exposed by graph acceptance:

1. A withdrawn support route is false even when its original members remain
   usable, in both initial evaluation and freshness reconciliation.
2. A downstream route consumes the recomputed support of an upstream conclusion,
   rather than using the conclusion's unchanged recorded decision as proof.
   Human decisions and attribution remain unchanged.

The output schema remains `transition-output-1.0`. The simulation projection is
`graph-simulation/1.0`, inside the existing `simulation/1.0` response envelope.

## Runtime and authority boundaries

The V1 executes changes supported by the existing transition contract. It is
not an unrestricted graph authoring system or a prose-to-causal-model service.
New hypothetical Claims are supported; inventing new Position/ModelNode/
SupportRoute types or rewriting attributed human views is not. Structural
changes use existing route membership and logic. The UI does not offer an
unsupported arbitrary edge or route-target rewrite.

Changing prose does not infer new assumptions or executable relationships.
An added claim with only a conclusion link and no declared route membership
explicitly reports that limit. Missing logic, stale inputs, contradictory
support, unsupported calculations and incomplete significance rules stay visible.
Current support is a separately labelled engine evaluation, not a silently
corrected stored baseline. Raw Current and the complete candidate output remain
available for inspection.

The wrapper never settles a candidate, appends institutional history, adopts
Current, alters Approved or writes an attributed human record. The engine may
propose governance actions in its output; those remain hypothetical. Only the
separate immutable scenario archive is written. Event preparation occurs on
load/refresh, not in an installed background scheduler. Events already reflected
in Current can honestly produce no further change.

Production uses the actual case bootstrap/session registry and compiled bundle,
including `runtime_state.json` when present. A case without a complete transition
bundle exposes an unavailable reason. Deployment is outside this implementation.

## Verification

- `backend/dynamics/tests/test_graph_simulation.py`: **20 tests**, including full
  result equality with a separately invoked `apply_state_transition`, independent
  support survival, multi-level support loss, route retraction, replacement
  connections, conflict, new counterevidence, mixed numeric/qualitative changes,
  wording limitations, stale/from-value stops, protected human decisions,
  complete-basis version checks, request bounds, and incremental/global oracle
  agreement for support cascades. HTTP tests cover authorization before loading,
  immutable replay, exact event evidence pins, candidate/foreign-event exclusion,
  split-state failure, and the production bundle loader with unchanged files.
- **105 tests** pass across graph/numeric simulation, numerical queries,
  formula/execution mapping compilers, V20 dynamics integration and live outputs.
- **57 runtime regression tests** pass, including core, routes/formulas, staleness,
  materiality/governance, numerical/inverse solvers and oracle workflows.
- `tests/graph-simulation.mjs` consumes HTTP-generated real engine fixtures and
  rejects wrong case/version, fabricated graph identities, mismatched events,
  inconsistent counts and live-case mutation flags. Included in `check:all`.
- `npm run check:all` passes: production isolation/contract/behavior checks,
  transport tests, TypeScript, production build and synthetic lab build.
- Browser acceptance in `simulation.html`: one withdrawn source leaves the
  independently supported conclusion held; withdrawing both changes seven
  reached objects and removes downstream support. Node inspection distinguishes
  unchanged recorded decisions from changed computed support. Event, connection
  editing and scenario reset are exercised in the same production UI.

Synthetic fixture: `tests/graph_simulation_fixture.py`. Local acceptance server:
`.venv/bin/python tools/simulation_lab.py` on 8177; lab UI on 5180. The lab has no
live case content and does not modify production case records.

## Publication verification — 5 September 2026

The simulation commit was first verified independently of unrelated local IC
memo editorial-profile work: 174 Python tests and `npm run check:all` passed.
After integrating the latest `origin/dev`, the simulation/compiler/integration
and runtime suites plus live-evidence/bootstrap regressions passed **179 tests**;
`npm run check:all` passed on that integrated checkout as well. The existing
runtime semantic-target mapping update and both simulation support fixes are
retained together. Browser acceptance confirmed an English mixed description,
reviewed changes and the Current/hypothetical graph comparison. Live-model
interpretation remains dependent on configuration as stated in the text-input
acceptance note; this verification does not claim an unrestricted language model
evaluation or product deployment.
