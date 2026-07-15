---
type: plan
id: plan-astrelia
deal: "[[astrelia]]"
written-by: phase-coordinator
produced: 2026-07-15
phase: S0_INTAKE
claims extracted: 32
contradictions: 3
---

# Plan — astrelia

_(phase-coordinator, 2026-07-15 19:56)_

## Current phase
`S0_INTAKE` — 6 critical question(s) open, 32 claim(s), 3 contradiction(s)

## Critical open questions
- [[q-astrelia-commercial]] — Is the revenue real? For Astrelia, this IS the deal.
- [[q-astrelia-financial]] — What do the numbers say under Meridian's own assumptions, not the company's?
- [[q-astrelia-tech]] — Can they build at the scale the plan assumes?
- [[q-astrelia-u1-61-2-of-plan-revenue-has-no-named]] — 61.2% of plan revenue has no named counterparty
- [[q-astrelia-u2-14-units-delivered-against-serial]] — 14 units delivered against serial-production volumes the plan assumes
- [[q-astrelia-u3-nebulaos-margins-65-80-assumed-vs]] — NebulaOS margins 65–80% assumed vs 17–25% on hardware

## What changed
- claims stable at 32

## What it opened (proposed next steps)
- [agent] → extractor: Process any unextracted inbox artifacts
- [agent] → sentinel: Announce any un-announced inbox artifacts
- [agent] → proposer: Derive assumption set from extracted claims (once per deal)

## Allowed next transitions (from contracts)
- DEAL_IDENTITY_RESOLVED_ACCESS_REQUIRED → S1_ACCESS_CLEARANCE
- DEAL_IDENTITY_RESOLVED_PUBLIC_ROUTE → S2_CASE_INGESTION
- CONFIDENTIAL_MATERIAL_REQUIRED → S1_ACCESS_CLEARANCE
- PUBLIC_OR_TEASER_MATERIAL_AVAILABLE → S2_CASE_INGESTION
