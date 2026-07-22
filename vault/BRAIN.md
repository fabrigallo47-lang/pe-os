---
type: brain-index
written-by: phase-coordinator
produced: 2026-07-15
---

# PE OS — Vault Brain Index

This file is the human-readable landing page for the vault. Open it first in Obsidian
to orient yourself before navigating the graph.

## What lives where

| Folder | What it holds | Who writes it |
|---|---|---|
| `deals/<slug>/deal.md` | Deal thesis, derived state, coordinator brief | human (open) + coordinator (brief section) |
| `deals/<slug>/questions/` | The question tree — what must be true for the thesis to hold | human + proposer |
| `deals/<slug>/claims/` | Typed, provenanced evidence — the epistemic backbone | extractor (LLM) + human |
| `deals/<slug>/assumptions/` | Quantified propositions + version history + stale flag | proposer (LLM) |
| `deals/<slug>/events/` | Immutable event log — the coordination backbone | all agents |
| `deals/<slug>/outputs/` | Workstream findings tied to assumptions | workstream-runner (LLM) |
| `deals/<slug>/ic/` | IC packages — assembled decision basis (never the decision) | ic-assembler (LLM) |
| `deals/<slug>/plan.md` | Phase coordinator plan — what changed + what it opened | phase-coordinator |
| `deals/<slug>/decisions/` | Human-only decision records (`/ic-record`) | human |
| `library/question-types/` | Cross-deal question-type archives (the firm brain) | librarian |
| `entities/` | Companies and people — observed, never maintained | extractor |
| `roles/` | Orchestration desks per deal-team role | human |
| `policy/policy-table.md` | The permission register — checked before every agent action | human |
| `audit/agent-log.jsonl` | Append-only audit trail — every agent action | all agents |

## How the graph reads

The knowledge graph (`/graph`) is the vault made visual. Every node is a file; every
edge is a frontmatter wikilink (`[[id]]`). The graph has no foreign data — if it is not
in the vault, it is not in the graph.

**Node colours by type:**
- Blue: `question` — the question tree, the epistemic spine of every deal
- Green: `claim` — evidence, typed by how it was obtained
- Gold: `assumption` / `deal` — the quantified propositions and the deal record
- Purple: `decision` — human-only records, append-only
- Grey: `event` — the immutable coordination log
- Orange: `entity` — companies and people (observed)
- Teal: `question-type` — the firm's cross-deal methodology library
- Red ring: `stale` — this object's basis has changed; re-run the work

**Node size** scales with degree (how many edges touch it). The highest-degree
nodes are the structural load-bearers of the deal — the questions everything else
leans on, the assumptions the plan rests on.

**Click any node** to read its raw markdown in the side panel.

## How the agents coordinate

Agents coordinate through **state, never relay** (invariant 9). The flow is:

```
inbox artifact
  → sentinel (announces ARTIFACT_ARRIVED)
  → extractor (typed claims)
  → contradiction (CONTRADICTION_FLAGGED if divergent)
  → librarian (cross-deal brain archives)
  → coordinator (deal.md brief)
  → phase-coordinator (plan.md — proposed next steps)
  → ic-assembler (ic-package.md — decision basis, human gate)
```

The **phase-coordinator** never calls other agents. It writes `plan.md` (what changed,
what it opened), emits `PLAN_UPDATED`, and returns `proposed[]` — a list of next
steps the canvas 'Run plan' button executes with the human's consent.

The **ic-assembler** writes the IC package via LLM (claude-sonnet-5). It assembles;
it never decides. The decision record is written only by the human via `/ic-record`.

## Obsidian graph tips

- Enable "Show orphans" in Obsidian graph settings to see entities and question-types
- Filter by `type:claim` or `deal:astrelia` in the Obsidian search panel
- The `bears-on` edges (claim → question) are the epistemic backbone
- The `tests` edges (question → assumption) close the loop: evidence → assumption → thesis

## Deals currently in vault

<!-- auto-maintained by coordinator — check deal.md files for current state -->
- **astrelia**: European space tech — S0_INTAKE (pilot deal)
