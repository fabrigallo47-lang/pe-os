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
```

Open `vault/` in Obsidian anytime — same truth, different projection.

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
| `app/` | FastAPI server + live UI. The API is the policy boundary: writes are ontology-validated, agent endpoints map to policy rows. |
| `docs/` | `00` problem structure · `01` spec/stack · `02` backbone map · `03` architecture (canonical) · `report/` client teaser · `ui/` static exports |
| `CLAUDE.md` | Agent operating manual: the 10 invariants, build-order status, conventions |

## The rules that don't bend

1. Evidence attaches to **questions**, never deals. 2. Every claim carries an **epistemic type**; derived ⇒ inspectable derivation. 3. **State is derived** from events — never set by hand, never inferred from file recency. 4. **No agent-to-agent relay** — coordination through events and guards. 5. `accepted-unresolved` and decision records are **human-only**. 6. Append-only: decisions, outcomes, events, audit — supersede, never edit. 7. Artifacts stay where they are; the graph holds claims with provenance pointers. 8. Anything not permitted by the contracts is **denied by default**.
