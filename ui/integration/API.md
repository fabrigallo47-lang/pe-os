# PANTA V17 local/API contract

The browser integration layer is `app/src/integration.js`. It supports:

- `demo`: embedded synthetic fixtures, no server;
- `auto`: tries the API and falls back to embedded fixtures;
- `connected`: API failure is surfaced as an error.

Use `?mode=connected&api=http://127.0.0.1:4177/api/v1`.

## Endpoints

### `GET /api/v1/bootstrap`
Returns API/package capabilities.

### `GET /api/v1/cases/{case_id}/projection`
Returns `{ "frontend_projection": ... }` or a raw compiler bundle consumable by
`PantaProjectionAdapter.frontendProjectionFromBackend()`.

### `GET /api/v1/cases/{case_id}/pending-events`
Returns admitted/reviewable events.

### `POST /api/v1/cases/{case_id}/events/{event_id}/admit`
Body: `{}` in the mock. In production, include the professional treatment,
actor, admitted source/version, policy references, and attestation.
Returns the frozen Transition Engine output. The frontend maps it; it does not
invent dispositions.

### `POST /api/v1/cases/{case_id}/settle`
Body:

```json
{
  "candidate_id": "candidate-...",
  "decision": {
    "authority_record": "AR-...",
    "course_id": "COURSE-B"
  }
}
```

### `GET /api/v1/cases/{case_id}/replay?known_at={snapshot_id_or_timestamp}`
Returns the bitemporal replay projection.

## Ownership boundary

Fabri owns source decoding, semantic compilation, Current Live Case,
execution mapping, manifest, and proposed/admitted events. Anto owns Candidate,
propagation, numerical execution, policy evaluation, human stops, settlement,
and replay hash. V17 owns presentation and interaction only.
