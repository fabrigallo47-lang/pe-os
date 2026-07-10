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

## Architecture (v1)

```
vault/          canonical state — typed markdown, Obsidian-compatible, git = provenance
  ontology/     schemas (the IP). Read before writing any entity file.
  library/      question-types — cross-deal reuse + Category-2 methodology layer
  deals/<slug>/ deal.md + questions/ + claims/ + decisions/
  entities/     companies, people (observed, not maintained)
  policy/       policy-table.md — check before ANY agent action
  inbox/        artifact drop-zone → run /ingest
.claude/skills/ the agents: open-deal · ingest · contradictions · ic-record
tools/          indexer.py (vault → .index/vault.db, rebuilt on demand)
```

## Workflow

- New deal → `/open-deal`. Artifact arrives → `/ingest`. Anytime → `/contradictions`. Decision moment → `/ic-record`.
- After any vault write: `make index`. Health check: `make report`.
- Build order status: **1 decision-record ✅ schema · 2 questions+evidence ✅ schema · 3 contradiction agent ✅ v1 · 4 policy table ✅ · 5 cross-question retrieval ⬜ · then: origination/ownership/exit loops ⬜.** Next milestone: run one full past deal through the pipeline end-to-end.

## Conventions

- Entity IDs: `q-<deal>-<slug>`, `c-<deal>-<nnn>`, `d-<deal>-<nnn>`, `o-<deal>-<nnn>`, `qt-<slug>`. Stable forever; never renamed.
- Frontmatter `written-by:` on every machine-written file.
- Python: stdlib + PyYAML only in v1. No frameworks, no graph DB, no event bus (see docs/01-spec.md for the migration triggers).
- Commit after each coherent unit of work; the git log is the audit trail.
