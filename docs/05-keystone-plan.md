# Plan 05 — Keystone Validation + Kernel Adoption + Living Deal (LOCAL ONLY)

*Priorities agreed with Fabrizio 2026-07-18. North star unchanged: auto-retrieval from integrations (Outlook/Gmail/SharePoint/scraping) → auto-filed into the brain → deals & portfolio built → reasoned on. Everything below serves that: Keystone calibrates the extraction+KG that integrations will feed.*

## P1 — Keystone Layer 1: grade extraction + knowledge graph (the calibration)
Open deal `keystone` via the real pipeline; ingest the 8 Layer-1 docs (xlsx converted to sheets-as-markdown first); run extractor → proposer → contradiction → librarian.
**Graded against the answer key** (`sources/keystone-fixture/ANSWER-KEY-DO-NOT-INGEST/` — never ingested, only read by the grader):
- **EBITDA-bases test**: reported 10.2 / seller-adj 12.7 / QoE 11.9 / underwritten 11.4 / covenant 12.2 must exist as *distinct* claims with distinct subjects — the epistemic-separation test. Conflating any two = fail.
- **Riverton test**: 18.2% ultimate-parent concentration is NOT stated in Layer 1 — it must be *derived* by summing 7 data-room rows. Expect the current extractor to miss it; that failure drives the new capability: an **aggregation/derivation pass** (derived claims with `rests-on` the row claims).
- Tie-outs: `tools/grade_keystone.py` compares extracted claims vs the answer-key controlling values → scorecard (PASS/FAIL/MISSED per field).
Iterate extraction prompts/config until the scorecard is honest-good. **Answer key must never enter vault/ or any prompt.**

## P2 — Living deal: Layer 2 through time (workflows on the KG)
Feed monitoring packs strictly in order (dec2026 → mar2027 → jun2027 → aug2027 → exit2031), advancing lifecycle events (S9→S10→S11…). Each input must: update the KG, hit the assumptions it falsifies (Riverton notice → concentration assumption → staleness cascade), trigger covenant detection (LTM 10.8 vs opening covenant 12.2 with the correct definition!), regenerate the coordinator plan and IC/monitoring outputs. This is "the deal as living entity" — every input updates the graph and generates new outputs. Grade the arc against the answer key's event chronology.

## P3 — Process kernel adoption (the proposed workflows)
`sources/process-kernel/`: load `edge_classification_engineering.csv` (AXIOM/ENFORCE/CONFIGURE/SUGGEST per edge) + `macro_flows_engineering.csv` (canonical sponsor flow) into `tools/contracts.py`; PhaseCoordinator consumes them: AXIOM/ENFORCE edges = hard gates, CONFIGURE = firm-editable, SUGGEST = advisory. This supersedes the dormant dependency-graph wiring. Read `process_kernel_implementation_specification(1).pdf` §runtime-engine and map onto our engine; note deltas in AI_HARNESS.

## P4 — Integrations (the point; after calibration)
Perception connectors → inbox → existing pipeline. Local-first: Gmail/Outlook via IMAP/Graph pull, SharePoint via Graph, scraping via fetcher with allowlist. Policy row 9 flips to autonomous-within-allowlist. Build only once P1 scorecard is good — connectors feeding a miscalibrated extractor multiplies garbage.

## Time estimates (wall clock, local)
- P0 organize/quarantine: done tonight.
- P1 first graded run: ~2–3 h (xlsx conversion + 8 ingestions ≈ 3 min each + grader build); iterating to pass EBITDA + Riverton tests: 1–2 focused sessions.
- P2 full monitoring arc: ~1 session after P1.
- P3 kernel first slice (edge classes into coordinator): 1–2 sessions; spec read-through in parallel.
- **Total to a graded end-to-end demo (Layers 1+2 vs answer key): ≈ 3–4 sessions / a weekend.**
- P4 first connector (Gmail read-only pull): 1 session, after P1.
