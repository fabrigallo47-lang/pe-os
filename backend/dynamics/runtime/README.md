# PANTA runtime

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
- Current/Approved governance routing and separation of duties;
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

The Financial Gold formula set now runs end to end: 11,371 scalar formulas,
five dated-cash-flow builders and five XIRR evaluators. Residual Gold coverage
limits are preserved from the source mapping; three reachable downstream
alias/check nodes still have no executable rule and therefore keep the tested
Candidate partial.

Run the executable suite with:

```bash
python3 -m unittest discover -s tests -v
```
