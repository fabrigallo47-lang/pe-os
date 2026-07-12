---
type: claim
id: c-aurora-002
epistemic: derived
subject: "FY26 ARR growth"
value: "28%"
bears-on: ["[[q-aurora-growth-real]]"]
direction: contradicts
source:
  artifact: "vault/inbox/aurora-model-v3.xlsx (demo placeholder)"
  locator: "Rev!D42"
  author: "deal team model"
  date: 2026-07-08
derivation: "Rev!D42 = (D41/D40)-1; D41 (FY26 ARR) = opening ARR × NRR + new bookings; NRR input from mgmt data pack, bookings from [[c-aurora-004]]"
rests-on: ["[[c-aurora-004]]"]
supersedes: null
extracted-by: extractor
extracted: 2026-07-12
---

The deal team's model derives FY26 ARR growth of 28% — six points below the CIM figure — and the derivation is inspectable. Note the chain: this derived claim rests on management-asserted bookings, so it is arithmetic on top of an assertion.

> Rev!D42 → 0.28
