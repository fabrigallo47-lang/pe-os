# Engine Output to Frontend Projection Mapping - V20

## Purpose

This is the executable integration boundary between Anto's frozen Transition Engine output and the PANTA V20 frontend transition projection. V20 preserves the V19.B mapping contract and adds venture/deep-tech samples; it does not alter the engine's causal semantics.

## Field accounting

The frozen runtime output requires 18 fields:

1. `schema_version`
2. `engine_version`
3. `run_id`
4. `case_id`
5. `prior_state_id`
6. `policy_refs`
7. `affected_set`
8. `ordered_transitions`
9. `rule_switches`
10. `recomputed_values`
11. `unchanged_objects`
12. `human_stops`
13. `blocked_components`
14. `coverage_limits`
15. `invariant_checks`
16. `candidate_current_approved_delta`
17. `partial_settlement_status`
18. `replay_hash`

PANTA requires one additional integration-binding field:

19. `source_event_id`

This binds the transition result to the admitted event without extending or replacing the frozen engine contract.

## Implementations

- Python mapper: `adapters/transition_runtime_adapter.py`
- Browser mapper: `01_PRODUCT_BUILD/app/src/projection_adapter.js`
- Buyout/growth sample: `samples/sample_engine_output.json`
- Venture sample: `samples/sample_venture_engine_output.json`
- Mapped samples: `samples/sample_frontend_transition.json` and `samples/sample_venture_frontend_transition.json`
- Schema: `schemas/transition_result.schema.json`

## Purity rule

The mapper is a pure deterministic function:

`engine output -> normalized frontend transition`

It may preserve fields, normalize stable ordering, and add display aliases directly derivable from explicit engine values. It may not calculate economics, invent an affected object, infer materiality, create or close a Human Stop, decide authority, create an execution package, settle state, reconstruct history, or mutate the input.

## V20 venture objects

V20 exercises both characteristic transition outcomes in a venture case:

- a populated `human_stops` collection for a material technical discrepancy;
- a populated `blocked_components` collection for maintenance economics that cannot be transferred from the observed deployment environment.

These objects originate in the fixture/runtime output and pass through the same adapter used for Keystone and Orion. The frontend does not fabricate them.

## Validation result

The packaged buyout/growth and venture samples map deterministically and validate at zero errors against `transition_result.schema.json`. The V20 acceptance suite also exercises Human Stop settlement refusal, blocked-scope partial settlement, run/Candidate scoping and idempotency conflicts.
