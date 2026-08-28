# PANTA V19.B API Reference

Base path: `/api/v19`

The bundled implementation is a stateful synthetic **Mock Connected** reference API. It refuses `CONNECTED` mode rather than returning fixture-backed data.

## Projection and discovery

- `GET /bootstrap?case_id=&actor=&mode=`
- `POST /sessions`
- `GET /cases/{case_id}/projection?session_id=&as_of_date=`
- `GET /cases/{case_id}/search?q=&session_id=`
- `GET /cases/{case_id}/objects/{object_id}?session_id=&as_of_date=`

`as_of_date` is the bitemporal knowledge cutoff. The response excludes records whose `known_at` is later than that date.

## Sources and compiler

- `POST /cases/{case_id}/ingest?session_id=` -> `202` plus typed job
- `GET /jobs/{job_id}?session_id=`
- `GET /cases/{case_id}/inbox?session_id=`
- `GET /cases/{case_id}/sources?session_id=`
- `POST /cases/{case_id}/sources/{source_id}/remove?session_id=`
- `GET /cases/{case_id}/claims/{claim_id}?session_id=`
- `GET /cases/{case_id}/questions/{question_id}?session_id=`
- `GET /cases/{case_id}/cells/{cell_id}?session_id=`
- `GET /cases/{case_id}/coverage?session_id=`
- `GET /cases/{case_id}/bindings?session_id=`
- `GET /cases/{case_id}/compiler-report?session_id=`

Every created source, source version, claim and Registry event carries `effective_date` and `known_at`.

## Human and institutional inputs

- `POST /cases/{case_id}/notes?session_id=`
- `POST /open-deal`
- `POST /cases/{case_id}/ic-record?session_id=`
- `POST /cases/{case_id}/work-items/{work_id}/prepare?session_id=`

Claim review uses the typed `claim_review` payload through the notes route in the bundled reference API. A production Case Store may expose a dedicated route while preserving the schema.

## Transition, authority and settlement

- `POST /cases/{case_id}/events/{event_id}/admit?session_id=`
- `POST /runs/{run_id}/prepare?session_id=`
- `POST /runs/{run_id}/authority/attest?session_id=`
- `POST /execution-packages/{package_id}/send?session_id=`
- `POST /runs/{run_id}/settle?session_id=`
- `GET /cases/{case_id}/replay?session_id=&event_id=`
- `GET /cases/{case_id}/replay?session_id=&as_of_date=`

### Authority invariants

Authority requires:

- an existing run in `PREPARED` state;
- exact run and Candidate binding;
- an open Human Stop from that transition;
- an admissible course;
- sufficient server-side actor authority;
- a prepared artifact hash;
- a unique, payload-consistent idempotency key.

### Settlement invariants

Settlement requires:

- the same current run and Candidate;
- explicit selected changes equal to the prepared set;
- every selected change to exist in the transition output;
- scoped authority records for all Human Stops;
- accepted, scoped execution acknowledgment for an external effect;
- explicit bounded partial settlement when blocked components remain;
- a payload-consistent idempotency key.

The server returns the full canonical result projection. The browser does not invent Current state.

## Replay contract

Replay is read-only and derived from Registry events. Each response resolves to:

- one exact `event_id`;
- `effective_date`;
- `known_at`;
- source and result state identifiers where present;
- a stable event hash;
- a projection rendered as known on the requested date.

Replay never appends a new institutional event.

## Idempotency and errors

All mutating routes require an idempotency key. Reusing a key with a different payload is rejected. Errors are structured and Connected mode never falls back to fixture data.
