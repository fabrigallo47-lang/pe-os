# PE OS — v1 Specification, Structure, Stack

*Successor to [00-problem-structure.md](00-problem-structure.md). Patterns adapted from a prior internal project (AI_HARNESS operating manual, AgentSpec permission model, planning discipline).*

## Functional spec (v1 = build-order steps 1–6)

| ID | Capability | Implemented by | Status |
|---|---|---|---|
| F1 | Decision record — both halves, append-only | `ontology/decision.md` + `/ic-record` | schema + skill ✅ |
| F2 | Deal-open decomposition — the one 20-min structured input | `ontology/question.md` + `/open-deal` | schema + skill ✅ |
| F3 | Claim extraction & binding — epistemic types, provenance, bears-on | `ontology/claim.md` + `/ingest` | schema + skill ✅ |
| F4 | Contradiction surfacing — internal-only, non-adjudicating | `/contradictions` + indexer candidates | v1 ✅ |
| F5 | Policy table — operation→authority as data | `vault/policy/policy-table.md` | v1 ✅ |
| F6 | Cross-question retrieval — evidence by question-type, cross-deal | `library/question-types/` + outcome `## Teaching` | schema only ⬜ |

Non-functional: zero-maintenance (kill criterion: any human-updated field), legibility (partner-readable raw), auditability (git + `written-by` + policy rows), substrate-independence of the ontology, local-first (policy row 3 is the only sanctioned egress).

## Structure

Five layers, one repo — see `CLAUDE.md` for the map. Vault canonical, SQLite index derived-and-disposable, agents as Claude Code skills with declared typed I/O and authority, Obsidian + machine-written dashboard notes as views, session-based triggers (inbox → `/ingest`).

Key schema decisions (settled):
- One file per claim — addressability is what makes contradiction and retrieval work.
- Contradiction grouping key is the normalized `subject` string (known tension: see AI_HARNESS §3).
- Ontology schemas live in the vault but outside the graph (indexer skips `vault/ontology/`).
- Corrections are `supersedes` chains, never edits, on claims/decisions/outcomes.

## Stack

| Layer | v1 choice | Migration trigger → v2 |
|---|---|---|
| State | Markdown + YAML + git, Obsidian viewer | >1 concurrent editor, ~10⁴ entities, external deployment ⇒ DB authoritative, markdown becomes projection |
| Index | SQLite, rebuild-from-scratch | inference needing sub-second traversal ⇒ persistent graph store |
| Agent runtime | Claude Code skills; policy table enforced by procedure + harness permissions | productization ⇒ Claude Agent SDK, AgentSpec-style registry (typed tool registry, fail-fast validation, permission modes, append-only audit table) |
| Perception | Claude via `/ingest`; Python + openpyxl for Excel derivation graphs when F3 hits models | — |
| Egress | Anthropic API under policy row 3, pilot-scoped | firm data ⇒ ZDR agreement / private endpoint (Bedrock/Vertex), row 3 re-authorized |

Deliberately absent from v1: event bus/daemon, web UI, vector DB, graph DB, orchestration frameworks, multi-user sync.

## Resolved forks (from the spec discussion)

1. **Confidentiality:** pilot pragmatically on own material; model egress is policy row 3 — a listed, revocable operation, not a default.
2. **Pilot shape:** one *past* deal with known outcome — exercises F1–F6 including the outcome loop, zero confidentiality risk, built-in answer key.
3. **Tooling language:** Python (perception layer will need Excel formula-graph work; indexer stays stdlib+PyYAML).

## Acceptance test for v1

One past deal run end-to-end produces: a corrected question tree; ≥1 genuine contradiction the team hadn't put side by side; a decision record whose accepted-unresolved list is longer than the memo admitted; an outcome file whose `## Teaching` entry is retrievable from a question-type. If schema friction appears, that friction is the deliverable.
