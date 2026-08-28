# Connected Adapter Handoff - V20

`01_PRODUCT_BUILD/app/src/api.js` is the executable browser-side reference adapter. A production adapter must implement the same routes and return the V20 schemas. It must not import demo fixture packs, synthesize missing domain state or silently fall back.

## Transition adapter

`transition_runtime_adapter.py` is implemented. It maps the frozen 18-field Transition Engine output plus `source_event_id` into the frontend transition projection as a pure deterministic function. V20 adds a venture sample but does not change the engine's causal contract.

## Compiler projection adapter

`compiler_projection_adapter.py` is implemented as a transport-neutral pure mapping:

`validated compiler bundle + validated projection shell -> V20 frontend projection`

It maps interactions, participants, utterances, claims, sources, archetype, Lenses, discrepancy rules, derivation specifications, missions, spine-change proposals, condition edges, validation envelopes and venture-financing objects. It applies the `known_at` cutoff when requested and emits a deterministic bundle hash.

It deliberately does not:

- call an AI model;
- derive contradictions or hypotheses;
- compute investment economics;
- decide materiality or authority;
- admit proposals;
- settle institutional state;
- reconstruct events that were not supplied.

The executable sample is:

```bash
python adapters/compiler_projection_adapter.py \
  samples/sample_v20_base_projection_shell.json \
  samples/sample_v20_compiler_bundle.json \
  /tmp/panta_v20_projection.json
```

The expected mapped output is packaged as `samples/sample_v20_compiler_projection.json` and validates at zero schema errors.

## Production boundary

The bundled Mock Connected server is a stateful synthetic reference implementation. It is not Fabrizio's production compiler/Case Store, Anto's independently deployed production Transition Engine, enterprise identity, or an external execution service.

Adapters may validate, normalize and transport. They may not invent evidence, institutional acts, financial results, affected objects, materiality, authority, execution acknowledgment, settlement or historical state.
