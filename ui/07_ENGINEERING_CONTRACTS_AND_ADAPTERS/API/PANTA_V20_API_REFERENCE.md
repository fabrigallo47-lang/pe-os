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

Creates a scoped authority record. The server verifies run, Candidate, open Human Stop, course, authenticated actor, authority assignment, artifact hash and idempotency semantics. Incompatible attestations are rejected.

## Deliver an execution package

`POST /execution-packages/{package_id}/send`

Returns synthetic server acknowledgment or failure. No success appears before the response. A `DEFER` course creates no executable package.

## Settle canonical state

`POST /runs/{run_id}/settle`

Validates selected changes, Human Stops, scoped authority, course-specific execution acknowledgment, blocked scope and partial-settlement boundaries. The server returns the canonical Current state, Registry event and replay identity. The browser does not invent the result.

# Other governed write routes

- `POST /cases/{case_id}/open-deal` records structured case opening.
- `POST /cases/{case_id}/notes` records a professional annotation or review note.
- `POST /cases/{case_id}/ic-record` records an institutional IC act.
- `POST /cases/{case_id}/sources/{source_id}/remove` retires a source from Current while preserving history.
- `POST /cases/{case_id}/work-items/{work_item_id}/prepare` creates an internal work draft without claiming external dispatch.

# Mode honesty and production boundary

A bootstrap request with `mode=CONNECTED` receives HTTP 503 and `CONNECTED_BACKEND_NOT_CONFIGURED`. The packaged server never serves fixture data under the Connected label.

The API is a synthetic reference implementation. It does not claim production SSO/RBAC, tenant-aware persistence, a live research service, external delivery, Fabrizio's production compiler/Case Store or Anto's independently deployed production runtime.
