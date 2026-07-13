---
type: claim
id: c-astrelia-027
epistemic: derived
subject: "FY30E plan revenue"
value: "€922.93m implied by summing FY30E segment tranches — €73.83m below the €996.76m P&L revenue line"
bears-on: ["[[q-astrelia-commercial]]", "[[q-astrelia-financial]]"]
direction: contradicts
source:
  artifact: "vault/inbox/astrelia-business-plan-extract.md"
  locator: "lines 26-29 (Segment revenue tranches) vs line 8 (P&L revenue row)"
  author: "extractor (arithmetic over Astrelia management figures)"
  date: 2025-07-08
derivation: "FY30E column sum of tranches: Defense 288.75 (pipeline) + Earth Observation 3.38 (high-prob) + 480 (pipeline) + Scientific Missions 131 (pipeline) + Other 19.8 (pipeline) = 922.93; P&L FY30E revenue = 996.76; gap = 996.76 - 922.93 = 73.83. Inputs asserted by management."
rests-on: ["[[c-astrelia-026]]", "[[c-astrelia-017]]"]
supersedes: null
extracted-by: extractor
extracted: 2026-07-13
---

The plan's own FY30E segment tranches sum to €922.93m, €73.83m short of the €996.76m FY30E revenue in the P&L table — the segment detail does not reconcile with the headline revenue line.

> pipeline: [0, 0, 0, 32.49, 42, 147.56, 288.75] … | revenue | 38.23 | 62.06 | 115.57 | 212 | 385.6 | 631.72 | 996.76 |
