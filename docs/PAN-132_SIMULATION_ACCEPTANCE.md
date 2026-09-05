# Numerical simulation subset — 5 September 2026

The investor can inspect the model's executable perimeter, choose a declared
numeric input, change its value, and inspect the resulting amounts and limits.
The same Simulate room runs through an authenticated HTTP adapter and the
transition runtime's Decimal evaluator. The test data is fictional; calculations
are real. No model-provider request or live deal modification is involved.

## Scope correction and completed general graph path

The earlier numeric-only completion claim was incorrect. The user clarified
that Simulate must introduce changes into the investment-case graph, including
qualitative and structural changes, and expose the real transition behavior.
That general path is now implemented and verified separately in
[`PAN-111_GRAPH_SIMULATION_ACCEPTANCE.md`](PAN-111_GRAPH_SIMULATION_ACCEPTANCE.md).
The numeric tests below establish only the financial subset; graph acceptance
uses the complete transition engine, exact result comparisons and nonmutation
checks. The default workspace is now **Case changes**.

## Delivered numerical subset

- **PAN-132 / F5.1:** versioned perimeter, current input values and semantic
  context, available calculations, and explicit missing/unsupported coverage.
- **PAN-136 / F5.2:** one numeric input shock against the exact case and model
  version the investor viewed. The caller supplies neither the case nor formulas.
- **PAN-133 / F5.3:** extends the existing impact presentation with absolute and
  relative amounts, neutral numeric change labels, unchanged affected outputs,
  and branches that could not be calculated. A larger number is not implicitly
  classified as a stronger investment case.

- **PAN-135 / F5.4:** admitted evidence events prepare atomic scenarios from
  explicitly declared claim-to-input rules on load/refresh. Each scenario
  retains event provenance and a frozen case/model basis in an immutable archive.
- **PAN-134 / F5.5:** verified inverse thresholds over user-specified intervals;
  equal-percentage sensitivity comparison between two independently authorized
  cases with explicitly compatible model definitions.

`src/main.tsx` now uses `createConnectedSimulationsAdapter`, the existing V20
bootstrap/session registry and the production simulation routes. Build with
`npm run build`; the backend serves the React workspace at `/workspace/`.
Vite development proxies `/api` to the local backend on port 8000. The same authenticated workspace now also connects the general graph path described in the graph acceptance note. This implementation does not deploy the product.

## Runtime and transport contract

`backend/dynamics/runtime/simulation.py` reads admitted Current model objects
and the case's execution mapping. It reuses `_execute_formula` from the
versioned transition engine for bounded arithmetic, compiled Decimal formulas,
and supported IF/MIN/MAX/ABS/SUM expressions. It requires explicit operands.
No formula is inferred from labels or source prose. Current values are not
replaced with old mapping initial values.

Missing model identities, numeric values or unit/period/scope, candidate
objects/formulas, inconsistent baselines, unresolved compiler coverage,
unsupported expressions and cycles remain visible limitations. Nodes outside
the mapping stay visible. Formulas must reproduce recorded Current within
absolute 1e-9 or relative 1e-9 tolerance before a hypothetical is computed.
Numeric inputs/results are bounded to absolute values at most 1e30 and, when
nonzero, at least 1e-100. Exact decimal strings are retained; display text is
rounded for legibility. A zero denominator blocks its branch rather than
returning a fabricated value. Relative movement from a zero baseline is null.

`app/simulation_routes.py` is mounted by `app/server.py` at:

- `GET /api/v20/cases/{case_id}/simulations`: authenticated projection and scope.
- `POST /api/v20/cases/{case_id}/simulations`: read-only counterfactual result.

All routes require `X-Panta-Session` and its matching `X-Panta-Actor`, verified through
the existing server session registry. Body fields are whitelisted separately for manual, event, inverse and comparison modes. Arbitrary models, formulas, events and overrides cannot be supplied by the caller. The scope digest includes both Current and the execution mapping. Stale
versions return 409; invalid or unavailable inputs return 422.

The response partitions every reached model object exactly once into changed,
held or unavailable. Formula dependencies generate inspectable relation
projections using the runtime's existing declared formula edges. Numeric
effects never adopt Current, rewrite HumanPositions or record a Decision.
Displayed results have deterministic identities and disappear on reset or setup/case changes. Manual, inverse and comparison results are ephemeral. Event scenarios are also archived independently of the case ledger; clearing their display does not erase the audit record.

The client checks case/model versions, exact decimal input identity, known
result objects and coverage totals. It does not replace the displayed case
with a hypothetical snapshot. Object Lens distinguishes Current from the
hypothetical and preserves calculation limitations.

## Verification

Passed:

```sh
npm run check:all
PYTHONPATH=backend/dynamics .venv/bin/python -m unittest \
  backend.dynamics.tests.test_simulation \
  backend.dynamics.tests.test_simulation_queries \
  backend.dynamics.tests.test_pan66_formula_compiler \
  backend.dynamics.tests.test_pan67_execution_mapping_compiler \
  backend.dynamics.tests.test_v20_dynamics_integration \
  backend.dynamics.tests.test_live_outputs -q
```

85 Python tests, including 43 simulation tests; all frontend gates, authenticated
adapter regressions, TypeScript, production build and all five lab entries.
The workbook test passes actual compiler output into the simulation, without
transcribing its formula in the simulation layer.

Browser acceptance:

1. Open the declared scope: 6 of 7 fictional model items are calculable; the
   unconfigured return solver is explicitly unavailable.
2. Change revenue from 100 to 90 EUR m: operating earnings move from 40 to 30,
   leverage from 2 to 2.6666667x; capped distribution remains 30. Three changed,
   one held and one unavailable item partition five examined items.
3. Open an amount and navigate its recorded model connections. The case value
   remains the baseline; the hypothetical is separately labelled.
4. Change revenue to 60: operating earnings become zero, and leverage becomes
   unavailable due to division by zero. The other branch still computes.
5. Reset and refresh: Current remains 100; the ephemeral result is cleared.

## Local preview

```sh
.venv/bin/python tools/simulation_lab.py
npm run lab -- --host 127.0.0.1 --port 5180
```

Open `http://127.0.0.1:5180/simulation.html`. The backend binds only to loopback
8177 and serves an isolated fictional model. `createConnectedSimulationsAdapter` uses the same bootstrap/transport contract as production and presents two fictional cases. No files
under the user's vault are changed by this workspace.


## Event admission and audit (PAN-135)

The production loader reads the verified append-only ledger using
`ledger_store.read_ledger`. `execution_mapping.json` may declare
`simulation_event_rules`, each with `rule_id`, `event_type`, `claim_id`,
`input_id`, and explicit `institutional_state` CURRENT or APPROVED. These are
execution configuration, not new kernel relations. A rule copies a point value
from that exact admitted claim mutation; it does not interpret event prose.
The event must have an admitted mode (AUTO_POLICY, HUMAN_CONFIRMED or
AUTHORITY_RECORDED), event identity, knowledge time and source identities.
The referenced claim must still be admitted, its source must belong to the
event, and unit/currency/period/perimeter/basis/scenario must match the input.

All mapped changes from one event run together. Any missing, ambiguous,
conflicting or unavailable mapped change stops the entire scenario and is
shown under that event. Unmapped or unadmitted events never fabricate shocks.
The scope remains based on the current model: an older evidence event can be
explored against a newer baseline, producing a new scenario identity. Every
historical scenario retains its original evidence, graph, mapping and result.

`PANTA_SIMULATION_DB` optionally selects the archive path (default
`vault/simulation-scenarios.sqlite3`; durable configuration required on Vercel).
SQLite uniqueness, transactions, UPDATE/DELETE rejection and content hashes
protect idempotent, immutable records. Authenticated
`GET /simulations/archive/{scenario_id}` reads the frozen envelope. The archive
is a scenario record store, not an adoption event or a rewritten case ledger.
The lab puts its archive in a temporary directory and never writes the vault.

Trigger timing: preparation occurs automatically on workspace load/refresh,
without a separate run action. This V1 does not install a background scheduler
or interpret free-text news. A new case needs its own admitted model and rules.

## Inverse question limits (PAN-134)

`mode: inverse` accepts `inverse: {outputId, target, lower, upper}` plus the
viewed case/scope versions and selected input. All other inputs stay fixed.
Outward-rounded Decimal interval arithmetic certifies continuity and a strict
single direction through the selected arithmetic formula path. Bisection then
returns a value only if the forward output residual meets max(1e-9,
abs(target)*1e-9), within 160 iterations. The forward impact trace is returned
with the solution, residual, tolerance, bounds and iteration count.

Possible division by zero, cycles, nonmonotone paths, a flat derivative, and
piecewise/function expressions such as MIN/MAX/IF remain UNSUPPORTED for this
inverse solver even when a forward simulation can evaluate them. A target
outside a certified output range is UNREACHABLE. Nonconvergence has its own
status. None of these outcomes produces fabricated impact rows or claims that
no solution exists outside the tested bounds. This is a one-variable threshold
solver, not a general optimizer or multi-root search.

## Comparison identity and access (PAN-134)

`mode: compare` applies `percent` to the selected input and its uniquely
matched counterpart. Both case versions and both model versions are pinned.
The server authenticates separate case-bound sessions before reading the peer.
The additional peer actor/session fields are transport-only and are never
included in a result or archive. Zero-baseline percentage shocks are rejected.

A node's `comparison_key` is an explicitly supplied shared definition identity
(including measurement semantics), not a match inferred from a label or local
node ID. It must be nonempty and unique within each model. Unit, currency,
period, perimeter, basis and scenario must also be explicitly present and
identical. No implicit FX, period alignment, normalization, ranking or combined
investment score is performed. Outputs without a compatible counterpart or a
valid calculation appear as exclusions, not numerical comparisons.

Rows expose both baselines, both scenario values and both relative changes,
with inspectable comparison dimensions. Local and peer traces retain their
own object identities. The peer case is navigable; switching case clears the
old result. The adapter verifies both trace versions and coverage, row-to-trace
consistency, returned inverse values and admitted-event identity.

## Additional acceptance evidence

- Event: revenue 100 → 90 and costs 60 → 65 atomically produce earnings 40 → 25
  and leverage 2 → 3.2. Five changed and one unavailable item; baseline intact.
- Inverse: revenue in [70, 100], target leverage 3, finds approximately
  86.66666668 and independently reproduces the forward result. Bounds [50, 100]
  disclose the possible pole; a piecewise capped output cannot claim uniqueness.
- Comparison: revenue -10% produces earnings -25% in Example A and -40% in
  Example B; both starts and results are visible. The unconfigured return
  calculation is excluded. Incompatible currencies/periods/definitions and
  ambiguous input matches are rejected.
- Production integration test uses the real bootstrap, issued-session registry,
  ledger reader, production router, and immutable archive in a temporary tree.
- Transport tests cover bootstrap recovery, separate peer credentials, stale
  requests, mismatched evidence, inverse/trace inconsistency and corrupt peer
  rows. The checked-in transport examples are generated by the real engine:
  `.venv/bin/python tests/build_simulation_transport_fixture.py`.
- Browser checks exercise event preparation and trace, inverse success and
  discontinuity rejection, comparison results, inspection, reset and case switch.
