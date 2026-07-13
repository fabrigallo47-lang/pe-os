---
type: claim
id: c-astrelia-032
epistemic: derived
subject: "FY30E plan EBITDA margin"
value: "32.5% implied by the P&L table (323.94 / 996.76)"
bears-on: ["[[q-astrelia-u3-nebulaos-margins-65-80-assumed-vs]]", "[[q-astrelia-financial]]"]
direction: context
source:
  artifact: "vault/inbox/astrelia-business-plan-extract.md"
  locator: "lines 8, 16 (P&L table, revenue and ebitda rows)"
  author: "extractor (arithmetic over Astrelia management figures)"
  date: 2025-07-08
derivation: "FY30E EBITDA 323.94 / FY30E revenue 996.76 = 32.5%. Compare Base Case stated 31% and Base-Case-implied 28.9% (288/996.76). Inputs asserted by management."
rests-on: ["[[c-astrelia-022]]", "[[c-astrelia-018]]"]
supersedes: null
extracted-by: extractor
extracted: 2026-07-13
---

The P&L table implies an FY30E EBITDA margin of 32.5%, which does not reconcile with the 31% stated in the Base Case scenario of the same artifact.

> | ebitda | 1.4 | 16.19 | 19.98 | 45.06 | 100.62 | 190.28 | 323.94 |
