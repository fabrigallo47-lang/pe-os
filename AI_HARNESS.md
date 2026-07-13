# PE OS — AI Harness & Operating Manual

> **This is the operating system for any AI agent working in this repo.** Read at session start, follow during work, update at task end (§4). Codebase facts live in the code and `CLAUDE.md`; this file holds the playbooks and the running findings. A finding not written down is a finding lost.

**Last updated:** 2026-07-10 · **Stack:** typed-markdown vault (Obsidian) · Python 3 + PyYAML + SQLite · Claude Code skills as agent runtime · git as provenance

---

## 0. Operating protocol

1. Session start: read this file and `CLAUDE.md`.
2. Before writing any vault entity: read its schema in `vault/ontology/`.
3. Before any agent action: check `vault/policy/policy-table.md`. Unlisted operation ⇒ `approval`.
4. Verify by execution: `make index && make report` after vault changes; run the skill end-to-end, don't inspect.
5. Task end: append to §4 session log; update `CLAUDE.md` build-order status if it moved.

### Definition of done
- [ ] Vault files conform to ontology schemas (indexer parses them: no `!` warnings)
- [ ] `make report` reflects the change (question states, bindings, contradictions)
- [ ] Policy table respected — human-only transitions untouched by agents
- [ ] Findings recorded in §4; committed to git

---

## 1. Task playbooks

**Add or change an ontology schema** — this is a product decision, not an edit. Update the schema file, then check every existing vault file still conforms (`make index` surfaces parse failures), then note the change in §4 with rationale. Schemas are versioned by git; breaking changes need a migration note.

**Add a question-type** — `vault/library/question-types/qt-<slug>.md`. Include "What resolves it" in epistemic-type terms. Link from related types' `decomposes-into`.

**Extend the indexer** — new frontmatter link field ⇒ add to `LINK_FIELDS` in `tools/indexer.py`. Keep it rebuild-from-scratch; no incremental state.

**Run the pilot deal** — `/open-deal` → drop artifacts in `vault/inbox/` → `/ingest` each → `/contradictions` → `/ic-record` → later, outcome file. The pilot's purpose is to falsify the ontology cheaply; schema friction discovered here is the deliverable, not a bug.

## 2. Key invariants
See `CLAUDE.md` — the eight invariants there are load-bearing; this file adds none.

## 3. Known tensions (open engineering questions)
- **Binding accuracy (Q1, docs/00 §7):** binder currently trusts the model; measure precision on the pilot deal before trusting unbound/bound status in reports.
- **Confidentiality boundary (policy row 3):** pilot-scoped. Re-authorize before any real firm data.
- **Subject normalization:** contradiction detection groups on the `subject` string; extractor must check existing subjects before minting new ones, or contradictions become invisible. Candidate for an indexer-assisted dedupe pass.

## 4. Session log & findings (append every task — newest first)

### 2026-07-13 — V1 LOOP COMPLETE (Fabrizio's 4-step definition, all proven live)
- New objects: `assumption.md` (statement/value/basis/version; questions link via `tests`) + `workstream-output.md` (findings `tied-to` assumptions, `stale` flag). Indexer: tests/tied-to/basis/uses edges.
- **Proposer** (LLM, auto-once-per-deal when claims exist & no assumptions): wrote a-aurora-001…005 grounded in claims, linked questions' `tests`. **Workstream runner** (`POST /api/agents/workstream/{deal}` + UI select): produced wso-aurora-commercial_market-001, tied to 3 assumptions, using 7 claims. **Staleness** (deterministic): value change → dependents flagged `stale: true` + ANALYTICAL_OBJECT_SUPERSEDED event. Proven: a-aurora-001 revised 115%→105% ⇒ q-aurora-retention + the wso output stale in 12s.
- UI: Assumptions section (inline value edit = the staleness trigger), Workstream outputs with STALE badges, stale badges on questions, run-workstream control. PATCH `/api/deal/{deal}/assumptions/{aid}` bumps version + history.
- Runtime now 9 agents. V1 = upload→extraction ✅ · OS proposes ✅ · workstream run ✅ · staleness cascade ✅.

### 2026-07-13 — WORKING SYSTEM DELIVERED (7 agents, full autonomous chain proven)
- **Extractor agent** (LLM via headless claude, acceptEdits, once-per-file state, 120KB autonomous cap): artifact → typed claims bound to questions. Proven live: expert-call transcript → 3 claims (c-aurora-008/009/010), correctly `observed`, subject strings reused, transcription error handled and noted, Evidence sections updated.
- **Coordinator agent**: rewrites deal.md § State of the deal — derived state, critical open questions ranked by fan-in, contradictions, allowed next transitions. (Next-transition hint currently reads v1-alias rows only.)
- **Upload connection**: `POST /api/upload` (multipart) → vault/inbox → cascade. UI "Feed the deal" panel + 12s auto-refresh (paused while typing/dialog open).
- Full chain proven end-to-end: audio → transcript (local whisper) → sentinel event → extractor claims → contradiction ×3 → librarian brain archive → coordinator brief → live UI. Runtime = 7 agents.
- Ops note: runtime/server restarts kill via pkill; extractor runs cost Claude quota (~90s each).

### 2026-07-13 — Brain agents + voice input; 5 agents deployed
- **Librarian** (deterministic, HVA_COMMERCIAL_02): maintains question-type Evidence archives cross-deal from the index — the upward flow deal→brain. Verified: 3 archives populated.
- **Ask-the-brain** (`POST /api/agents/ask` + UI box): read-only headless Claude over the vault (tools Read/Grep/Glob only). Verified live: cited claims by id, weighed epistemic types, connected retention→growth dependency.
- **Transcriber** (machine_assisted_extraction): audio in inbox → ffmpeg → whisper.cpp (local, `.models/ggml-base.bin`, 141MB, gitignored) → `*.transcript.md` with `epistemic-default: observed` → sentinel announces. Verified end-to-end with `say`-generated call audio. Upgrade path: ggml-small for accuracy. Sentinel now ignores `.16k.`/`.txt` temp files.
- User directive: proceed without asking permission through project completion.
- Deployed set now: sentinel · state-resolver · contradiction · librarian · transcriber.

### 2026-07-12 — Final contracts ingested; agent runtime deployed; repo tidied
- `sources/domain-contracts-final/` (13 files, 19:49 package): 77 entities/964 fields, 46-transition state machine with predicate DSL, 877 permission policies/21 roles/24 authority actions, epistemic schemas (37 reasoning operators, 181 sufficiency rules, **114-row human-vs-automatable register**), 30 product requirements, enforce-vs-configure register. Per PR_030 these are machine contracts — loaded as data via `tools/contracts.py`, not hand-coded.
- Engine now replays against final transitions + v1 aliases (70 rows merged). Repair precedence available from contracts.
- **Agent runtime deployed** (`agents/runtime.py`, `make agents`): polling watcher, 3 agents (sentinel/inbox, state-resolver/events, contradiction/claims), each **bound to its register row and refusing forbidden automation classes**; append-only audit at `vault/audit/agent-log.jsonl`. Live-verified end to end: inbox drop → ARTIFACT_ARRIVED event → state re-derived; API claim → CONTRADICTION_FLAGGED event → state re-derived. No agent-to-agent calls anywhere — all via events (invariant 9).
- README rewritten as the single map (was the "mess" complaint). Next integration candidates from the package: predicate-DSL guard evaluation, permission grid enforcement in the server per role, epistemic sufficiency rules on question resolution, gates as ENT_GATE objects.

### 2026-07-12 — Live app (UI ⇄ agents ⇄ vault)
- `app/server.py` (FastAPI, localhost:8787, `make app`): the API is the policy boundary. Reads: deals, deal view (replay+guards+contradictions), ontology/policy, inbox. Writes (human, `written-by: human`): claims / questions / events via ontology-shaped templates — **server enforces rule 3** (derived ⇒ derivation required; verified by test). Agents: state engine (row 4), contradiction (row 5, emits CONTRADICTION_FLAGGED event), ingest via headless `claude -p` with the /ingest skill (row 3; untested end-to-end — uses user quota).
- `app/static/index.html`: live dashboard + add-claim form with epistemic selector (derivation field appears only for `derived`), add-question, record-event dialogs, agent console, ontology & policy browser tab. Same navy/gold system.
- Validated loop: UI POST → vault file → reindex → engine → UI refresh. Growth contradiction now 3-way (34/28/31) after test claim c-aurora-006.
- Static export (`tools/ui.py`) kept for shareable snapshots.

### 2026-07-12 — Deal dashboard UI
- `tools/ui.py` (`make ui DEAL=<id>`): generates `docs/ui/<deal>.html` from the live index — read-only projection, self-contained, zero external refs. Sections: lifecycle rail (S0–S13, current highlighted), KPI row, IC-gate-held banner (guard replay), nested question tree with state/critical/workstream badges, contradiction cards with epistemic types side by side ("shows its working" marker on derived), event timeline with the blocked transition marked.
- Palette from PE-brand research: deep navy dominant (trust/"old money"), gold as restrained accent only, green=resolved/growth, muted red=contradiction/critical. Serif display (Iowan/Palatino), mono for event kinds, tabular numerals. Layout quality patterns from the prior internal project; none of its naming.
- ui-ux rules applied: 4.5:1 contrast pairs, color never sole indicator (badges carry text), reduced-motion respected, no emoji icons, single-accent discipline.

### 2026-07-12 — Engine built; full stack validated on demo deal
- `tools/engine.py`: derives deal state by replaying immutable events through the backbone transition register (CSV loaded from sources); implements guard T10 (no S7 entry while critical questions are open and unaccepted); `--write` updates `deal.state` per invariant 10. `make state DEAL=<id>`.
- Demo deal `aurora` (marked `demo: true`): 4 questions (2 critical), 5 claims with two planted contradictions, 8 events including a premature IC push. Result: state derived S0→S6, **T10 held the IC gate** (2 critical questions open), both contradictions surfaced with epistemic types side by side. The wow demo is now reproducible in one command.
- Indexer fix: deal inferred from `vault/deals/<slug>/` path when frontmatter lacks it (claims don't carry `deal`).
- Note: shell cwd persisted into a subdir mid-session and broke relative-path commands; use absolute paths in Bash.

### 2026-07-12 — Target architecture fixed; backbone schemas integrated
- Fabrizio's target confirmed against the documents: one central graph + small hardened agents + gated ingestion edge. Three doc-driven refinements adopted (see `docs/03-architecture.md`, now canonical): (1) center holds reasoning+state, never files; (2) **no agent-to-agent handoff** — coordination is state-mediated via immutable events + guards + dependency graph (blackboard); (3) perception is gated (AccessGrant, provenance per claim, two sanctioned human inputs).
- Schema integration: new `event.md` + `exception.md`; `deal.stage` → derived `deal.state` (S0–S13/SX); question schema gains `critical`, `target-workstream`, and acceptance scope/conditions/expiry/review-trigger. CLAUDE.md invariants 9–10 added.
- v1 engine note: no daemon — skills emit event files and evaluate guards when run; semantics identical, scheduling manual.

### 2026-07-12 — Workflow backbone V1 ingested
- New source package in `sources/workflow-backbone-v1/`: 15-state deal lifecycle with deterministic state-resolution rules, 24 guarded transitions, typed 19-node/49-edge workstream dependency graph, 21 provisional object types, first-class unhappy paths (13 reason codes, skip/backtrack/revival).
- Reconciliation with our ontology written in `docs/02-workflow-backbone-map.md`. Headline: the spec is the missing *process layer*; our vault stays the *reasoning layer* and the ontology-integration target (the spec says so itself). Keep epistemic typing + question-attachment; adopt state machine, ExceptionRecord, WorkflowEvent, risk-acceptance expiry/review triggers, LOAD_BEARING vs HABITUAL ordering flags.
- Watch item: WorkstreamTask/Output risks reintroducing human-maintained fields — only adopt if derivable from events.

### 2026-07-10 — Roles-as-desks layer added
- Fabrizio's idea: an agent per real-life role, activating to do the work and feed the brain. Refined to avoid cloning the org chart (which would re-import the silo problem the system exists to destroy): **roles are orchestration desks** — event triggers + invocable functional agents + authority profile + a named human counterpart. Functional agents remain the auditable unit; roles never own data.
- Added `vault/ontology/role.md` + three v1 desks in `vault/roles/` (analyst, diligence coordinator, IC secretary). Portfolio desk and librarian deferred until those stages activate.
- Demo framing this unlocks: "every person on the deal team gets a counterpart desk that never sleeps."

### 2026-07-10 — Scaffold created
- Studied a prior internal project as the pattern source: AI_HARNESS operating manual, AgentSpec registry (typed tools + permission modes + append-only audit log + mandatory reasoning field), `.planning` discipline, Makefile entry points.
- Ported the patterns: policy table = AgentSpec permission modes as data; skills = agents with typed I/O and declared authority; git = audit log; `written-by` = the reasoning/provenance field.
- Built: ontology (7 schemas), policy table v1, 4 skills (open-deal, ingest, contradictions, ic-record), indexer (vault→SQLite, rebuild-from-scratch), 3 seed question-types.
- Decision: claims are one-file-each for addressability; subjects are normalized strings (see §3 tension).
- Decision: ontology schemas are excluded from the index (`vault/ontology/` skipped) — they describe the graph, they are not in it.
