# Integration Handoff

## Purpose

This package removes the remaining ambiguity between the frontend, Fabri's compiler and Anto's Transition Engine. The frontend has one job: project state and collect explicit user actions. It must not duplicate compiler or runtime logic.

## End-to-end contract

### 1. Compiler bundle

Fabri provides:

- Current Live Investment Case;
- admitted claims and provenance;
- Case Positions and support routes;
- position dependencies;
- model nodes and position-model bindings;
- execution mapping;
- admission manifest;
- pending proposed/admitted events;
- coverage limits.

The frontend may receive a purpose-built `frontend_projection`, or a compiler bundle that `projection_adapter.js` normalizes. A production projection should be generated server-side from validated state.

### 2. Professional admission

The frontend displays the exact source passage and proposed treatment. The user's confirmation creates or admits an event. The event sent to the runtime must validate against the frozen event schema.

### 3. Transition runtime

Anto receives:

`Prior State + Admitted Event + Execution Mapping + Policy`

He returns the frozen Transition Engine output, including:

- affected set;
- ordered transitions;
- recomputed values;
- unchanged objects and reasons;
- rule switches and solver results;
- human stops;
- blocked components;
- coverage limits;
- Candidate/Current/Approved delta;
- artifact change sets;
- settlement status;
- replay hash.

The browser maps the output to the V17 transition projection. It does not recompute formulas or decide whether an object Falls, Survives, Recomputes or requires a Human.

### 4. Decision and settlement

When a human stop exists, V17 opens Decision Room using the authority request returned by policy. An attested course becomes an authority record. Anto's settlement endpoint determines what can become Current and whether Approved changes.

### 5. Replay

Replay is requested by case and bitemporal timestamp or snapshot identifier. The response must preserve what was known, believed, approved and open at that point.

## Browser files

- `app/src/integration.js`: API/demo mode boundary;
- `app/src/projection_adapter.js`: pure mapping functions;
- `app/src/engine.js`: UI state machine and explicit user actions;
- `app/src/render.js`: product surfaces;
- `app/src/selftest.js`: structural checks;
- `app/src/demo_controller.js`: deterministic demo sequence.

## Modes

- `?mode=demo`: embedded synthetic data and simulated external actions;
- `?mode=auto`: API first, fixture fallback;
- `?mode=connected`: API required;
- `?api=http://host:port/api/v1`: custom API base.

## Integration sequence

1. Run `START_PANTA.command` and confirm connected-mode rendering.
2. Replace mock projection with the validated compiler projection.
3. Replace mock transition endpoint with Anto's runtime output.
4. Validate all payloads against frozen schemas and V17 projection schemas.
5. Run the acceptance suite in `tests/`.
6. Record a connected-mode demo using the same script as the included synthetic video.
