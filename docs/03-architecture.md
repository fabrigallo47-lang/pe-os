# PE OS — Target Architecture (canonical statement)

*Agreed 2026-07-12. Supersedes informal descriptions. Where any ambiguity arises, the workflow backbone (`sources/workflow-backbone-v1/`) and the OSPM principles win, in that order of specificity.*

## The shape: hub-and-spoke blackboard

```
                    ┌─────────── PERCEPTION EDGE (gated) ───────────┐
                    │  users (2 sanctioned inputs) · inbox · APIs    │
                    │  gate: AccessGrant before confidential intake  │
                    │  rule: provenance flag on every source claim   │
                    └──────────────────┬────────────────────────────┘
                                       ▼
   ┌────────────────────── THE CENTER: one typed graph ──────────────────────┐
   │  vault/ — questions · claims · decisions · outcomes · events ·          │
   │  exceptions · entities · question-types · deal state                    │
   │                                                                          │
   │  Holds REASONING + STATE, never files: artifacts stay in place,         │
   │  external systems are queried as sources, claims point outward.         │
   │  Deal state is DERIVED (resolution rule) — no human ever sets it.       │
   └───────────────┬───────────────────────────────▲────────────────────────┘
                   │ state change / event           │ WorkflowEvent (immutable)
                   ▼                                │
   ┌──────────────────── AGENTS: small, hardened, state-activated ──────────┐
   │  Functional agents: one narrow job, typed I/O, policy-row authority.    │
   │  NO agent-to-agent handoff. An agent finishes → emits event → the       │
   │  state machine's guards + the typed dependency graph decide what        │
   │  activates next. Desks (roles) bundle activations for a named human.    │
   └──────────────────────────────────────────────────────────────────────────┘
                   │
                   ▼
   Humans decide (policy rows 7–8, IC, risk acceptance). The system proposes.
```

## The three laws (from the documents; they override convenience)

1. **One graph, not one bucket.** The center is the unification of *reasoning* into one substrate (OSPM §4). Artifacts stay where they are (§3: Excel, data rooms, proprietary DBs are sources, not destinations). Claims carry pointers; nothing is warehoused.
2. **Coordination through state, never through relay.** Execution follows the backbone: WorkflowEvents are the only way agents affect the flow; transitions fire on trigger + guard; the primary deal state is resolved from authoritative events, exposure, and blockers — "do not use the most recently uploaded document as the state determinant." Every handoff is therefore a recorded, replayable event; any agent can fail and be re-run without breaking a chain, because there is no chain.
3. **Gated perception.** Nothing confidential enters without an access basis (backbone S1, edge E01 — hard block). Every source claim carries provenance (S2). Humans are asked for structure exactly twice per deal (open, decision); all other human knowledge arrives as byproduct.

## Execution semantics for every agent (the "hardened small agent" contract)

An agent invocation must satisfy, in order:
1. **Activation** — a WorkflowEvent or state condition listed in its spec (or its desk's `activates-on`). Agents do not self-start and are not started by other agents.
2. **Authority check** — every operation maps to a policy-table row; unlisted ⇒ approval.
3. **The job** — one typed input → one typed output, written into the graph with `written-by` and provenance.
4. **Emission** — an immutable event recording what it did (append-only; corrections supersede).
5. **No adjudication, no state-setting** — it never sets the primary deal state (derived), never resolves judgment questions, never speaks for the firm.

What activates next is the engine's business (state machine + dependency-graph edge modes), not the agent's.

## Layer inventory (current implementation status)

| Layer | Implementation | Status |
|---|---|---|
| Center | `vault/` typed markdown + derived SQLite index | live |
| State backbone | S0–S13/SX machine + 49-edge graph (`sources/workflow-backbone-v1/`) | reference data ingested; schemas integrated (see `ontology/event.md`, `exception.md`, `deal.md`) |
| Functional agents | Claude Code skills (extractor, binder, contradiction, recorder, decomposer) | live, session-triggered |
| Desks | `vault/roles/` | 3 defined |
| Perception edge | `vault/inbox/` + `/ingest`; API connectors | inbox live; connectors pending (policy row 9) |
| Engine (auto-activation) | file-watcher/daemon evaluating guards | deliberately deferred — session-run today, same semantics |
