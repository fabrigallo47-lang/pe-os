# Product Experience Specification

The authoritative definition of PANTA V19: V18 product architecture plus every extractor-to-screen correction in Fabri's audit.

**Release:** V19.0.0  
**Date:** 27 August 2026

## 1. Executive premise

PANTA V19 preserves the V18 product architecture and command-center interaction grammar. The release adds the complete extractor-to-screen operating surface and closes every material finding in Fabri's V17 UI audit. It is not a redesign; it is a source, inspection, grounding, interaction and integration completion release.

PANTA V19 compiles sources into a Live Investment Case, lets professionals inspect and correct the compiler output, executes governed consequences, and preserves one coherent institutional state.

### Release intent

- Preserve V18 Fund Command, Deal Command, Object Aperture, Change Impact, Decision Room, Execution Room and Causal Replay.
- Add visible source ingestion, vault inbox, source library, claims exploration, compiler review, structured case opening and IC recording.
- Expose granular evidence, cell, question, binding, coverage and replay routes.
- Keep domain unknowns distinct from pipeline uncertainty.
- Remove the remaining visual-only and hardcoded behavior identified in the audit.

## 2. Release status and boundary

| Capability | V19 status | Meaning |
| --- | --- | --- |
| Product architecture | Specified and UI implemented | All persistent rooms, contextual overlays, transient workflows and gated rooms are present. |
| Mock integration | Stateful server-gated simulation | Ingest, review, authority, execution, settlement and replay are exercised through the public API boundary. |
| Connected integration | Contract-ready | No fixture fallback; a real compiler/Case Store/Transition Engine must provide the V19 contracts. |
| Production identity and external effects | Deferred | SSO, enterprise RBAC, real email/Excel/SharePoint writes and production persistence are not claimed. |
| Mobile authority | Intentionally unavailable | Below 768px the product is read/review-first. |

V19 is a complete product-experience and integration handoff, not a claim that production authentication or external delivery already exists.

## 3. Product architecture

V19 is one investment state projected at fund scale, deal scale, object scale and historical time. Rooms do not own separate copies of the case.

| Layer | Responsibility | Owner boundary |
| --- | --- | --- |
| Source and compiler | Native ingestion, claims, locators, question bindings, cells, coverage and compiler review | Fabri / connected compiler |
| Live Investment Case | Questions, positions, artifacts, unknowns, events, versions and Registry | Case Store |
| Transition and finance | Affected set, dispositions, recomputation, controls, Human Stops and Candidate | Anto runtime |
| Authority and settlement | Course attestation, execution package, invariant gate, Current/Approved treatment | Server-side policy and authority |
| Product experience | Projection, inspection, review, action, navigation, accessibility and error states | Frontend; never invents truth |

## 4. Source-to-screen operating model

![Diagram](/mnt/data/PANTA_V19_COMPLETE/04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/02_Extractor_to_Screen.png)

### Native source intake

The Source Center accepts an uploaded file, a server-visible path, a URL or a vault-inbox item. The server returns a job immediately. The source enters the case only after parsing, extraction, binding and validation complete.

### Professional correction loop

Claims Explorer exposes statement, value, source, locator, period, perimeter, epistemic class, question binding and review state. Professional review is written to the session Case Store and never overwrites the raw source.

### Projection refresh

Completed jobs materialize source versions, claims, inspectable workbook cells and artifacts. The frontend refreshes the validated projection rather than merging hidden defaults.

## 5. Information architecture

| Category | Surfaces |
| --- | --- |
| Portfolio orientation | Fund Command |
| Deal orientation | Deal Command |
| Source and compiler | Sources: Ingest, Vault Inbox, Source Library, Claims Explorer, Compiler Review, Case Setup and IC Record |
| Case work | Work, What the Deal Rests On, Everything We Still Do Not Know, Shadow IC, Scenario Lab, Artifacts, Registry, Causal Replay |
| Contextual overlay | Object Aperture |
| Transient workflow | Change Arrival, Change Review, Change Impact, Action Frontier |
| Gated rooms | Decision Room, Execution Room |
| Completion | Settled State |

Navigation uses the capability map returned by the projection. A room that is not supported is hidden or explicitly gated; the interface never assumes every deal exposes the same capabilities.

## 6. Source Center and compiler review

### Ingest

- File input and drag-and-drop
- Server-visible path
- URL input
- Vault Inbox ingestion
- Purpose/expected-content metadata
- Asynchronous job with stage and progress

### Claims Explorer

- Search statement, locator, value and perimeter
- Filters: epistemic, topic, period, perimeter, source, direction and author
- Sorting and explicit pagination
- Question-binding drill-down
- Professional accept/correct/reject review
- Export of the filtered result set

### Compiler Review

The room contains two registers: domain unknowns about the investment and pipeline issues about extraction, grounding or mapping. They are never mixed.

## 7. Core persistent rooms

| Room | Question answered |
| --- | --- |
| Fund Command | Where should the fund allocate attention now? |
| Deal Command | What does the institution currently believe about this case? |
| Work | What needs to be done, by whom, to close a case object? |
| What the Deal Rests On | Which minimal supports and weak floors hold the case? |
| Everything We Still Do Not Know | Which missing fact has the highest decision value? |
| Shadow IC | What are the strongest credible cases for and against? |
| Scenario Lab | How do governed alternate mechanisms change the economics? |
| Artifacts | Which file/version represents which case objects? |
| Registry | What source, system, human, authority and settlement events occurred? |
| Causal Replay | What was known, believed, approved and open at an as-of state? |

## 8. Object Aperture

Object Aperture is the universal two-gesture inspection pattern. It now has explicit branches for questions, claims, sources, workbook cells/model nodes, unknowns, artifacts, people, support sets and transition objects.

| Tab | Purpose |
| --- | --- |
| Basis | Exact source, proposition/value, definition, period, perimeter, epistemic class and current state. |
| Dependents | Question bindings, positions, model nodes, formula precedents/dependents, artifacts and coverage. |
| Action | Review, correction, closure path, assignment, export, copy and deep link. |
| History | Source versions, state changes, reviews, notes, authority and replay references. |

## 9. Change, authority and settlement

![Diagram](/mnt/data/PANTA_V19_COMPLETE/04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/06_Authority_Execution_Settlement.png)

The LLM/compiler proposes; the professional admits, edits or rejects; the Transition Engine calculates; policy generates Human Stops; the authority holder attests; an immutable course-specific execution package is created only when the course has an external effect; settlement returns one canonical result state.

- Zero selected change sets block response preparation.
- Defer creates no execution package.
- Success is shown only after server acknowledgment.
- Settlement verifies Candidate, selected changes, Human Stops, authority records, package acknowledgment and coverage scope.
- Replay is read-only and never writes a new Registry event.

## 10. Bitemporal and search model

One as_of_state_id governs the page. The global selector and Causal Rail reconstruct historical state without silently mixing snapshots.

Quick Navigation indexes rooms, questions, claims, source statements, locators, values, perimeters, artifacts and cells. Analytical answers are shown only when a backend capability exists.

## 11. Interaction, responsive and accessibility

- Region-keyed incremental rendering updates only changed shell regions.
- Focus and scroll are captured and restored across state changes.
- Dialogs and Object Aperture implement focus trapping and restoration.
- A small status region announces ingest, transition, Human Stop and completion; the root is not a live region.
- Transition pacing adapts to affected-set size and prefers-reduced-motion.
- At 1024-1439px contextual rails collapse or overlay; below 768px the product is read/review-first.
- Text, state, icon and color all carry semantic labels.

## 12. Fixture-free core

No domain fact may exist in the core UI unless it entered through a validated projection.

Keystone and Orion are fixture packs outside the core. Connected mode never imports fixtures and never falls back silently. Mock Connected and Offline Demo are selected explicitly and remain visibly synthetic.

## 13. V19 Definition of Done

- All 44 Fabri audit findings are implemented and mapped to evidence.
- 89 automated tests pass, including API, browser, responsive, negative-path and core-purity checks.
- Two cases render through the same frontend without code changes.
- File/path/URL/inbox ingestion, progress, projection refresh and source inspection are visible.
- Claims, questions, cells, sources, coverage and bindings are reachable through granular routes.
- Authority, execution and settlement remain server-gated and idempotent.
- Every screen in the atlas is captured from the runnable V19 build.
