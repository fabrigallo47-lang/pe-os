# Simulated versus Connected

## Embedded demo

The embedded demo is designed to communicate the product experience without requiring a server. It includes synthetic fund situations and two Keystone treatment scenes. It simulates external execution and local persistence.

The demo is not a statement that every displayed value is a validated Keystone Real output. Its purpose is to demonstrate the complete interaction contract.

## Connected mode

Connected mode loads Fund and Deal projections from the API and calls the API for event admission, transition, settlement and replay. The same interface is used; only the source of state changes.

## Reference backend files

`fixtures/backend_reference/` contains the latest raw files provided during development. They are preserved so Anto and Fabri can build adapters against the exact artifacts they produced. They are not loaded by the V17 demo because prior review identified unresolved schema and semantic issues.

## Production requirement

Before any connected pilot, the backend bundle must pass:

- frozen event, execution-mapping, Live Case and engine-output schemas;
- semantic invariants;
- financial gold tolerances;
- policy and authority tests;
- incremental/global equivalence;
- provenance and replay integrity.
