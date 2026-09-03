# Product Architecture V4 FINAL

## One case, multiple acts

Every room is a different operation over one authoritative investment case:

- Deal Home — where the case stands
- Workstream Focus — what is happening inside one part of the case
- Trace — why a reading exists
- Simulate — what changes if an assumption changes
- Review & Admit — whether new evidence / machine proposal becomes institutional
- Resolve — which evidence-producing work can close an uncertainty
- Formation — how raw material becomes a proposed case
- Replay — what the case actually looked like at a prior cutoff
- Decision — attributed human judgment against a frozen case state
- Outputs — live writable projections of the same case

## Source of truth

The append-only bitemporal ledger is authoritative. Current state, dependency graph, readings, work queue and artifact projections are derived/materialized views.

The frontend consumes a `PantaCaseSnapshot` projection for fast rendering; it never writes primary truth into that snapshot directly.

## Kernel vs UI projection

Kernel objects keep canonical identity. UI-only containers such as Workstream, Finding and Quantity exist only as projections for investor interaction.

A Workstream is a grouping over the active Question Spine/archetype structure. It is not a universal ontology type.

## Authority

PANTA can do internal mechanical work automatically. Human/authorized authority remains definitive for decisions, risk acceptance, waivers, commitment, external/irreversible action and other governed acts.

## Replay

Historical state is loaded via:

`loadCase(caseId, { asOf })`

The frontend never asks the backend to fabricate historical snapshots.

## Artifacts

Artifacts are projections of the case, not substitutes for the case. Memo/model/decision-pack content remains addressable to underlying case objects and can become stale when its basis changes.
