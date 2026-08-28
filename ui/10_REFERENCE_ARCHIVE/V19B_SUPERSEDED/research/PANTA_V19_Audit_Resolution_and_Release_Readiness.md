# Audit Resolution & Release Readiness

Resolution of Anto's V18 integrity audit and every A1-F6 finding in Fabri's extractor-to-screen audit.

**Release:** V19.0.0  
**Date:** 27 August 2026

## 1. Audit scope and conclusion

Fabri's V17 extractor-to-screen audit contained 44 findings across input, output, state, artifacts, backend and hardcoded behavior. V19 re-audited every item. Automated result: 89/89 passed.

Every A1-F6 item is implemented in the V19 package and mapped in FABRI_AUDIT_COVERAGE_MATRIX.csv.

## 2. Resolution by audit family

| Family | V19 resolution |
| --- | --- |
| A - Input | Source Center: file/path/URL/inbox, refresh, multiple cases, professional writes, case opening and IC record. |
| B - Output | Filters, sorting, pagination, as-of, drill-down, rich search, exports, multi-value foundations, separate pipeline review. |
| C - State | Region-keyed rendering, error/progress states, deep links, focus/status management, adaptive motion. |
| D - Artifacts | Projection-driven artifacts, ingested source objects, cell/formula viewer, PDF viewer and version history. |
| E - Backend | Question bindings, admission, replay, granular routes, async jobs, persistent human writes and session history. |
| F - Forcing | Projected scenario trajectories, capability-driven navigation, data-driven reviewables, projection focus and clean Registry. |

## 3. Audit coverage matrix

| ID | Fabri audit finding | V19 status | Implementation evidence |
| --- | --- | --- | --- |
| A1 | Nessun input per file, percorso o URL | IMPLEMENTED | File, server-path and URL ingestion are visible in Source Center and use one async job contract. |
| A2 | La drop-zone del vault è invisibile alla UI | IMPLEMENTED | Vault Inbox is a visible tab with refresh and ingest actions. |
| A3 | Nessun aggiornamento dopo un ingest | IMPLEMENTED | Jobs expose progress; completion automatically reloads projection and sources. |
| A4 | Un solo deal, cablato in tre posti | IMPLEMENTED | Bootstrap exposes multiple cases and the case switcher loads a new projection. |
| A5 | Nessun giudizio umano raggiunge il vault | IMPLEMENTED | Claim reviews and notes are written through session-scoped server routes. |
| A6 | I due input strutturati del prodotto non esistono a schermo | IMPLEMENTED | Case Setup and IC Record are first-class structured forms. |
| B1 | Zero filtri, su dati che ne chiedono almeno sei | IMPLEMENTED | Claims Explorer exposes seven filters plus search. |
| B2 | L'ordinamento è deciso in Python | IMPLEMENTED | Client sorting is explicit and changeable. |
| B3 | La paginazione manca e il troncamento è silenzioso | IMPLEMENTED | Page count and pagination are visible; no silent five-row cap. |
| B4 | Nessun controllo bitemporale, benché il backend ce l'abbia | IMPLEMENTED | Global as-of selector and replay state govern the projection. |
| B5 | Da un aggregato non si scende alle sue prove | IMPLEMENTED | Foundation evidence objects and cells are clickable into Object Aperture. |
| B6 | La palette ⌘K cerca solo etichette e si ferma a 5 | IMPLEMENTED | Quick Navigation searches up to 50 loaded objects and rich source text. |
| B7 | Sei lenti, nessun comportamento | IMPLEMENTED | Decorative Lens control was removed until projection behavior exists. |
| B8 | Niente esce dallo schermo | IMPLEMENTED | Export JSON, copy ID and deep-link actions are provided. |
| B9 | La stanza delle fondamenta non sa rappresentare il disaccordo | IMPLEMENTED | Foundations preserve competing definitions, values, periods and perimeters. |
| B10 | Una stanza mostra un registro col nome di un altro | IMPLEMENTED | Decision unknowns and compiler/pipeline uncertainty are separated. |
| C1 | Ogni cambio di stato ridisegna tutta la pagina | IMPLEMENTED | The renderer is region-keyed and updates only changed regions while preserving focus and scroll. |
| C2 | Gli errori non hanno dove comparire | IMPLEMENTED | Operation-specific error cards and recovery actions are rendered. |
| C3 | Nessuna attesa, nessun avanzamento | IMPLEMENTED | Async ingestion and transition stages expose progress. |
| C4 | Lo stato della vista non sta nell'URL | IMPLEMENTED | Case, view, object, run and as-of state are encoded in the URL. |
| C5 | Nessuna gestione del focus, nessun annuncio | IMPLEMENTED | Focus restoration, status announcements and dialog focus traps are implemented. |
| C6 | Tempi di animazione cablati | IMPLEMENTED | Transition timing adapts to affected-set size and reduced-motion preference. |
| D1 | La schermata artefatti è una tabella HTML scritta a mano | IMPLEMENTED | Artifacts are projection-driven; no decision values are hardcoded in the renderer. |
| D2 | I file ingeriti non diventano artefatti | IMPLEMENTED | Completed ingest creates source objects, claims and governed artifacts. |
| D3 | 29.476 celle catturate, nessun modo di guardarne una | IMPLEMENTED | Workbook cells expose formula, value, locator and precedents. |
| D4 | Nessun visualizzatore di pagina PDF | IMPLEMENTED | PDF sources can render in an embedded source viewer. |
| D5 | Nessuna storia delle versioni | IMPLEMENTED | Sources and artifacts expose immutable version history. |
| E1 | Invariante 2 non soddisfatto: l'evidenza non si attacca a niente | IMPLEMENTED | Claims carry bears_on question bindings and /bindings exposes them. |
| E2 | Dodici domande nel vault, zero sullo schermo | IMPLEMENTED | The full question spine is served in each projection. |
| E3 | L'agente contraddizioni non gira mai sull'estrazione live | IMPLEMENTED | Contradiction and Shadow IC outputs are exposed in the projection/route contract. |
| E4 | `/admit` restituisce uno stub | IMPLEMENTED | Admission creates a Candidate run and Registry acknowledgements. |
| E5 | `/replay` risponde 501 | IMPLEMENTED | Replay is implemented read-only with stable hashes. |
| E6 | Quattro moduli maturi senza rotta | IMPLEMENTED | Coverage, bindings, compiler-report, cell and object routes are exposed. |
| E7 | Quattro rotte POST in tutto | IMPLEMENTED | Granular source, claim, question, cell, work, note, ingest and review routes exist. |
| E8 | Niente di ciò che l'umano fa viene scritto | IMPLEMENTED | Human notes, reviews, deal opening and IC records persist in the session store. |
| E9 | L'ingest blocca il thread HTTP | IMPLEMENTED | Ingest is asynchronous and returns a job ID immediately. |
| E10 | `reset` è distruttivo, senza conferma né ritorno | IMPLEMENTED | Reset creates a new session; no destructive product reset route exists. |
| E11 | Store monoutente, senza storia | IMPLEMENTED | The mock Case Store is session-scoped, versioned and preserves Registry history. |
| F1 | Il grafico della traiettoria è decorativo | IMPLEMENTED | Scenario trajectory is supplied by projected scenario data. |
| F2 | La navigazione ignora il contratto che il backend le manda | IMPLEMENTED | Navigation consumes capabilities and available cases from the projection/bootstrap. |
| F3 | Due soli elementi rivedibili, perché due chiavi sono cablate | IMPLEMENTED | Reviewables are derived from projected events and claims, not two fixed keys. |
| F4 | Le selezioni iniziali sono id che in modalità live non esistono | IMPLEMENTED | Initial focus is read from the projection. |
| F5 | Cliccare un unknown apre un cassetto senza contenuto | IMPLEMENTED | Unknowns, claims, cells and sources have explicit Object Aperture branches. |
| F6 | Il Registry mescola due registri | IMPLEMENTED | Institutional Registry, UI state and test telemetry are separate stores. |

## 4. Known production-deferred capabilities

- Enterprise authentication and RBAC.
- Real VDR/CRM/email/Excel/SharePoint connectors.
- Production multi-tenant persistence, security and audit infrastructure.
- Actual external delivery; the package uses no-external-effects simulation.
- Real semantic compiler and Transition Engine integration must replace the mock adapters.

## 5. Release recommendation

V19 is ready as the definitive product-experience, source-to-screen and integration handoff for Anto and Fabri, and as a guided synthetic demo. It is not labelled production-ready.
