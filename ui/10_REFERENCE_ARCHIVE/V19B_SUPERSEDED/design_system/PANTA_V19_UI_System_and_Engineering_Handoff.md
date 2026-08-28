# UI System & Engineering Handoff

Design rules, data contracts, API surface, ownership boundaries and acceptance criteria.

**Release:** V19.0.0  
**Date:** 27 August 2026

## 1. Engineering premise

The frontend projects validated state. It does not compute financial truth, decide materiality, invent authority or generate institutional state.

sources / compiler -> validated frontend projection; admitted event + mapping + policy -> Transition Engine; server-gated authority and settlement -> canonical result projection.

## 2. Active code map

| Path | Responsibility |
| --- | --- |
| 01_PRODUCT_BUILD/app/src/store.js | UI state only: view, filters, focus, active run, selected changes. |
| engine.js | Actions and orchestration; all writes cross the adapter. |
| api.js | Connected/Mock/Offline adapters and granular API calls. |
| render.js | Region-keyed projection rendering and interaction binding. |
| contracts.js | Runtime boundary validation. |
| mock_api/server.py | Stateful synthetic reference implementation and regression harness. |
| fixtures/PROJECT-* | External demo data; never imported by Connected core. |

## 3. Required frontend projection

| Field | Purpose |
| --- | --- |
| context | Mode, action capability, actor, authority, projection/as-of/run identifiers. |
| fund | Situations, Morning Delta and available attention objects. |
| deal.question_spine | Decision-bearing questions. |
| deal.claims | Statements with locator, semantic identity and bears_on bindings. |
| deal.source_center | Inbox, sources, jobs/coverage and pipeline issues. |
| deal.cells | Workbook objects, formula, precedents and dependents. |
| deal.rooms | Foundations, Unknowns, Pipeline Review and Shadow IC. |
| deal.artifacts | Source and governed artifact versions. |
| events | Reviewable source arrivals. |

## 4. API surface

| Route family | Purpose |
| --- | --- |
| GET /bootstrap, /cases/{id}/projection | Case discovery and validated projection. |
| POST /cases/{id}/ingest; GET /jobs/{id} | Asynchronous source ingestion and progress. |
| GET /sources, /claims/{id}, /questions/{id}, /cells/{id} | Granular source and object inspection. |
| GET /coverage, /bindings, /compiler-report | Compiler observability and grounding. |
| POST /notes, /claim-reviews, /open-deal, /ic-record | Human and institutional write paths. |
| POST /events/{id}/admit | Candidate run creation. |
| POST /runs/{id}/prepare, /authority/attest | Change selection and authority. |
| POST /execution-packages/{id}/send | Server-acknowledged simulated/real delivery. |
| POST /runs/{id}/settle | Invariant-gated canonical settlement. |
| GET /replay | Read-only as-of reconstruction. |

## 5. Interaction implementation

- Render only changed shell regions; do not replace the application root on every state mutation.
- Capture and restore focus/scroll when a changed region is patched.
- Use explicit loading, empty, partial, unsupported, permission and failure states.
- Use one global as_of_state_id.
- Abort or ignore stale responses by request channel/run ID.
- Do not show optimistic success.

## 6. Design system

| Token family | Rule |
| --- | --- |
| Typography | Operational text 14-16px; important metadata >=12px; compact labels >=10px. |
| Color | Cyan Current/live, violet Working/scenario, amber stale/threshold, red blocked/fail, gold authority. |
| Density | Dense command center, but progressive disclosure before type-size reduction. |
| Motion | Reveal, Bind, Ripple, Branch, Route, Attest, Settle; motion communicates state, not decoration. |
| Targets | Primary controls 40-44px; visible keyboard focus. |
| Responsive | Full shell >=1440; overlay rails 1024-1439; drawers 768-1023; read/review <768. |

## 7. Ownership boundaries

| Owner | Produces | Must not produce |
| --- | --- | --- |
| Fabri / compiler | Sources, claims, semantic identities, question bindings, cells, coverage, Current projection | Candidate consequences or authority. |
| Anto / runtime | Affected set, recomputation, dispositions, Human Stops, Candidate, transition output | Source interpretation or frontend display logic. |
| Policy/authority service | Materiality, admissible courses, authority records, execution/settlement invariants | Evidence extraction. |
| Frontend | Validated projection, inspection, explicit selections, accessible interactions | Causal, financial or institutional truth. |

## 8. Acceptance checklist

- Connected core runs with fixture folders removed.
- A second case loads without frontend edits.
- All 44 Fabri audit findings are regression-tested.
- No source enters the projection before job completion.
- Claims are inspectable and reviewable.
- Authority and execution are impossible outside a valid run.
- Settlement is idempotent and state-coherent.
- No page clipping at target widths.
- Keyboard and reduced-motion paths pass.
