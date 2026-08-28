# PANTA V19.B Release Notes

## Release identity

- Product: PANTA Deal World
- Release: V19.B
- Semantic version: 19.1.0
- Base release: V19.0.0
- Release date: 27 August 2026
- Release class: corrective integrity and generalization release

## Release thesis

V19.B preserves the V18/V19 command-center architecture, source/compiler operating layer, rooms, interaction grammar and visual system. It corrects six weaknesses that prevented V19 from being used as credible evidence of generalization, bitemporality, epistemic discipline and transition integration.

## 1. Orion rebuilt as a distinct growth case

The prior Orion fixture was not retained as evidence. V19.B replaces it with a new growth-equity case for Orion Metrics Cloud.

The case now uses:

- contracted ARR and recurring-revenue definitions;
- NRR and GRR by cohort maturity;
- new-logo and expansion pipeline quality;
- implementation capacity and time to production;
- CAC payback and burn multiple;
- runway and hiring sequence;
- product and security diligence;
- milestone-linked primary financing.

It does not contain EBITDA, MOIC, IRR, leverage, rollover, debt paydown, working-capital or entry/exit-multiple quantities. Normalized exact statement overlap with Keystone is 0.0% across 42 Orion claims.

Evidence:

- `08_TEST_EVIDENCE/generalization/ORION_GENERALIZATION_REPORT.json`
- `08_TEST_EVIDENCE/generalization/ORION_GENERALIZATION_REPORT.md`
- `01_PRODUCT_BUILD/fixtures/PROJECT-ORION/`

## 2. Bitemporality implemented at the packaged reference layer

Every fixture claim, visible source event and Registry entry now carries:

- `effective_date`: when the underlying fact or act applies;
- `known_at`: when the case could legitimately know it.

The topbar as-of control is driven by date. The reference API filters claims, sources, versions, pending events and Registry entries by `known_at`. A later-arriving source never appears in an earlier knowledge projection.

Replay is generated from Registry events. The fixture carries no handwritten replay snapshots. Each replay step resolves to one event with both dates and a stable hash.

This is real bitemporal behavior in the bundled synthetic reference runtime. It is not a claim that the production Live Investment Case store, migrations or tenant-aware historical query service already exist.

## 3. `institutional_act` added and enforced

The epistemic vocabulary now has five classes:

- `asserted`
- `observed`
- `derived`
- `attested`
- `institutional_act`

The fifth class is used for the firm's own decisions, judgments, approvals, directions and conditions. It includes Firm-underwritten EBITDA at 11.4 and all IC decision claims.

Keystone distribution across 75 claims:

- asserted: 10
- observed: 11
- derived: 18
- attested: 14
- institutional_act: 22

The release suite detects firm acts and fails if any is labelled `attested`.

## 4. Typed schemas and engine-output adapter

The eight public schemas are no longer required-field shells. They type nested fields, dates, arrays, enums, bitemporal records, authority, execution, settlement and transition objects.

The engine boundary is now implemented twice:

- `07_ENGINEERING_CONTRACTS_AND_ADAPTERS/adapters/transition_runtime_adapter.py`
- `01_PRODUCT_BUILD/app/src/projection_adapter.js`

Both are pure deterministic mappings. Neither computes economics, materiality, authority or settlement. They preserve the frozen Transition Engine fields and add frontend-facing aliases only where explicitly derivable.

The frozen runtime output has 18 required fields. V19.B requires `source_event_id` as a nineteenth integration binding field so the mapped Candidate remains anchored to the admitted event.

## 5. Human Stop and blocked component shown end-to-end

Orion provides two separate transition examples:

- `retention_restatement` produces an open Human Stop requiring `approve_growth_round` authority;
- `pipeline_coverage_gap` produces a blocked renewal-forecast component with an explicit reason and resolution route.

Both are visible in Change Impact. The server:

- refuses authority before explicit preparation;
- refuses a mismatched Candidate;
- refuses settlement without the Human Stop's scoped authority record;
- refuses a change outside the calculated transition output;
- refuses blocked scope unless bounded partial settlement is explicit.

## 6. Language regression removed

The retired pricing phrase has been removed from fixture text and packaged documents. The canonical product term is **approved EV ceiling**.

## Compatibility and supersession

V19.B supersedes V19.0.0 for implementation and demonstration. The original V19 professional PDFs remain applicable except where this release addendum explicitly changes:

- Orion/generalization evidence;
- temporal and replay claims;
- epistemic vocabulary;
- schema and adapter maturity;
- transition example coverage;
- pricing terminology.

## Production boundary

The included runtime remains a synthetic reference API. Connected mode is deliberately unavailable unless a real backend is supplied. Fabri's production compiler/Case Store and Anto's production runtime remain explicit integration dependencies.
