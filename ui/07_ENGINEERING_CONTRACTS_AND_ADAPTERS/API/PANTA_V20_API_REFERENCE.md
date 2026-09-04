---
title: "PANTA V20 API Reference"
author: "PANTA Product and Engineering"
date: "27 August 2026"
lang: en-GB
geometry: margin=0.78in
fontsize: 10pt
colorlinks: true
linkcolor: blue
urlcolor: blue
toc: true
toc-depth: 2
numbersections: true
---

# Runtime identity

- **Base path:** `/api/v20`
- **Legacy alias:** `/api/v19` remains accepted for inherited clients. V20 clients use `/api/v20`.
- **Packaged runtime:** stateful synthetic Mock Connected; no external effects.
- **Connected behavior:** the packaged server refuses `CONNECTED` rather than serving a fixture under a live label.

# Bootstrap and projection

## Create or resume a session

`GET /bootstrap?mode={mode}&case_id={case_id}&actor={actor}`

Creates or resumes a namespaced session, returns the available cases, the validated projection and the Experience Context Envelope.

## Read the bitemporal projection

`GET /cases/{case_id}/projection?session_id={session_id}&as_of_date={date}&lens_id={lens_id}`

Returns the complete page-wide projection as known at the requested date. `lens_id` may change ranking, emphasis and policy requirements; it must not change the underlying facts hash.

## Search and resolve objects

- `GET /cases/{case_id}/search?q={query}` searches the loaded projection.
- `GET /cases/{case_id}/objects/{object_id}` resolves a generic projection object for Object Aperture.
- `GET /cases/{case_id}/replay?event_id={event_id}&as_of_date={date}` returns event-derived read-only replay.

## Read the Case Journal

`GET /cases/{case_id}/journal?since={date}&until={date}&as_of_date={date}&workstream={id}&kind={kind}`

Returns the canonical event timeline plus a deterministic graph delta. Each
event exposes `effective_date`, `known_at`, server-owned `recorded_at`, actor,
object/workstream correlations and integrity metadata. `baseline_state_id` and
`current_state_id` select exact immutable Current snapshots. `close_state_id`
enables post-close drift; without an explicit close state drift is reported as
unavailable. A corrupt runtime-ledger hash chain returns `409` rather than a
partial Journal. Change summaries use `journal-change-rules/1.1`: malformed or
duplicate graph identities also return `409`, audit-only metadata is excluded
from semantic hashes, and disappearance alone never proves that an unresolved
item was closed.

# Source and compiler routes

## Intake and jobs

- `POST /cases/{case_id}/ingest` queues file, local-path or URL intake.
- `GET /jobs/{job_id}` polls the compiler job and returns the completed projection when available.

## Source and semantic collections

- `GET /cases/{case_id}/sources` returns Source Library records and immutable versions.
- `GET /cases/{case_id}/inbox` returns Vault Inbox arrivals.
- `GET /cases/{case_id}/claims` returns claims and exact locators.
- `GET /cases/{case_id}/questions` returns the governed question spine.
- `GET /cases/{case_id}/cells` returns inspectable workbook cells and formulas.
- `GET /cases/{case_id}/coverage` returns coverage limits and pipeline issues.
- `GET /cases/{case_id}/bindings` returns claim-question and position-model bindings.
- `GET /cases/{case_id}/compiler-report` returns compiler counts, versions and projection hash.

## Compiler proposals

`GET /cases/{case_id}/compiler-proposals`

Returns candidate discrepancies, deterministic derivations, AI hypotheses and spine-change proposals. These are proposals rather than admitted institutional truth.

`POST /cases/{case_id}/compiler-proposals/{kind}/{proposal_id}/review`

Records the professional disposition for one proposal. `kind` is `discrepancy`, `derivation`, `hypothesis` or `spine`.

# Governed missions

## Prepare a mission

`POST /cases/{case_id}/missions/{mission_id}/prepare`

Creates a no-effect mission draft with objective, permitted and prohibited sources, confidentiality policy, data-egress policy, stop condition, reviewer and authority class.

## Run a policy-safe mission

`POST /cases/{case_id}/missions/{mission_id}/run`

The packaged reference runtime runs only policy-safe synthetic mission classes. Human-contact, physical-test and non-auto missions return `MISSION_AUTHORITY_REQUIRED`. Results enter as a new synthetic source and review-required claim; they are never silently admitted.

# Admission and transition

## Admit a professional treatment

`POST /cases/{case_id}/events/{event_id}/admit`

Requires treatment ID and hash, source version, actor, as-of context, both temporal dates and idempotency key. A successful admission creates the server-side run and Candidate.

## Prepare selected changes

`POST /runs/{run_id}/prepare`

Requires explicit valid change IDs. Zero selection and any ID outside the transition's affected set are rejected.

# Authority, execution and settlement

## Attest an admissible course

`POST /runs/{run_id}/authority/attest`

Creates a scoped authority record. `actor_id` remains mandatory for an explicit, backward-compatible request, but it is not an identity credential. The request must carry the opaque session returned by bootstrap in `X-Panta-Session`; `session_id` in the query remains accepted for compatibility, and both values must match when both are present. The server resolves the principal from its own expiring session registry and rejects a missing, unknown, expired, cross-case or actor-mismatched session before recording authority.

The server then verifies the prepared selection, run, Candidate, normalized Human Stop, admissible course, server-owned actor assignment, role, authority verb, independence constraint, replay artifact hash and idempotency semantics. The output envelope is unchanged. Its `authority_record/2.0` now binds `case_id`, `authentication_context` and `authentication_context_hash` in addition to the Human Stop, policy references, selected authority resolution and bitemporal authority assignment. The authentication context contains the principal, method, session digest and validity interval; the raw bearer token is never persisted or returned in the record. It also includes signature metadata and the append-only ledger sequence/previous-hash link. Connected mode signs with Ed25519 and verifies `signing_key_id` against a versioned public-key keyring, so retired keys remain available for historical verification while unknown, post-retirement and effectively revoked keys fail closed. Mock Connected emits the same record contract with `SYNTHETIC-HMAC-SHA256` and `SYNTHETIC_SERVER_SESSION`, explicitly limited to the synthetic session. Correction-only, unresolved-policy and non-waivable stops are not attestable.

Unsigned authority records from earlier contract versions fail closed. They require explicit migration or a new attestation; the API does not silently rewrite historical acts.

## Deliver an execution package

`POST /execution-packages/{package_id}/send`

Returns synthetic server acknowledgment or failure. No success appears before the response. A `DEFER` course creates no executable package.

## Settle canonical state

`POST /runs/{run_id}/settle`

Validates selected changes, Human Stops, the authority-ledger hash chain, every record signature and historical authority snapshot, course-specific execution acknowledgment, blocked scope and partial-settlement boundaries. Reference arrays accept unique, non-empty string IDs only. The server returns the canonical Current state, Registry event and replay identity. The browser does not invent the result.

# Other governed write routes

- `POST /cases/{case_id}/open-deal` records structured case opening.
- `POST /cases/{case_id}/notes` records a professional annotation or review note.
- `POST /cases/{case_id}/ic-record` records an institutional IC act.
- `POST /cases/{case_id}/sources/{source_id}/remove` retires a source from Current while preserving history.
- `POST /cases/{case_id}/work-items/{work_item_id}/prepare` creates an internal work draft without claiming external dispatch.

# Mode honesty and production boundary

A bootstrap request with `mode=CONNECTED` receives HTTP 503 and `CONNECTED_BACKEND_NOT_CONFIGURED`. The packaged server never serves fixture data under the Connected label.

The API is a synthetic reference implementation. It does not claim production SSO/RBAC, tenant-aware persistence, a live research service, external delivery, Fabrizio's production compiler/Case Store or Anto's independently deployed production runtime.
