# PE OS

The operating system for private markets. One typed graph in the middle; small contract-bound agents around it; humans deciding on top. Everything local — no remote, no telemetry, model calls only under policy row 3.

## The system in one look

```
 PERCEPTION            CENTER (canonical)          AGENTS (deployed)         HUMANS
 vault/inbox/   ──▶    vault/                ◀──   agents/runtime.py         decide via
 app UI forms          questions·claims·           sentinel                  app / Claude Code
 (APIs later)          events·decisions·           state-resolver            skills; rows 7–8
                       ontology·policy             contradiction             are theirs alone
                            │
                            ▼ derived, disposable
                       .index/vault.db  +  vault/audit/agent-log.jsonl
```

## Run it

```bash
make setup      # once: venv + deps
make app        # live UI + API          → http://127.0.0.1:8787
make watch      # inbox watcher: drop a file → pipeline auto-activates
make agents     # deploy the agent runtime (watches vault, acts, audits)
make state DEAL=aurora   # derive a deal's state by event replay
make report     # open questions · contradictions · unbound claims
make ui DEAL=aurora      # static shareable dashboard export
make contracts  # show what the machine contracts load
make baseline   # verify frozen inputs, hashes and external-package markers
make document-eval  # multimodal gold suite: PDF/Word/PowerPoint/Excel/email/images
```

Open `vault/` in Obsidian anytime — same truth, different projection.

### V20 + extractor: quickest local run

```bash
make setup
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 4191
```

Open `http://127.0.0.1:4191/ui/index.html?mode=connected` and select the
Keystone case. In **Sources → Ingest**, upload a PDF, `.md`, `.txt`, `.xlsx`
or `.xlsm` file. Narrative sources run through V1; workbooks run through V2,
which preserves sheet/range locators plus formula and cached-value evidence.
Either route stores only a reviewable evidence proposal. Go to **Ingestion
History** and choose **Admit evidence** to promote it into the semantic Current
(Sources → Claims → Questions → Case Positions).
Choose **Reject** to retain the extraction audit trail without changing Current.
Use **Open live graph** in Sources to inspect the parallel semantic graph.

### Excel formula smoke test (PAN-51)

The workbook boundary is explicit: `.xlsx` and `.xlsm` uploads use V2 and
preserve formula text, the displayed/cached value (when present), named ranges,
and directed cell dependencies. Narrative files use V1. Legacy `.xls` is not
read as an Open XML workbook and returns: `convert the workbook to .xlsx before
upload`.

Run the versioned, non-sensitive formula fixture without an API key:

```bash
.venv/bin/python tools/excel_formula_graph.py \
  --workbook tools/fixtures/pan51_formula_model.xlsx \
  --out /tmp/pan51-formula-graph.json
```

Expected summary:

```text
[excel_formula_graph] pan51_formula_model.xlsx: 8 formulas, 14 dependencies, 2 Human Stops
  -> /tmp/pan51-formula-graph.json
```

The fixture has never been calculated by Excel and therefore contains no
displayed/cached formula values. The bounded local evaluator recomputes the six
supported acyclic outputs; the external workbook link and unsupported function
remain `null` with distinct Human Stop reason codes. After professional
admission, these formula/model nodes and edges are stored in
`excel_model_graphs.json` and projected through V20's `semantic_current_graph`;
an evaluation failure is never silently promoted to a calculated fact.

The local extraction state is intentionally ignored by Git: it contains source
material and derived claim memory. A fresh clone starts without it.

## Input surfaces (how knowledge enters)

| Input | How | Handled by |
|---|---|---|
| Documents (decks, models, packs) | drop into `vault/inbox/` | sentinel announces → `/ingest` extracts typed claims |
| Voice: meetings, expert calls, memos | drop audio (m4a/mp3/wav/mp4…) into `vault/inbox/` | transcriber (local whisper.cpp — audio never leaves the machine) → transcript → sentinel → `/ingest` as `observed` claims |
| Typed human context | app forms (claim / question / event) | server validates against the ontology, stamps `written-by: human` |
| Questions to the brain | "Ask the brain" box in the app | read-only LLM over the whole vault, citations included |
| The two ritual inputs | `/open-deal` (20 min, once) · `/ic-record` (decision moment) | Claude Code skills |
| External APIs (data providers, news) | not yet connected | policy row 9 — requires approval to enable |

## Map of the repo

| Path | What it is |
|---|---|
| `vault/` | **The product's state.** `ontology/` (schemas — the IP), `policy/` (operation→authority), `deals/<id>/` (questions, claims, events, decisions), `roles/` (desks), `library/` (question-types), `entities/`, `inbox/` (perception drop-zone), `audit/` (append-only agent log) |
| `agents/` | The deployed runtime. Every agent binds to a row of the human-vs-automatable register; `human_judgment_required` and `authority_only_human_action` classes refuse to deploy. |
| `tools/` | `contracts.py` (loads the machine contracts as data) · `engine.py` (state resolution by event replay + guards) · `indexer.py` (vault → SQLite) · `ui.py` (static export) |
| `backend/dynamics/` | Deterministic Candidate/Current/Approved transition runtime, extraction adapters, policy fixtures, schemas and executable conformance tests. The runtime consumes the compiled Live Investment Case, never the raw extraction graph. |
| `evaluation/` | Versioned multimodal gold suite for extraction and semantic understanding across PDF, Word, PowerPoint, Excel, Outlook-compatible email, images and mixed attachments. See [`evaluation/README.md`](evaluation/README.md). |
| `app/` | FastAPI server + live UI. The API is the policy boundary: writes are ontology-validated, agent endpoints map to policy rows. |
| `docs/` | `00` problem structure · `01` spec/stack · `02` backbone map · `03` architecture (canonical) · `reproducible-baseline.md` input/access plan · `report/` client teaser · `ui/` static exports |
| `CLAUDE.md` | Agent operating manual: the 10 invariants, build-order status, conventions |

## The rules that don't bend

1. Evidence attaches to **questions**, never deals. 2. Every claim carries an **epistemic type**; derived ⇒ inspectable derivation. 3. **State is derived** from events — never set by hand, never inferred from file recency. 4. **No agent-to-agent relay** — coordination through events and guards. 5. `accepted-unresolved` and decision records are **human-only**. 6. Append-only: decisions, outcomes, events, audit — supersede, never edit. 7. Artifacts stay where they are; the graph holds claims with provenance pointers. 8. Anything not permitted by the contracts is **denied by default**.
