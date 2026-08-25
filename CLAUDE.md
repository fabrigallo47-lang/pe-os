# PE OS — Claude Code Action Plan

> Operating manual: read `AI_HARNESS.md` at session start and update it at task end. Strategy lives in `docs/00-problem-structure.md`; spec in `docs/01-spec.md`; founding sources in `sources/`.

## Prime Directive

We own the container: the ontology through which intelligence flows and leaves behind proprietary, outcome-linked data. The system unifies (holds every workstream at once), proposes (push, not pull), and bounds (every agent action maps to a policy-table row). **The human decides; the system never does.**

## Non-negotiable invariants

1. **Zero-maintenance:** exactly one structured input ever — the 20-minute thesis decomposition at deal open (`/open-deal`), plus the decision ritual (`/ic-record`). If any other flow requires a human to update a field, the product has failed.
2. **Evidence attaches to questions, never to deals.** Claims carry `bears-on` links; retrieval is by what evidence bears on.
3. **Every claim is epistemically typed** (`asserted | derived | observed | attested`); `derived` requires an inspectable `derivation` and `rests-on` chain.
4. **`accepted-unresolved` transitions and decision records are human-only** (policy rows 7–8). Decision records and outcomes are append-only — supersede, never edit.
5. **Vault is canonical; `.index/` is derived and disposable.** Never treat the SQLite index as truth; rebuild with `make index`.
6. **Artifacts are never copied into the vault** — claims point into them (`source.artifact` + `source.locator`).
7. **Nothing leaves this machine** except operations listed in `vault/policy/policy-table.md` (model API calls are row 3 — scoped, deliberate).
8. **Agents do not adjudicate.** Contradiction reports say what doesn't reconcile and who shows their working — never who is right.
9. **Coordination through state, never relay.** No agent starts another agent or hands work to one. Agents finish → emit an immutable event → guards + the dependency graph decide what activates next (see `docs/03-architecture.md`).
10. **Deal state is derived, never set.** `deal.state` comes from the backbone resolution rule over events, exposure, and blockers — never from file recency, labels, or a human update.

## Architecture (v1)

```
vault/          canonical state — typed markdown, Obsidian-compatible, git = provenance
  ontology/     schemas (the IP). Read before writing any entity file.
  library/      question-types — cross-deal reuse + Category-2 methodology layer
  deals/<slug>/ deal.md + questions/ + claims/ + decisions/
  entities/     companies, people (observed, not maintained)
  policy/       policy-table.md — check before ANY agent action
  roles/        desks — event-activated orchestration personas over functional agents,
                each serving a named human; never own data, only lens + triggers
  inbox/        artifact drop-zone → run /ingest
.claude/skills/ the agents: open-deal · ingest · contradictions · ic-record
tools/          indexer.py (vault → .index/vault.db, rebuilt on demand)
```

## Workflow

- New deal → `/open-deal`. Artifact arrives → `/ingest`. Anytime → `/contradictions`. Decision moment → `/ic-record`.
- After any vault write: `make index`. Health check: `make report`.
- Build order status: **1 decision-record ✅ schema · 2 questions+evidence ✅ schema · 3 contradiction agent ✅ v1 · 4 policy table ✅ · 5 knowledge graph ✅ · 6 phase coordinator ✅ · 7 IC assembler ✅ · 8 origination/ownership/exit loops ✅ (PLAYBOOK S10-S13 ✅ · MonitoringAgent ✅ · ExitAssembler ✅ · ArchiveAgent ✅ · PipelineAgent ✅).** Runtime: 15 agents. **P1 Layer-1 grader ✅ 8/8 · P2 Living arc ✅ 15/15 · lifecycle S12_EXIT_REALIZATION ✅ · P3 process kernel ✅ v1 · P4 integrations ⬜.** Model graph: **xlsx-parser ✅ 100% recall · claim-extractor schema ✅ (period+perimeter v2) · identity-resolver ✅ · binding-proposer ✅ · coverage-report ✅ · dependency-graph ✅ · staleness-cascade ✅ (40 nodes, 732 edges).** Benchmark: `tools/benchmark_runner.py` — Stage1 F1 85.4% (100% recall) · Stage2 (measured 2026-08-25, pre-v2-reextract) value 82.7% / epistemic 33.3% / period 1.3% / perimeter 2.7% / locator 22.7% · Stage3 ✅ 100% F1 (62/62 bindings — `tools/position_model_binder.py` zero-LLM). Retrieval test: `tools/test_retrieval.py` ✅ 34.2% divergence → 40 nodes stale → PIPELINE.md rebuilt. F5 as_of filter ✅.

**Verification: `make verify`** (`tools/verify_all.py`) — regression 36/36 · V7 acceptance 181/181 · V7 e2e 21/21 · cascade 40 nodes · grounding gate · PANTA reference runtime 4/4 SETTLED FULL. Pass `--reference-kit PATH` to include Antonio's engine.

Institutional semantics are per-deal in `vault/deals/<slug>/deal_profile.json` — **never hardcoded in `tools/`**. A deal without a profile gets no perimeter and a recorded warning; the bridge must not borrow another deal's scope. `tools/grounding_gate.py` routes unverifiable claims to human review (it never rewrites or drops one). v1 stays stdlib-only: `tools/minigraph.py` covers the graph algorithms instead of networkx.

Next: `export ANTHROPIC_API_KEY=...` → re-extract K-IC with the v2 extractor → re-score Stage2. period/perimeter are low because 55/75 matched claims carry an empty period and 44/75 carry `perimeter='unknown'`; the v2 free-text schema (commit e162d97) targets exactly that and is **not yet validated**.

## Conventions

- Entity IDs: `q-<deal>-<slug>`, `c-<deal>-<nnn>`, `d-<deal>-<nnn>`, `o-<deal>-<nnn>`, `qt-<slug>`. Stable forever; never renamed.
- Frontmatter `written-by:` on every machine-written file.
- Python: stdlib + PyYAML only in v1. No frameworks, no graph DB, no event bus (see docs/01-spec.md for the migration triggers).
- Commit after each coherent unit of work; the git log is the audit trail.
