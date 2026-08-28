# Fabri V17 Extractor-to-Screen Audit - V19 Coverage Matrix

All 44 findings were re-audited against V19. Each item is implemented and included in the automated regression suite.

## A1 - Nessun input per file, percorso o URL
**Status:** IMPLEMENTED
File, server-path and URL ingestion are visible in Source Center and use one async job contract.

## A2 - La drop-zone del vault è invisibile alla UI
**Status:** IMPLEMENTED
Vault Inbox is a visible tab with refresh and ingest actions.

## A3 - Nessun aggiornamento dopo un ingest
**Status:** IMPLEMENTED
Jobs expose progress; completion automatically reloads projection and sources.

## A4 - Un solo deal, cablato in tre posti
**Status:** IMPLEMENTED
Bootstrap exposes multiple cases and the case switcher loads a new projection.

## A5 - Nessun giudizio umano raggiunge il vault
**Status:** IMPLEMENTED
Claim reviews and notes are written through session-scoped server routes.

## A6 - I due input strutturati del prodotto non esistono a schermo
**Status:** IMPLEMENTED
Case Setup and IC Record are first-class structured forms.

## B1 - Zero filtri, su dati che ne chiedono almeno sei
**Status:** IMPLEMENTED
Claims Explorer exposes seven filters plus search.

## B2 - L'ordinamento è deciso in Python
**Status:** IMPLEMENTED
Client sorting is explicit and changeable.

## B3 - La paginazione manca e il troncamento è silenzioso
**Status:** IMPLEMENTED
Page count and pagination are visible; no silent five-row cap.

## B4 - Nessun controllo bitemporale, benché il backend ce l'abbia
**Status:** IMPLEMENTED
Global as-of selector and replay state govern the projection.

## B5 - Da un aggregato non si scende alle sue prove
**Status:** IMPLEMENTED
Foundation evidence objects and cells are clickable into Object Aperture.

## B6 - La palette ⌘K cerca solo etichette e si ferma a 5
**Status:** IMPLEMENTED
Quick Navigation searches up to 50 loaded objects and rich source text.

## B7 - Sei lenti, nessun comportamento
**Status:** IMPLEMENTED
Decorative Lens control was removed until projection behavior exists.

## B8 - Niente esce dallo schermo
**Status:** IMPLEMENTED
Export JSON, copy ID and deep-link actions are provided.

## B9 - La stanza delle fondamenta non sa rappresentare il disaccordo
**Status:** IMPLEMENTED
Foundations preserve competing definitions, values, periods and perimeters.

## B10 - Una stanza mostra un registro col nome di un altro
**Status:** IMPLEMENTED
Decision unknowns and compiler/pipeline uncertainty are separated.

## C1 - Ogni cambio di stato ridisegna tutta la pagina
**Status:** IMPLEMENTED
The renderer is region-keyed and updates only changed regions while preserving focus and scroll.

## C2 - Gli errori non hanno dove comparire
**Status:** IMPLEMENTED
Operation-specific error cards and recovery actions are rendered.

## C3 - Nessuna attesa, nessun avanzamento
**Status:** IMPLEMENTED
Async ingestion and transition stages expose progress.

## C4 - Lo stato della vista non sta nell'URL
**Status:** IMPLEMENTED
Case, view, object, run and as-of state are encoded in the URL.

## C5 - Nessuna gestione del focus, nessun annuncio
**Status:** IMPLEMENTED
Focus restoration, status announcements and dialog focus traps are implemented.

## C6 - Tempi di animazione cablati
**Status:** IMPLEMENTED
Transition timing adapts to affected-set size and reduced-motion preference.

## D1 - La schermata artefatti è una tabella HTML scritta a mano
**Status:** IMPLEMENTED
Artifacts are projection-driven; no decision values are hardcoded in the renderer.

## D2 - I file ingeriti non diventano artefatti
**Status:** IMPLEMENTED
Completed ingest creates source objects, claims and governed artifacts.

## D3 - 29.476 celle catturate, nessun modo di guardarne una
**Status:** IMPLEMENTED
Workbook cells expose formula, value, locator and precedents.

## D4 - Nessun visualizzatore di pagina PDF
**Status:** IMPLEMENTED
PDF sources can render in an embedded source viewer.

## D5 - Nessuna storia delle versioni
**Status:** IMPLEMENTED
Sources and artifacts expose immutable version history.

## E1 - Invariante 2 non soddisfatto: l'evidenza non si attacca a niente
**Status:** IMPLEMENTED
Claims carry bears_on question bindings and /bindings exposes them.

## E2 - Dodici domande nel vault, zero sullo schermo
**Status:** IMPLEMENTED
The full question spine is served in each projection.

## E3 - L'agente contraddizioni non gira mai sull'estrazione live
**Status:** IMPLEMENTED
Contradiction and Shadow IC outputs are exposed in the projection/route contract.

## E4 - `/admit` restituisce uno stub
**Status:** IMPLEMENTED
Admission creates a Candidate run and Registry acknowledgements.

## E5 - `/replay` risponde 501
**Status:** IMPLEMENTED
Replay is implemented read-only with stable hashes.

## E6 - Quattro moduli maturi senza rotta
**Status:** IMPLEMENTED
Coverage, bindings, compiler-report, cell and object routes are exposed.

## E7 - Quattro rotte POST in tutto
**Status:** IMPLEMENTED
Granular source, claim, question, cell, work, note, ingest and review routes exist.

## E8 - Niente di ciò che l'umano fa viene scritto
**Status:** IMPLEMENTED
Human notes, reviews, deal opening and IC records persist in the session store.

## E9 - L'ingest blocca il thread HTTP
**Status:** IMPLEMENTED
Ingest is asynchronous and returns a job ID immediately.

## E10 - `reset` è distruttivo, senza conferma né ritorno
**Status:** IMPLEMENTED
Reset creates a new session; no destructive product reset route exists.

## E11 - Store monoutente, senza storia
**Status:** IMPLEMENTED
The mock Case Store is session-scoped, versioned and preserves Registry history.

## F1 - Il grafico della traiettoria è decorativo
**Status:** IMPLEMENTED
Scenario trajectory is supplied by projected scenario data.

## F2 - La navigazione ignora il contratto che il backend le manda
**Status:** IMPLEMENTED
Navigation consumes capabilities and available cases from the projection/bootstrap.

## F3 - Due soli elementi rivedibili, perché due chiavi sono cablate
**Status:** IMPLEMENTED
Reviewables are derived from projected events and claims, not two fixed keys.

## F4 - Le selezioni iniziali sono id che in modalità live non esistono
**Status:** IMPLEMENTED
Initial focus is read from the projection.

## F5 - Cliccare un unknown apre un cassetto senza contenuto
**Status:** IMPLEMENTED
Unknowns, claims, cells and sources have explicit Object Aperture branches.

## F6 - Il Registry mescola due registri
**Status:** IMPLEMENTED
Institutional Registry, UI state and test telemetry are separate stores.
