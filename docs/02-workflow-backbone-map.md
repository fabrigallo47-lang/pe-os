# Workflow Backbone V1 ↔ PE OS Ontology — Reconciliation Map

*Source: `sources/workflow-backbone-v1/` (spec + machine-readable state machine and dependency graph, ingested 2026-07-12). The spec self-describes as "implementation-ready workflow backbone; object types provisional until ontology integration." This document is that integration map: `vault/ontology/` is the integration target.*

## What the package is

Four consistent artifacts: a **15-state deal lifecycle** (S0 intake → S13 archive, + SX terminal) with deterministic state *resolution* rules; **24 transitions**, each with trigger, guard, action, ordering logic, and exception route; a **typed workstream dependency graph** (19 nodes, 49 edges, 8 edge modes); and **21 provisional object types**. Plus an enforcement policy split into hard blocks vs warn-and-parallelize.

It is the **process layer** the reasoning layer was missing. Our ontology answers *what is known and decided*; this answers *where the deal is, what may run in parallel, and what blocks what* — with unhappy paths (decline, stall, backtrack, revival) as first-class citizens.

## Object-type mapping

| Spec object | Our ontology | Verdict |
|---|---|---|
| `QuestionRegister` item | `question` | Same concept. Adopt from spec: `owner`, `evidence_needed`, `target_workstream`, `critical` flag. Keep ours: epistemic evidence binding, question-types, `accepted-unresolved`. |
| `EvidenceItem` | `claim` | Ours is richer (epistemic types, `rests-on`, provenance locators). Adopt from spec: `materiality`. |
| `RiskAcceptanceRecord` | `accepted-unresolved` state + decision § | **Spec improves us**: scope, conditions, owner, and — the gem — **expiry / review trigger**. An acceptance that re-opens itself. Fold these fields into the question schema's acceptance block. |
| `DecisionRecord` | `decision` | Same spine. Adopt: `conditions` tracking, `approved_with_conditions` outcome. Keep: both-halves structure, dissent, Basis. |
| `OutcomeRecord` | `outcome` | Same. Spec adds partial/impaired/restructured statuses — adopt the richer enum. |
| `ExceptionRecord` | *(missing in ours)* | **Adopt whole.** "A dead deal is an outcome with reason-coded evidence, not missing data" — 13 reason codes, skip/backtrack/revival rules. Most deals die; this makes dead deals compound too. |
| `WorkflowEvent` | *(deferred event bus)* | The event objects we postponed, now specified: immutable, actor, timestamp, payload, transition-capable. Adopt schema now, daemon later. |
| `MonitoringSignal`, `ReunderwritingRecord`, `PositionRecord` | *(ownership stage, unbuilt)* | The S10/S11 machinery — the Portfolio desk's object types, ready-made. Falsification framing fits: a signal contradicts an underwritten assumption. |
| `WorkstreamTask` / `WorkstreamOutput` | *(none)* | New task layer. Defer: tasks risk becoming human-maintained fields (CRM death). Only adopt if derivable from events. |
| `AccessGrant`, `SourceMaterialSet` | *(none / inbox)* | Compliance-grade ingestion gating. Adopt when real firm data arrives; maps onto policy-table row 2/3 scoping. |
| `ModelCase` / `ValuationCase` | *(claims from models)* | Keep as typed artifact-derived claim clusters for now; formalize at the Excel round-trip milestone (Q4 in docs/00 §7). |

## What the spec fixes in our design

1. **`deal.stage` was a naive 7-value label.** Replace with the S0–S13/SX machine, and — critically — adopt the **state-resolution rule**: state is *derived* from authoritative events, exposure, and unresolved blockers, never from the newest file or a human update. This is our zero-maintenance principle applied to lifecycle state; the spec and the manifesto agree perfectly here.
2. **Dependency ranking gets real machinery.** The 49-edge typed graph (BLOCKS / BLOCKS_FINAL_OUTPUT / PARALLEL_SOFT / ITERATIVE_RETURN / TRIGGERS…) is the formal substrate for the Diligence coordinator desk's "which open question does the structure depend on."
3. **`LOAD_BEARING` vs `HABITUAL` ordering logic** is Category-2 methodology made explicit: which process order is substantively required vs mere convention. This is exactly the 80%-shared / 20%-firm-specific configurable layer — per-firm config lives in flipping these flags.
4. **The loop closes on dead deals too.** SX + revival conditions + reason codes mean declined/stalled opportunities retain their evidence and re-enter intake when new evidence arrives.

## What our design keeps against the spec

- **Epistemic typing of evidence** (asserted/derived/observed/attested + `rests-on` composition) — absent from the spec, load-bearing for contradiction and trust.
- **Evidence attaches to questions, not deals/workstreams** — the spec files outputs under workstreams; cross-deal compounding requires our question-type attachment. Workstreams are routing, not the anchor.
- **Question-type library and outcome `## Teaching`** — the firm-brain layer has no counterpart in the spec.
- **The policy table** — the spec's §10 explicitly defers "actor, role, permission, confidentiality and approval rules to a dedicated governance layer." We already have it: policy table + roles-as-desks.

## Integration order (when we do it)

1. Question schema: add `critical`, `owner` (have), `target_workstream`; enrich acceptance block with scope/conditions/expiry/review-trigger.
2. New schemas: `exception.md`, `event.md` (immutable, append-only like decisions).
3. Deal schema: `stage` → `state` per the machine; add the resolution-rule note; store the deal's instantiated dependency graph.
4. Indexer: ingest `state_machine_v1.json` + graph JSON as reference tables; contradiction/coordinator agents read edge modes for ranking.
5. Ownership objects (signal, re-underwriting, position) when the Portfolio desk activates.
