# Project Keystone Fixture Validation Manifest

## Manifest

### Layer 1 - ingested set

- `keystone_data_room_extract.md`
- `keystone_firm_initial_assessment.md`
- `keystone_firm_model_summary.md`
- `keystone_ic_memo.md`
- `keystone_lbo_model_working.xlsx`
- `keystone_qoe_report.md`
- `keystone_question_list.md`
- `keystone_seller_cim.md`

### Layer 2 - held-back monitoring set

- `keystone_monitoring_augustamendment2027.md`
- `keystone_monitoring_boardpack1_dec2026.md`
- `keystone_monitoring_boardpack2_mar2027.md`
- `keystone_monitoring_junecompliance2027.md`
- `keystone_monitoring_recovery_exit2031.md`

### Layer 3 - answer key / grading materials

- `keystone_answer_key.md`
- `keystone_fixture_validation_manifest.md`

## Validation results

- Seller CIM largest billing account 7.6%: PASS
- IC memo includes 18.2% finding: PASS
- Data room Riverton rows sum to 18.2%: PASS
- Workbook removed answer-key sheets: PASS
- Layer 1 markdown forbidden words absent: PASS
- Layer 1 forward-event leakage absent in markdown: PASS
- Layer 2 pack separation heuristic clean: PASS
- Layer 1 workbook comments and forbidden labels absent: PASS

## Inference and separation notes

- The 18.2% Riverton ultimate-parent exposure is not stated as a concentration conclusion in the seller CIM. In the data-room extract it is discoverable by summing the seven raw customer rows whose Ultimate Parent is Riverton Industrial Group. The validation script confirms those rows sum to 18.2%.
- The Firm IC memo states the 18.2% finding as the Firm's own diligence conclusion.
- The working LBO workbook retains case sheets because the task explicitly required keeping all case sheets. The explicit answer-key sheets were removed and audit labels/comments were scrubbed.
- No Layer-1 markdown document dated before March 2027 refers to the later Riverton notice, scope reduction, covenant breach, waiver or final outcome.
- Layer 2 files were split by slide ranges and release dates; earlier board packs do not include later waiver or recovery slides.
- No mixed-party source sentence was copied into Layer 1 where it would leak another party's knowledge; in such cases, content was restated only from the relevant party's viewpoint using source facts.
## Unable-to-perfectly-separate caveat

- The Layer-1 working workbook retains all case sheets, including `Combined_Risk`, because the task explicitly instructed that all case sheets remain in `keystone_lbo_model_working.xlsx`. The answer-key sheets (`Tie_Outs`, `Model_Audit`, `Model_Guide`) were removed and audit/comment labels were scrubbed, but the numeric combined-risk case remains in the workbook. For a strictly pre-close-only ingestion set, move `Combined_Risk` and related event rows in `Debt_Covenants` / `Ownership_Returns` into the answer key instead.
