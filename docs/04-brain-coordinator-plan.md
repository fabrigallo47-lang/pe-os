# Plan: Obsidian Brain + Knowledge Graph + Phase Coordinator (LOCAL ONLY)

*Planned by Fable 5 with full session context. Executor: follow exactly; where detail is missing, read the referenced files. Read `CLAUDE.md` and `AI_HARNESS.md` first — their invariants are law (esp.: coordination through events not agent-relay; state derived never set; append-only decisions; `written-by` on machine writes; git commits local-only, NEVER create a remote or push; product LLM calls use model `claude-sonnet-5` via `_llm_text` in `app/server.py`; ANTHROPIC_API_KEY available in `.env.vercel` — for local runs export it from there).*

**Design intent (from Alex's transcripts `sources/alex-voicenotes.txt` + `sources/alex-chat.txt`):** the deal is a living Pursuit; the system must (a) make all entities visibly interconnected (knowledge graph), (b) generate next steps by itself (palingenetic coordinator over the phases), (c) make the IC package self-assembling, decisions living objects. Every output must state *what it changed and what it opened*.

## Part A — The Brain: Obsidian + knowledge graph

1. **Graph API**: in `app/server.py` add `GET /api/graph?deal=<optional>` returning `{nodes:[{id,type,title,deal,state,epistemic,stale}], links:[{source,target,rel}]}` straight from the SQLite index (`nodes`, `edges` tables — see `tools/indexer.py`). Firm-wide by default; filter by deal when param given. Call `sync(); reindex()` first like other reads.
2. **Graph view**: new `app/static/graph.html` served at `GET /graph` — a force-directed knowledge graph, **no external libraries** (small custom simulation ~100 lines: repulsion + spring along links, canvas 2D). Visual language of `canvas.html` (graphite bg, champagne accent). Color by type (question/claim/assumption/decision/event/entity/question-type), red ring when `stale`, node size by degree. Click node → side panel with the file's content (`GET /api/node/{id}` → add endpoint returning raw markdown from `nodes.path`). Link it in the canvas header ("Graph").
3. **Obsidian-native brain**: ensure every machine-written file keeps proper `[[wikilinks]]` (already true — verify librarian/extractor outputs render links in Obsidian graph). Add `vault/BRAIN.md` (human-readable index: what lives where, how the graph reads) so opening the vault in Obsidian lands somewhere meaningful.

## Part B — Phase Coordinator (the palingenetic protocol)

4. **New agent `PhaseCoordinator`** in `agents/runtime.py` (deterministic core; contract row HVA_COMMERCIAL_02; registered in the runtime list and runnable via `/api/agents/run/phase-coordinator`). For each deal:
   - derived state from `deal.md` (never compute here — read what state-resolver wrote);
   - load allowed next transitions from `tools/contracts.py` `transitions()` (final source rows first);
   - phase playbook mapping (write as data in the file): S0–S3 origination/screening → dispatch: extractor on unprocessed inbox, proposer if no assumptions; S4–S5 diligence → dispatch: workstream runs for workstreams with open critical questions (`target-workstream` of open critical questions), contradiction; S6–S7 underwriting/IC → dispatch: ic-assembler (Part C), flag human gate (rows 7–8); S8–S13 → note the required human/external events (no dispatch).
   - **Output**: rewrite `deals/<id>/plan.md` (`type: plan`, `written-by: phase-coordinator`) with: current phase; *what changed* since last plan (diff of question states/claim count/contradictions); *what it opened* (the proposed next steps: each step = node type human|agent|external-event, target, why); emit event `PLAN_UPDATED`. Audit like the other agents.
5. **Dispatch = state-mediated**: the coordinator NEVER calls other agents. It writes the plan; a tick/canvas run executes proposed agent steps (extend `/api/agents/run/phase-coordinator` response to include `proposed:[{kind,config}]`, and in `canvas.html` add a "Run plan" button that executes them sequentially like Run flow does).

## Part C — Self-assembling IC package (Alex's beat)

6. **`ic-assembler` agent** (LLM on sonnet-5 via `_llm_text`, contract HVA_COMMERCIAL_01, runnable via `/api/agents/run/ic-assembler`): reads the deal's full graph (questions+states, claims by epistemic type, assumptions+versions, contradictions, workstream outputs, prior decisions) → writes `deals/<id>/ic/ic-package.md`, regenerated on each run, containing: recommendation-neutral decision basis; resolved (with strongest chain + epistemic bottom); **accepted-unresolved ledger** (what proceeding accepts, exposure); unresolved contradictions verbatim; assumptions table (value, version, stale?); **IC Shadowing** section — likely objections inferred from question types + past decision records; footer: *changed / opened* since previous package (keep previous as `ic-package-vN.md`, append-only). The decision itself stays human (never write a decision record).

## Verification (must actually run, not inspect)

- `make report` clean; runtime deploys 10+ agents with contracts; `curl POST /api/agents/run/phase-coordinator` on astrelia returns a plan and `deals/astrelia/plan.md` exists with changed/opened; `curl POST /api/agents/run/ic-assembler` produces `ic-package.md` with all sections (real sonnet-5 call — export ANTHROPIC_API_KEY from `.env.vercel`); `/graph` renders nodes>50 for astrelia and node click shows content; audit log shows the new agents with contract ids. Update `AI_HARNESS.md` session log; commit locally (Co-Authored-By trailer per repo convention). **Do not deploy to Vercel. Do not touch remotes.**
