---
document_id: keystone_answer_key
layer: 3_answer_key
document_type: Grading key
intended_use: Never ingest into the AI system; use only to grade extraction and analysis
---

# ANSWER KEY — NOT FOR INGESTION. For grading only.


## Full Tie_Outs table


| Cross-Document Tie-Outs and Controlling Values |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Field | Controlling value | Seller document | QoE | Firm / IC | Credit / Board | Status | Source |
| Enterprise value | 108 | 108 | 108 | 108 | 108 | PASS | KS-DL-1.2 |
| Reported EBITDA | 10.2 | 10.2 | 10.2 | 10.2 | 10.2 | PASS | Historical accounts |
| Seller-adjusted EBITDA | 12.7 | 12.7 | 12.7 | 11.4 | 12.2 | INTENTIONAL | Distinct bases |
| QoE-normalized EBITDA | 11.9 | N/A | 11.9 | 11.9 | 11.9 | PASS | QoE |
| Firm-underwritten EBITDA | 11.4 | N/A | 11.9 | 11.4 | N/A | PASS | Firm model |
| Opening covenant EBITDA | 12.2 | N/A | 11.9 | 11.4 | 12.2 | PASS | Credit agreement |
| Sponsor initial equity | 62 | N/A | N/A | 62 | 62 | PASS | v1.2 correction |
| Seller rollover | 12 | 12 | 12 | 12 | 12 | PASS | KS-DL-1.2 |
| Largest billing account | 0.076 | 0.076 | 0.076 | 0.182 | 0.182 | INTENTIONAL | Account vs parent |
| Largest ultimate parent | 0.182 | Footnoted | 0.182 | 0.182 | 0.182 | PASS | Customer data |
| Riverton notice date | 2027-01-31 | N/A | N/A | N/A | 46418 | PASS | Event chronology |
| Scope reduction effective | 2027-04-01 | N/A | N/A | N/A | 46478 | PASS | Event chronology |
| Amendment contribution | 7.5 | N/A | N/A | N/A | 7.5 | PASS | Not contractual cure |


## Full Model_Audit table


| Phase 1 Model Audit and Delivery Gate |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Audit Test | Target | Actual | Variance | Status | Case / Location | Source | Notes |
| Gross sources equal gross uses | 121 | 121 | 0 | PASS | S&U_Opening | KS-DL-1.2 |  |
| Opening balance sheet balances | 0 | 0 | 0 | PASS | S&U_Opening | PPA / opening BS |  |
| Standalone Base max balance-sheet check | 0 | 5.68434188608e-14 | 5.68434188608e-14 | PASS | Standalone Base | Model engine |  |
| Standalone Base sponsor return includes all capital | 62 | 62 | 0 | PASS | Standalone Base | Ownership_Returns |  |
| Standalone Downside max balance-sheet check | 0 | 4.26325641456e-14 | 4.26325641456e-14 | PASS | Standalone Downside | Model engine |  |
| Standalone Downside sponsor return includes all capital | 62 | 62 | 0 | PASS | Standalone Downside | Ownership_Returns |  |
| Standalone Upside max balance-sheet check | 0 | 4.26325641456e-14 | 4.26325641456e-14 | PASS | Standalone Upside | Model engine |  |
| Standalone Upside sponsor return includes all capital | 62 | 62 | 0 | PASS | Standalone Upside | Ownership_Returns |  |
| Acquisition Base max balance-sheet check | 0 | 8.52651282912e-14 | 8.52651282912e-14 | PASS | Acquisition Base | Model engine |  |
| Acquisition Base sponsor return includes all capital | 67 | 67 | 0 | PASS | Acquisition Base | Ownership_Returns |  |
| Combined Risk max balance-sheet check | 0 | 4.26325641456e-14 | 4.26325641456e-14 | PASS | Combined Risk | Model engine |  |
| Combined Risk sponsor return includes all capital | 69.5 | 69.5 | 0 | PASS | Combined Risk | Ownership_Returns |  |
| June 2027 LTM covenant EBITDA | 10.8 | 10.8 | 0 | PASS | Combined Risk | Locked event path |  |
| June 2027 gross debt | 53 | 53 | 0 | PASS | Combined Risk | Locked event path |  |
| June 2027 cash | 2.2 | 2.19986506673 | -0.000134933268653 | PASS | Combined Risk | Locked event path |  |
| June 2027 covenant net debt | 50.8 | 50.8001349333 | 0.000134933268654 | PASS | Combined Risk | Locked event path |  |
| June 2027 net leverage | 4.7 | 4.70371619752 | 0.00371619752487 | PASS | Combined Risk | Locked event path |  |
| June 2027 liquidity | 2.92 | 2.91986506673 | -0.000134933268653 | PASS | Combined Risk | Locked event path |  |
| June 2027 LCs | 2 | 2 | 0 | PASS | Combined Risk | Locked event path |  |
| Amended 15% add-back cap | 1.41 | 1.41 | 0 | PASS | Combined Risk | Credit amendment | LTM add-backs are $1.4m |
| Amendment pro forma net leverage | 4.01 | 4.00925925926 | -0.000740740740741 | PASS | Combined Risk | June reference balances | Contribution is not contractual cure |
| Standalone Base unidentified acquisitions | 0 | 0 | 0 | PASS | Standalone Base | Model design |  |
| Standalone Downside unidentified acquisitions | 0 | 0 | 0 | PASS | Standalone Downside | Model design |  |
| Standalone Upside unidentified acquisitions | 0 | 0 | 0 | PASS | Standalone Upside | Model design |  |
| Harbor add-on fully funded | 12.5 | 12.5 | 0 | PASS | Acquisition Base | Acquisition schedule |  |
| Standalone Base exit EBITDA uses LTM Mar-2031 | 18.3467200016 | 18.3467200016 | 0 | PASS | Standalone Base | Last four quarters |  |
| Standalone Downside exit EBITDA uses LTM Mar-2031 | 14.4716248593 | 14.4716248593 | 0 | PASS | Standalone Downside | Last four quarters |  |
| Standalone Upside exit EBITDA uses LTM Mar-2031 | 20.8161412969 | 20.8161412969 | 0 | PASS | Standalone Upside | Last four quarters |  |
| Acquisition Base exit EBITDA uses LTM Mar-2031 | 21.6712015633 | 21.6712015633 | 0 | PASS | Acquisition Base | Last four quarters |  |
| Combined Risk exit EBITDA uses LTM Mar-2031 | 17.85 | 17.85 | 0 | PASS | Combined Risk | Last four quarters |  |
| Delivery Gate |  |  |  |  |  |  |  |
| Unresolved inconsistency | None after explicit model assumptions and v1.2 capitalization correction |  |  |  |  |  |  |
| Phase 1 status | PASS - proceed to document production |  |  |  |  |  |  |
| Important limitation | All outputs are fictional; tax, PPA and historical completion assumptions are identified on Inputs and Model Guide |  |  |  |  |  |  |


## Full QoE_Bridge comparison


| EBITDA Basis Reconciliation ($mm) |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- |
| Adjustment | Reported | Seller View | QoE View | Firm View | Covenant View | Source / Treatment |
| Reported EBITDA | 10.2 | 10.2 | 10.2 | 10.2 | 10.2 | Historical accounts |
| Founder / executive compensation | 0 | 0.4 | 0.35 | 0.35 | 0.35 | QoE accepted at market replacement cost |
| Transaction-readiness and professional fees | 0 | 0.3 | 0.25 | 0.25 | 0.25 | Recurring audit/compliance retained |
| Integration and systems costs | 0 | 0.5 | 0.3 | 0.2 | 0.3 | Firm retains $0.10m recurring cost |
| Legal and settlement expense | 0 | 0.2 | 0.2 | 0.2 | 0.2 | Supported non-recurring item |
| Duplicate occupancy / facility move | 0 | 0.2 | 0.15 | 0.15 | 0.15 | Implemented closure |
| Implemented headcount savings | 0 | 0.4 | 0.25 | 0.25 | 0.5 | Additional covenant-certified savings |
| Pricing and utilization initiatives | 0 | 0.5 | 0 | 0 | 0 | Forecast only; no historical add-back |
| Revenue cut-off | 0 | 0 | -0.1 | -0.1 | -0.1 | QoE correction |
| Bonus accrual normalization | 0 | 0 | 0.2 | 0.2 | 0.2 | Approved plan support |
| Related-party rent normalization | 0 | 0 | 0.1 | 0.1 | 0 | Not recognized in covenant definition |
| Revenue / WIP quality reserve | 0 | 0 | 0 | -0.2 | 0 | Firm conservatism |
| Customer / project run-rate reserve | 0 | 0 | 0 | -0.15 | 0 | Firm conservatism |
| Incremental finance and reporting cost | 0 | 0 | 0 | -0.05 | 0 | Recurring post-close cost |
| Procurement and software savings | 0 | 0 | 0 | 0 | 0.15 | Covenant-only certified saving |
| Adjusted EBITDA | 10.2 | 12.7 | 11.9 | 11.4 | 12.2 | Controlling amounts |


## Intentional divergences and why

| Divergence | Party / document version | Correct grading interpretation |
|---|---|---|
| EBITDA basis | Seller uses $12.7m; QoE uses $11.9m; Firm uses $11.4m; credit documents use $12.2m | These are intentionally different definitions, not arithmetic errors. The system should identify which basis applies to which purpose. |
| Customer concentration | Seller presents 7.6% largest billing account; firm identifies 18.2% ultimate-parent Riverton exposure | The seller view is by billing account. The firm view aggregates seven billing accounts under one parent. |
| Revenue recurrence | Seller says 72% recurring or repeat; firm should split this into 38% scheduled/programmatic and 34% repeat projects | Repeat projects are not the same as contractually recurring revenue. |
| Utilization | Seller-reported utilization is 70%; standardized billable-professional utilization is 66%; standardized total-professional utilization is 63% | The system should recognize different definitions, not average them. |
| Integration status | Seller says the acquisitions are commercially integrated; firm and board materials show systems are not fully integrated | Commercial branding and operational systems integration are different facts. |
| Covenant metrics | Firm valuation uses firm EBITDA; lender compliance uses covenant EBITDA | Lender EBITDA is a contract definition and is not the valuation basis. |
| Amendment funding | The $7.5m August 2027 sponsor contribution is not an ordinary contractual equity cure | It is a waiver-condition equity contribution that repays revolver debt and leaves cash on the balance sheet. |
| Pre-close knowledge | IA and IC know customer concentration and integration risk; they do not know Riverton will later reduce scope | The event is foreseeable in kind but not known as a future fact before it happens. |



## Full causal chain for grading

1. The seller presents Alderstone as a scaled outsourced technical-services platform with $74.0m of FY2025 revenue, $12.7m of seller-adjusted EBITDA and 72% recurring or repeat revenue.
2. The seller presents customer concentration by billing account, showing the largest billing account as 7.6%, with a footnote that some accounts may share a common parent.
3. The data-room customer schedule contains seven Riverton billing accounts under Riverton Industrial Group. Summing those rows yields 18.2% ultimate-parent exposure.
4. The third-party QoE normalizes EBITDA to $11.9m and rejects forecast-only pricing and utilization improvements.
5. The Firm applies additional conservatism and underwrites $11.4m of firm EBITDA.
6. The Firm's Initial Assessment identifies customer concentration and integration as the two key concerns.
7. The IC memo accepts the Riverton concentration and integration risk with conditions, including reporting, a $4.0m integration/liquidity capacity, integration leader, readiness review and acquisition gating.
8. One IC member dissents because the 18.2% customer concentration, incomplete integration and 9.5x firm entry multiple do not provide enough compensation for correlated risk.
9. The transaction closes March 31, 2026 at $108.0m EV with $62.0m sponsor cash equity, $12.0m seller rollover, $42.8m first-lien debt and $3.0m opening cash.
10. Sentinel closes September 30, 2026 and adds systems complexity.
11. Board Pack 1 in December 2026 shows Project Unify rated yellow, with 17 high-severity defects, 11% customer records requiring manual review, WIP at $6.4m and DSO at 68 days, but no future Riverton decision known.
12. Project Unify goes live January 1, 2027.
13. Riverton issues notice January 31, 2027 and the scope reduction becomes effective April 1, 2027.
14. Board Pack 2 in March 2027 shows billing disruption, Riverton notice, worsening utilization, DSO, WIP and forecast covenant pressure.
15. June 30, 2027 lender-accepted covenant EBITDA is $10.8m, gross debt is $53.0m, cash is $2.2m, net leverage is 4.70x and liquidity is $2.92m including $2.0m of letters of credit.
16. The borrower breaches total net leverage and minimum liquidity.
17. Management proposes higher EBITDA adjustments, but the lender accepts only $10.8m.
18. On August 15, 2027, the sponsor contributes $7.5m as a waiver-condition equity contribution, not an ordinary contractual equity cure.
19. $4.78m repays the revolver and $2.72m remains as cash. Pro forma leverage using June 30 reference balances is 4.01x.
20. The amendment resets covenants, increases pricing, tightens add-back flexibility, cancels remaining DDTL availability, suspends acquisitions and requires enhanced reporting.
21. The recovery plan focuses on billing command center, customer stabilization, systems remediation, working-capital control and governance.
22. Final modeled March 31, 2031 combined-risk outcome: exit LTM EBITDA $17.9m, exit economic net debt $20.9m, sponsor capital $69.5m, sponsor proceeds $104.4m, gross MOIC 1.50x and gross XIRR 8.7%.

A correct AI analysis should reconstruct that the failure was not an undiscovered diligence surprise. It was the materialization of two risks that were identified, debated, accepted with conditions and then compounded after the Sentinel acquisition and Project Unify cutover.
