# PE Buyout Domain and Engineering Specification

## 1. Domain overview

A private-equity buyout process is a controlled transformation of an investment opportunity into an approved, executed, monitored, and ultimately realized or closed exposure. The operating system must coordinate analytical work, legal and financial execution, governance, evidence sufficiency, and capital authority without reducing judgment to a checklist.

The core control chain is:

`Question → Evidence → Reasoning operation → Finding → Assumption / Risk → Model case → Valuation case → Decision → Execution → Monitoring → Reopening / Outcome`

Each link is represented by typed objects and lineage. A document may represent one or more objects, but it does not replace the underlying question, finding, assumption, model, decision, approval, or outcome.

The lifecycle supports both positive and negative paths: proceed, defer, decline, abandon, backtrack, conditionally approve, fail signing or closing, monitor, re-underwrite, follow on, restructure, impair, partially exit, retain residual exposure, realize, archive, or revive.

## 2. Design principles

- **Questions are first-class.** Material uncertainty is owned, testable, evidenced, resolvable, and reopenable.
- **Assumptions are versioned.** A later view never overwrites the assumption version supporting an earlier decision.
- **Evidence is multidimensional.** Availability, relevance, reliability, completeness, recency, corroboration, sufficiency, and conclusion support are distinct.
- **Evidence thresholds are phase-specific.** Screening may tolerate proxies; commitment, signing, closing, and outcome actions demand stronger proof or explicit authority-backed exceptions.
- **Financial modeling and valuation are separate.** The model computes operating, cash, financing, and return cases; valuation applies methods, capital-structure bridges, security waterfalls, and risk interpretation.
- **Materiality is executable.** A rule produces an explicit consequence: block, warn, condition, reopen, trigger, escalate, accept, permit, or terminate.
- **Permission is not authority.** Access and editing rights never imply the power to approve, waive, accept risk, commit capital, or release funds.
- **Ownership is not approval.** Preparation, recommendation, approval, commitment, and funding are separately attributable.
- **Historical bases are immutable.** Decisions retain exact evidence, assumption, model, valuation, term, policy, authority, and condition versions.
- **Lineage drives staleness.** Material upstream change creates a staleness record and controlled recomputation; it does not mutate historical outputs.
- **Unhappy paths are first-class.** Decline, stall, failure, skip, backtrack, revival, partial outcome, and residual exposure have explicit contracts.
- **Structural logic is enforced; convention is configured.** Identity, lineage, authority, gates, staleness, and audit are structural. Templates, labels, thresholds, methods, cadence, and role composition are configurable.
- **Universal core, conditional extensions.** Transaction-specific objects activate only when their archetype or structure requires them.

## 3. Core ontology

### 3.1 Conceptual layers

- **Opportunity and exposure:** deal, company, organization, fund/vehicle, investment exposure, position, security, capital structure, sources and uses.
- **People and governance:** actor, role definition, role assignment, permission policy/evaluation, authority rule, approval, risk acceptance, delegation, recusal, dissent, gate, condition, exception.
- **Knowledge and analysis:** source-material set, document/version, evidence, question/register, assumption, risk, metric definition/observation, finding, thesis, challenge, reasoning record, evidence-sufficiency assessment.
- **Models and value:** analytical model, model case, valuation input/case, adjustment item, bridge analysis, value-creation plan.
- **Execution and portfolio:** execution-document set, legal agreement, covenant, governance right, closing record, capital event, monitoring record, re-underwriting trigger/record, outcome record.
- **Control and history:** workflow event, staleness record, immutable decision basis and supersession relationships.
- **Conditional extensions:** synergy/integration, add-on pipeline, carve-out perimeter and transition services, founder rollover, auction/vendor diligence, public-market transaction, shareholder approval, sponsor track record, key-person dependency.

### 3.2 Canonical entity catalog

| Entity ID | Name | Class | Status | Purpose |
| --- | --- | --- | --- | --- |
| ENT_DEAL | Deal Record | core_aggregate | canonical | Root aggregate and state-bearing identity for the workflow. |
| ENT_COMPANY | Company | party | canonical | Separates the operating subject from the transaction and investor exposure. |
| ENT_ORGANIZATION | Organization | party | canonical | Provides reusable party identity independent of deal-specific roles. |
| ENT_ACTOR | Actor | party | canonical | Supports accountability, access control, and approval traceability. |
| ENT_ROLE_ASSIGNMENT | Role Assignment | governance | canonical | Separates identity from responsibility, permission, and authority. |
| ENT_FUND_VEHICLE | Fund or Vehicle | economic | canonical | Represents the investor-side legal and economic container for exposure. |
| ENT_INVESTMENT_EXPOSURE | Investment Exposure | economic | canonical | Separates investor exposure from the operating company and instrument. |
| ENT_POSITION_RECORD | Position Record | portfolio | canonical | Supports monitoring, reporting, reconciliation, and outcome analysis. |
| ENT_ACCESS_GRANT | Access Grant | governance | canonical | Controls confidential information ingestion and use. |
| ENT_PERMISSION_POLICY | Permission Policy | governance | configurable | Provides object-level access control independent from approval authority. |
| ENT_AUTHORITY_RULE | Authority Rule | governance | configurable | Separates approval power from access permission. |
| ENT_APPROVAL_RECORD | Approval Record | governance | canonical | Provides non-repudiable authorization evidence. |
| ENT_WORKSTREAM_DEFINITION | Workstream Definition | configuration | configurable | Defines reusable workstream contracts used to instantiate deal-specific runs. |
| ENT_WORKSTREAM_RUN | Workstream Run | workflow_control | canonical | Tracks actual work and dependencies within a deal. |
| ENT_SOURCE_MATERIAL_SET | Source Material Set | knowledge | canonical | Groups incoming information by source, access basis, and purpose before claim extraction. |
| ENT_DOCUMENT_ARTIFACT | Document Artifact | knowledge | canonical | Preserves document identity separately from file versions and domain meaning. |
| ENT_DOCUMENT_VERSION | Document Version | knowledge | canonical | Supports exact evidence locators, version history, and decision-basis reproducibility. |
| ENT_EVIDENCE_ITEM | Evidence Item | knowledge | canonical | Provides the atomic traceability unit between sources and reasoning objects. |
| ENT_SCREENING_ASSESSMENT | Screening Assessment | analytical | canonical | Creates explicit proceed, decline, defer, or exception-proceed rationale before heavy diligence. |
| ENT_QUESTION_REGISTER | Question Register | knowledge | canonical | Converts uncertainty into assigned, testable, and gate-relevant work. |
| ENT_QUESTION | Question | knowledge | canonical | Creates traceable work between discomfort, diligence, and decisioning. |
| ENT_ASSUMPTION | Assumption | knowledge | canonical | Makes underwriting premises explicit and traceable through model, decision, and monitoring. |
| ENT_RISK | Risk | knowledge | canonical | Separates uncertainty from explicit downside exposure and control actions. |
| ENT_METRIC_DEFINITION | Metric Definition | analytical | canonical | Ensures observations, targets, forecasts, and variances use comparable definitions. |
| ENT_METRIC_OBSERVATION | Metric Observation | analytical | canonical | Provides comparable data for models, monitoring, variance analysis, and decisions. |
| ENT_DILIGENCE_FINDING | Diligence Finding | knowledge | canonical | Represents diligence output without equating a document with the finding. |
| ENT_INVESTMENT_THESIS | Investment Thesis | analytical | canonical | Connects assumptions, risks, value drivers, and decisions. |
| ENT_CHALLENGE_ASSESSMENT | Challenge Assessment | analytical | configurable | Supports configurable pre-decision challenge and negative-underwriting practice. |
| ENT_ANALYTICAL_MODEL | Analytical Model | analytical | canonical | Provides reusable model identity independent of individual cases. |
| ENT_MODEL_CASE | Model Case | analytical | canonical | Represents management, base, downside, upside, stress, actual, and re-underwritten scenarios. |
| ENT_VALUATION_INPUT | Valuation Input | analytical | canonical | Separates decision-critical valuation facts from model mechanics. |
| ENT_VALUATION_CASE | Valuation Case | analytical | canonical | Provides an immutable decision-basis snapshot for price, returns, and downside. |
| ENT_ADJUSTMENT_ITEM | Adjustment Item | analytical | canonical | Makes normalization and purchase-price adjustments explicit and auditable. |
| ENT_BRIDGE_ANALYSIS | Bridge Analysis | analytical | canonical | Explains causality and attribution rather than only endpoint values. |
| ENT_VALUE_CREATION_PLAN | Value Creation Plan | analytical | canonical | Connects underwriting claims to executable post-close actions and monitoring baselines. |
| ENT_CAPITAL_STRUCTURE | Capital Structure | economic | canonical | Provides the economic topology consumed by valuation, structuring, decisioning, and monitoring. |
| ENT_SECURITY | Security | economic | canonical | Represents the instrument through which value and risk are allocated. |
| ENT_SOURCES_USES | Sources and Uses | economic | canonical | Reconciles transaction funding and provides a closing control. |
| ENT_MATERIALITY_ASSESSMENT | Materiality Assessment | workflow_control | canonical | Centralizes configurable materiality logic and workflow consequence. |
| ENT_GATE | Gate | workflow_control | canonical | Makes transition authorization explicit and machine-evaluable. |
| ENT_DECISION_RECORD | Decision Record | governance | canonical | Preserves the historical basis for proceed, decline, approve, hold, follow-on, restructure, sell, impair, or write-off decisions. |
| ENT_RISK_ACCEPTANCE_RECORD | Risk Acceptance Record | governance | canonical | Allows continuation without pretending uncertainty has been resolved. |
| ENT_EXCEPTION_RECORD | Exception Record | workflow_control | canonical | Makes unhappy paths and controlled deviations first-class. |
| ENT_EXECUTION_DOCUMENT_SET | Execution Document Set | execution | canonical | Coordinates document readiness, conditions, and economic consistency. |
| ENT_LEGAL_AGREEMENT | Legal Agreement | execution | canonical | Represents legal rights and obligations independently from the file recording them. |
| ENT_COVENANT | Covenant | execution | canonical | Makes covenant monitoring and breach consequences executable. |
| ENT_GOVERNANCE_RIGHT | Governance Right | execution | canonical | Represents control and information rights affecting monitoring and authority. |
| ENT_CLOSING_RECORD | Closing Record | execution | canonical | Creates the authoritative transition from approved transaction to live exposure. |
| ENT_CAPITAL_EVENT | Capital Event | portfolio | canonical | Provides the event ledger from which position and outcome records are derived. |
| ENT_MONITORING_RECORD | Monitoring Record | portfolio | canonical | Provides the recurring evidence layer that confirms, challenges, or breaks the original case. |
| ENT_REUNDERWRITING_TRIGGER | Re-underwriting Trigger | portfolio | canonical | Provides the explicit bridge from monitoring or transaction events to re-underwriting. |
| ENT_REUNDERWRITING_RECORD | Re-underwriting Record | portfolio | canonical | Closes the outcome-calibration loop without overwriting original underwriting. |
| ENT_OUTCOME_RECORD | Outcome Record | portfolio | canonical | Records how the investment loop closed or remained open. |
| ENT_SYNERGY_PLAN | Synergy Plan | archetype_extension | archetype_extension | Supports merger, add-on, and integration underwriting. |
| ENT_INTEGRATION_PLAN | Integration Plan | archetype_extension | archetype_extension | Translates synergy and execution assumptions into milestones and dependencies. |
| ENT_ADD_ON_PIPELINE | Add-on Pipeline | archetype_extension | archetype_extension | Supports buy-and-build assumptions without treating uncommitted targets as realized value. |
| ENT_PLATFORM_ADD_ON_LINK | Platform–Add-on Link | archetype_extension | archetype_extension | Separates portfolio structure from standalone company identity. |
| ENT_SEPARATION_PERIMETER | Separation Perimeter | archetype_extension | archetype_extension | Defines what business is being underwritten and transferred. |
| ENT_TRANSITION_SERVICE_AGREEMENT | Transition Service Agreement | archetype_extension | archetype_extension | Represents operational dependencies and transition obligations in carve-outs. |
| ENT_STANDALONE_COST_BASELINE | Standalone Cost Baseline | archetype_extension | archetype_extension | Provides the operating and valuation basis for carve-out economics. |
| ENT_FOUNDER_ROLLOVER | Founder Rollover | archetype_extension | archetype_extension | Represents alignment and continuing ownership separately from purchase consideration. |
| ENT_AUCTION_PROCESS | Auction Process | archetype_extension | archetype_extension | Represents competitive process constraints shaping timing and information access. |
| ENT_VENDOR_DILIGENCE_PACKAGE | Vendor Diligence Package | archetype_extension | archetype_extension | Represents buyer evidence that must retain adviser scope and source provenance. |
| ENT_PUBLIC_MARKET_TRANSACTION | Public Market Transaction | archetype_extension | archetype_extension | Captures public-market-specific objects and gates without changing the universal deal core. |
| ENT_SHAREHOLDER_APPROVAL | Shareholder Approval | archetype_extension | archetype_extension | Represents a public-market or governance gate external to internal approval authority. |
| ENT_SPONSOR_TRACK_RECORD | Sponsor Track Record | archetype_extension | archetype_extension | Supports sponsor selection, alignment, and execution-risk assessment. |
| ENT_KEY_PERSON_DEPENDENCY | Key-Person Dependency | archetype_extension | archetype_extension | Makes founder, sponsor, and management concentration risk explicit. |
| ENT_WORKFLOW_EVENT | Workflow Event | immutable_event | canonical | Preserves deterministic history and idempotent execution |
| ENT_STALENESS_RECORD | Staleness Record | lineage_control | canonical | Controls recomputation without rewriting historical decision bases |
| ENT_CONDITION_RECORD | Condition Record | governance_control | canonical | Makes conditional authority explicit and testable |
| ENT_PERMISSION_EVALUATION_RECORD | Permission Evaluation Record | governance_control | canonical | Proves access control without conflating permission and authority |
| ENT_EVIDENCE_SUFFICIENCY_ASSESSMENT | Evidence Sufficiency Assessment | epistemic_control | canonical | Separates evidence existence from decision sufficiency |
| ENT_REASONING_RECORD | Reasoning Record | epistemic_record | canonical | Provides an auditable reasoning chain without treating documents as decisions |
| ENT_ROLE_DEFINITION | Role Definition | governance_configuration | canonical | Separates role design from a person or organization assignment |
| ENT_DELEGATION_RECORD | Delegation Record | governance_record | canonical | Supports continuity while preserving attribution and non-delegable constraints |
| ENT_RECUSAL_RECORD | Recusal Record | governance_record | canonical | Enforces conflict management and quorum recalculation |
| ENT_DISSENT_RECORD | Dissent Record | governance_record | canonical | Preserves minority reasoning and decision accountability |

### 3.3 Relationship model

Every relationship has directionality, cardinality, lifecycle constraints, workflow and workstream relevance, and where applicable permission, authority, and materiality consequences. The complete relationship contracts are in `ontology_schema_final.json` and `data_object_model.json`.

| Relationship ID | Source → Target | Cardinality | Definition |
| --- | --- | --- | --- |
| REL_001 | ENT_DEAL → ENT_COMPANY | 1:1..* | A deal concerns one or more operating companies, assets, or legally defined perimeters. |
| REL_002 | ENT_DEAL → ENT_ORGANIZATION | 1:1..* | An organization participates in a deal in a defined role such as sponsor, seller, buyer, lender, adviser, or administrator. |
| REL_003 | ENT_DEAL → ENT_FUND_VEHICLE | 1:1..* | A deal is allocated to one or more legal or accounting vehicles. |
| REL_004 | ENT_DEAL → ENT_INVESTMENT_EXPOSURE | 1:0..* | A deal may create one or more vehicle-security exposures. |
| REL_005 | ENT_INVESTMENT_EXPOSURE → ENT_FUND_VEHICLE | 0..*:1 | An investment exposure is held or committed by exactly one vehicle. |
| REL_006 | ENT_INVESTMENT_EXPOSURE → ENT_SECURITY | 0..*:1 | An investment exposure obtains its economics and rights from one security or instrument. |
| REL_007 | ENT_INVESTMENT_EXPOSURE → ENT_POSITION_RECORD | 1:0..* | An exposure has zero or more as-of position snapshots. |
| REL_008 | ENT_DEAL → ENT_WORKSTREAM_RUN | 1:0..* | A deal instantiates workstreams as required by state, archetype, risk, and materiality. |
| REL_009 | ENT_WORKSTREAM_RUN → ENT_WORKSTREAM_DEFINITION | 0..*:1 | A run implements one version of a reusable workstream definition. |
| REL_010 | ENT_ACTOR → ENT_ROLE_ASSIGNMENT | 1:0..* | An actor may hold multiple scoped roles over time. |
| REL_011 | ENT_ORGANIZATION → ENT_ROLE_ASSIGNMENT | 1:0..* | An organization may hold multiple deal or entity roles over time. |
| REL_012 | ENT_ROLE_ASSIGNMENT → ENT_DEAL | 0..*:0..1 | A role assignment may be scoped to one deal. |
| REL_013 | ENT_ACCESS_GRANT → ENT_SOURCE_MATERIAL_SET | 1:0..* | An access grant authorizes use of one or more material sets within its scope. |
| REL_014 | ENT_PERMISSION_POLICY → ENT_DOCUMENT_ARTIFACT | 0..*:0..* | A permission policy may govern actions on document artifacts based on role, classification, and context. |
| REL_015 | ENT_AUTHORITY_RULE → ENT_GATE | 1:0..* | An authority rule specifies the approval or override requirements for a gate. |
| REL_016 | ENT_APPROVAL_RECORD → ENT_AUTHORITY_RULE | 0..*:1 | An approval record evidences an authority decision under one rule version. |
| REL_017 | ENT_APPROVAL_RECORD → ENT_DECISION_RECORD | 1..*:1 | One or more approval records authorize or reject a decision. |
| REL_018 | ENT_SOURCE_MATERIAL_SET → ENT_DEAL | 0..*:1 | A material set is scoped to one deal. |
| REL_019 | ENT_SOURCE_MATERIAL_SET → ENT_DOCUMENT_ARTIFACT | 1:0..* | A material set contains zero or more logical documents. |
| REL_020 | ENT_DOCUMENT_ARTIFACT → ENT_DOCUMENT_VERSION | 1:1..* | A logical document has one or more immutable content versions. |
| REL_021 | ENT_EVIDENCE_ITEM → ENT_DOCUMENT_VERSION | 0..*:0..1 | An evidence item may be captured from a precise document version and locator. |
| REL_022 | ENT_EVIDENCE_ITEM → ENT_DEAL | 0..*:1 | An evidence item is evaluated within one deal context. |
| REL_023 | ENT_DEAL → ENT_QUESTION_REGISTER | 1:0..* | A deal may have multiple versioned question-register snapshots. |
| REL_024 | ENT_QUESTION_REGISTER → ENT_QUESTION | 1:0..* | A register version contains zero or more questions. |
| REL_025 | ENT_QUESTION → ENT_ASSUMPTION | 0..*:0..* | A question may test one or more assumptions, and an assumption may be tested by multiple questions. |
| REL_026 | ENT_EVIDENCE_ITEM → ENT_ASSUMPTION | 0..*:0..* | Evidence may increase support for an assumption. |
| REL_027 | ENT_EVIDENCE_ITEM → ENT_ASSUMPTION | 0..*:0..* | Evidence may challenge or break an assumption. |
| REL_028 | ENT_RISK → ENT_INVESTMENT_THESIS | 0..*:0..* | A risk may threaten one or more value-creation claims in a thesis. |
| REL_029 | ENT_ASSUMPTION → ENT_INVESTMENT_THESIS | 0..*:1..* | A thesis is supported by one or more explicit assumptions. |
| REL_030 | ENT_METRIC_OBSERVATION → ENT_METRIC_DEFINITION | 0..*:1 | Each observation uses exactly one metric-definition version. |
| REL_031 | ENT_METRIC_OBSERVATION → ENT_COMPANY | 0..*:0..1 | An observation may measure a company. |
| REL_032 | ENT_WORKSTREAM_RUN → ENT_DILIGENCE_FINDING | 1:0..* | A workstream run may produce zero or more diligence findings. |
| REL_033 | ENT_DILIGENCE_FINDING → ENT_EVIDENCE_ITEM | 0..*:1..* | A validated finding is supported by one or more evidence items. |
| REL_034 | ENT_DILIGENCE_FINDING → ENT_QUESTION | 0..*:0..* | A finding may answer, reframe, or leave unresolved a question. |
| REL_035 | ENT_DILIGENCE_FINDING → ENT_ASSUMPTION | 0..*:0..* | A finding may support, challenge, break, or supersede an assumption. |
| REL_036 | ENT_ANALYTICAL_MODEL → ENT_MODEL_CASE | 1:1..* | A model contains one or more versioned scenario cases. |
| REL_037 | ENT_MODEL_CASE → ENT_ASSUMPTION | 1:1..* | A model case uses one or more explicit assumption versions. |
| REL_038 | ENT_MODEL_CASE → ENT_METRIC_OBSERVATION | 1:0..* | A model case consumes measured or forecast observations as inputs or calibration points. |
| REL_039 | ENT_MODEL_CASE → ENT_VALUATION_CASE | 0..*:1..* | A valuation case uses one or more model cases. |
| REL_040 | ENT_VALUATION_INPUT → ENT_VALUATION_CASE | 0..*:1..* | A valuation case consumes one or more typed valuation inputs. |
| REL_041 | ENT_VALUATION_CASE → ENT_DECISION_RECORD | 0..*:0..* | A decision may rely on one or more valuation cases. |
| REL_042 | ENT_ADJUSTMENT_ITEM → ENT_VALUATION_INPUT | 0..*:0..1 | An accepted adjustment changes a metric or valuation input basis. |
| REL_043 | ENT_BRIDGE_ANALYSIS → ENT_VALUATION_CASE | 0..*:0..* | A bridge may explain the change between valuation or return states. |
| REL_044 | ENT_VALUE_CREATION_PLAN → ENT_ASSUMPTION | 1:1..* | A value-creation plan depends on explicit assumptions. |
| REL_045 | ENT_VALUE_CREATION_PLAN → ENT_METRIC_DEFINITION | 1:0..* | A plan identifies metrics used to measure initiative execution. |
| REL_046 | ENT_MATERIALITY_ASSESSMENT → ENT_DEAL | 0..*:1 | Every materiality assessment is evaluated in a deal context. |
| REL_047 | ENT_MATERIALITY_ASSESSMENT → ENT_GATE | 0..*:0..* | A materiality result may satisfy, warn, block, trigger, or reopen a gate. |
| REL_048 | ENT_GATE → ENT_DEAL | 0..*:1 | A satisfied or validly waived gate authorizes a specified state transition for a deal. |
| REL_049 | ENT_DECISION_RECORD → ENT_QUESTION_REGISTER | 0..*:0..1 | A decision references the question-register snapshot used at the decision time. |
| REL_050 | ENT_DECISION_RECORD → ENT_RISK_ACCEPTANCE_RECORD | 0..*:0..* | A decision may rely on explicit acceptance of residual risks or unresolved questions. |
| REL_051 | ENT_RISK_ACCEPTANCE_RECORD → ENT_RISK | 0..*:0..1 | A risk-acceptance record may accept one residual risk. |
| REL_052 | ENT_EXCEPTION_RECORD → ENT_GATE | 0..*:0..1 | An exception may waive or defer a specific gate requirement. |
| REL_053 | ENT_EXECUTION_DOCUMENT_SET → ENT_LEGAL_AGREEMENT | 1:0..* | An execution set contains zero or more legal agreements required for the transaction. |
| REL_054 | ENT_LEGAL_AGREEMENT → ENT_SECURITY | 0..*:0..* | A legal agreement may create, issue, amend, or govern one or more securities. |
| REL_055 | ENT_LEGAL_AGREEMENT → ENT_COVENANT | 1:0..* | A legal agreement may contain zero or more covenants. |
| REL_056 | ENT_LEGAL_AGREEMENT → ENT_GOVERNANCE_RIGHT | 1:0..* | A legal agreement may grant governance and information rights. |
| REL_057 | ENT_CLOSING_RECORD → ENT_EXECUTION_DOCUMENT_SET | 0..*:1 | A closing record confirms one signed execution-document set. |
| REL_058 | ENT_CLOSING_RECORD → ENT_INVESTMENT_EXPOSURE | 1:1..* | A closing may create one or more live investment exposures. |
| REL_059 | ENT_CAPITAL_EVENT → ENT_INVESTMENT_EXPOSURE | 0..*:1 | A capital event changes the economic state of one exposure. |
| REL_060 | ENT_MONITORING_RECORD → ENT_METRIC_OBSERVATION | 1:1..* | A monitoring record contains one or more period observations. |
| REL_061 | ENT_MONITORING_RECORD → ENT_MODEL_CASE | 0..*:0..1 | A monitoring record may compare actuals against an approved model-case baseline. |
| REL_062 | ENT_MONITORING_RECORD → ENT_REUNDERWRITING_TRIGGER | 1:0..* | A monitoring record may create zero or more re-underwriting triggers. |
| REL_063 | ENT_REUNDERWRITING_TRIGGER → ENT_REUNDERWRITING_RECORD | 1..*:1 | One or more validated triggers initiate a re-underwriting cycle. |
| REL_064 | ENT_REUNDERWRITING_RECORD → ENT_MODEL_CASE | 0..*:1 | A re-underwriting record compares current evidence with the original or prior approved model case. |
| REL_065 | ENT_REUNDERWRITING_RECORD → ENT_ASSUMPTION | 0..*:0..* | A re-underwriting record may confirm, break, or supersede assumptions. |
| REL_066 | ENT_REUNDERWRITING_RECORD → ENT_DECISION_RECORD | 0..*:0..1 | A re-underwriting record may produce a hold, follow-on, rescue, restructure, sell, impairment, or no-action decision. |
| REL_067 | ENT_DECISION_RECORD → ENT_OUTCOME_RECORD | 0..*:0..* | A decision may authorize or record an outcome. |
| REL_068 | ENT_CAPITAL_EVENT → ENT_OUTCOME_RECORD | 0..*:0..* | Capital events provide economic realization, impairment, or write-off evidence for outcomes. |
| REL_069 | ENT_OUTCOME_RECORD → ENT_DEAL | 0..*:1 | An outcome may close, partially close, restructure, or keep a deal open. |
| REL_070 | ENT_VALUE_CREATION_PLAN → ENT_SYNERGY_PLAN | 1:0..* | A value-creation plan may include a separately governed synergy plan. |
| REL_071 | ENT_SYNERGY_PLAN → ENT_INTEGRATION_PLAN | 0..*:0..1 | An integration plan executes and tracks the operational steps required to realize synergies. |
| REL_072 | ENT_VALUE_CREATION_PLAN → ENT_ADD_ON_PIPELINE | 1:0..1 | A buy-and-build plan may include an add-on pipeline. |
| REL_073 | ENT_PLATFORM_ADD_ON_LINK → ENT_COMPANY | 0..*:1 | A platform-add-on link identifies exactly one platform company. |
| REL_074 | ENT_PLATFORM_ADD_ON_LINK → ENT_COMPANY | 0..*:1 | A platform-add-on link identifies exactly one add-on company. |
| REL_075 | ENT_SEPARATION_PERIMETER → ENT_COMPANY | 0..*:1 | A separation perimeter defines the operating scope of a carve-out company. |
| REL_076 | ENT_TRANSITION_SERVICE_AGREEMENT → ENT_SEPARATION_PERIMETER | 0..*:1 | A transition-service agreement supports operating dependencies arising from a separation perimeter. |
| REL_077 | ENT_STANDALONE_COST_BASELINE → ENT_MODEL_CASE | 0..*:1..* | A standalone-cost baseline supplies cost assumptions to carve-out model cases. |
| REL_078 | ENT_FOUNDER_ROLLOVER → ENT_SECURITY | 0..*:1 | A founder rollover is implemented through one continuing security. |
| REL_079 | ENT_AUCTION_PROCESS → ENT_SOURCE_MATERIAL_SET | 1:0..* | An auction process may issue process materials and data-room sets. |
| REL_080 | ENT_VENDOR_DILIGENCE_PACKAGE → ENT_SOURCE_MATERIAL_SET | 0..*:1 | A vendor-diligence package is distributed within one source-material set. |
| REL_081 | ENT_PUBLIC_MARKET_TRANSACTION → ENT_SHAREHOLDER_APPROVAL | 1:0..* | A public-market transaction may require one or more holder approvals. |
| REL_082 | ENT_SPONSOR_TRACK_RECORD → ENT_RISK | 0..*:0..* | A sponsor track record may create or mitigate sponsor-execution risk. |
| REL_083 | ENT_KEY_PERSON_DEPENDENCY → ENT_RISK | 0..*:1 | A key-person dependency is represented as or linked to a risk object for decision and monitoring purposes. |
| REL_084 | ENT_DOCUMENT_ARTIFACT → ENT_DEAL | 0..*:0..1 | A deal-scoped document is associated with exactly one deal unless explicitly classified as reusable reference material. |
| REL_085 | ENT_DOCUMENT_ARTIFACT → ENT_ORGANIZATION | 0..*:0..1 | A document may identify the organization responsible for producing or issuing it. |
| REL_086 | ENT_DOCUMENT_ARTIFACT → ENT_INVESTMENT_THESIS | 0..*:0..* | A document may present one or more thesis versions without becoming the thesis object itself. |
| REL_087 | ENT_SCREENING_ASSESSMENT → ENT_DECISION_RECORD | 1:1 | A finalized screening assessment produces a proceed, decline, defer, or exception-proceed decision record. |
| REL_088 | ENT_MODEL_CASE → ENT_METRIC_OBSERVATION | 1:1..* | A model case produces forecast, target, stress, or re-underwritten metric observations. |
| REL_089 | ENT_PERMISSION_POLICY → ENT_DEAL | 0..*:0..* | A permission policy may govern actions on deal records and their inherited object scope. |
| REL_090 | ENT_WORKSTREAM_RUN → ENT_VALUATION_INPUT | 1:0..* | A workstream run may produce a decision-relevant input for valuation or return analysis. |
| REL_091 | ENT_WORKSTREAM_RUN → ENT_SECURITY | 0..*:0..* | Financing, structuring, tax, or legal work may propose or revise security terms before execution. |
| REL_092 | ENT_BRIDGE_ANALYSIS → ENT_INVESTMENT_THESIS | 0..*:0..* | A bridge analysis may decompose thesis value drivers, operating change, or entry-to-exit value into quantified components. |
| REL_093 | ENT_SYNERGY_PLAN → ENT_MODEL_CASE | 0..*:0..* | A synergy plan may provide timing, cost, and value assumptions to one or more model cases. |
| REL_094 | ENT_ADD_ON_PIPELINE → ENT_INVESTMENT_THESIS | 0..*:0..1 | An add-on pipeline may support a buy-and-build thesis, subject to probability and execution constraints. |
| REL_095 | ENT_EXCEPTION_RECORD → ENT_GATE | 0..*:0..1 | An effective exception may waive, defer, or alter one specifically identified gate condition. |
| REL_096 | ENT_DEAL → ENT_WORKFLOW_EVENT | 1:0..* | A deal owns an append-only sequence of workflow events. |
| REL_097 | ENT_STALENESS_RECORD → ENT_DOCUMENT_ARTIFACT | 1:1 | A staleness record identifies a downstream representation or analytical object that must be recomputed or reviewed. |
| REL_098 | ENT_APPROVAL_RECORD → ENT_CONDITION_RECORD | 1:0..* | An approval may impose one or more explicit, testable conditions. |
| REL_099 | ENT_GATE → ENT_CONDITION_RECORD | 1:0..* | A gate may require conditions to be satisfied or explicitly waived. |
| REL_100 | ENT_CONDITION_RECORD → ENT_EVIDENCE_ITEM | 1:0..* | Evidence supports satisfaction, failure, or waiver evaluation of a condition. |
| REL_101 | ENT_PERMISSION_POLICY → ENT_PERMISSION_EVALUATION_RECORD | 1:0..* | A permission policy is evaluated for a role assignment, object, and requested action. |
| REL_102 | ENT_PERMISSION_EVALUATION_RECORD → ENT_ROLE_ASSIGNMENT | 1:1 | A permission evaluation applies to one contextual role assignment. |
| REL_103 | ENT_ROLE_ASSIGNMENT → ENT_ROLE_DEFINITION | 0..*:1 | A contextual role assignment instantiates an effective role definition. |
| REL_104 | ENT_DELEGATION_RECORD → ENT_ROLE_ASSIGNMENT | 1:1 | A delegation record transfers listed actions within a bounded scope and period to a receiving assignment. |
| REL_105 | ENT_RECUSAL_RECORD → ENT_ROLE_ASSIGNMENT | 1:1 | A recusal excludes a contextual role assignment from specified governance actions. |
| REL_106 | ENT_DISSENT_RECORD → ENT_DECISION_RECORD | 0..*:1 | A dissent record preserves a reasoned disagreement with a collective decision. |
| REL_107 | ENT_QUESTION → ENT_EVIDENCE_SUFFICIENCY_ASSESSMENT | 1:0..* | A question may have phase-specific sufficiency assessments over its evidence set. |
| REL_108 | ENT_REASONING_RECORD → ENT_EVIDENCE_ITEM | 1:1..* | A reasoning record identifies the evidence used in an analytical transformation. |
| REL_109 | ENT_REASONING_RECORD → ENT_DILIGENCE_FINDING | 1:1..* | A reasoning record produces one or more findings. |
| REL_110 | ENT_REASONING_RECORD → ENT_ASSUMPTION | 1:0..* | A reasoning record may create, support, challenge, reject, or supersede an assumption. |
| REL_111 | ENT_REASONING_RECORD → ENT_MODEL_CASE | 1:0..* | A model reasoning record may produce a versioned model case. |
| REL_112 | ENT_REASONING_RECORD → ENT_VALUATION_CASE | 1:0..* | A valuation reasoning record may produce a versioned valuation case. |
| REL_113 | ENT_COVENANT → ENT_METRIC_OBSERVATION | 1:0..* | A covenant is evaluated against one or more metric observations. |
| REL_114 | ENT_MONITORING_RECORD → ENT_COVENANT | 1:0..* | A monitoring record may evaluate covenant compliance and headroom. |
| REL_115 | ENT_COVENANT → ENT_REUNDERWRITING_TRIGGER | 1:0..* | A covenant breach or headroom deterioration may create a re-underwriting trigger. |
| REL_116 | ENT_FOUNDER_ROLLOVER → ENT_GOVERNANCE_RIGHT | 1:0..* | A founder rollover may carry explicit governance rights and retained influence. |
| REL_117 | ENT_KEY_PERSON_DEPENDENCY → ENT_ROLE_ASSIGNMENT | 1:1..* | A key-person dependency concerns one or more contextual management or sponsor role assignments. |
| REL_118 | ENT_DECISION_RECORD → ENT_MODEL_CASE | 1:0..* | A decision identifies the exact model-case version used as its approved basis. |
| REL_119 | ENT_DECISION_RECORD → ENT_VALUATION_CASE | 1:0..* | A decision identifies the exact valuation-case version used as its approved basis. |
| REL_120 | ENT_DECISION_RECORD → ENT_ASSUMPTION | 1:0..* | A decision identifies the assumption versions relied upon. |
| REL_121 | ENT_MONITORING_RECORD → ENT_DECISION_RECORD | 0..*:1 | Monitoring compares actual evidence against an immutable approved decision baseline. |
| REL_122 | ENT_REUNDERWRITING_RECORD → ENT_DECISION_RECORD | 1:0..* | A re-underwriting record may support a successor decision without overwriting the prior decision. |
| REL_123 | ENT_ASSUMPTION → ENT_STALENESS_RECORD | 1:0..* | A changed assumption creates staleness records for affected downstream objects. |
| REL_124 | ENT_APPROVAL_RECORD → ENT_PERMISSION_EVALUATION_RECORD | 1:1..* | An authority action includes permission evaluations proving the actor may perform the action. |
| REL_125 | ENT_APPROVAL_RECORD → ENT_RECUSAL_RECORD | 1:0..* | An approval records recusals that affected participation or quorum. |
| REL_126 | ENT_APPROVAL_RECORD → ENT_DISSENT_RECORD | 1:0..* | An approval may record dissent from collective participants. |
| REL_127 | ENT_APPROVAL_RECORD → ENT_DELEGATION_RECORD | 1:0..* | An approval authorizes a scoped delegation where delegation is permitted. |

### 3.4 Provenance and version model

- Identity fields are immutable.
- Current projections may mutate only through controlled events.
- Evidence and document versions preserve source and permitted-use lineage.
- Assumptions, reasoning, models, valuations, findings, and analytical packages create successor versions.
- Decisions, approvals, risk acceptance, exceptions, commitments, and outcome snapshots are immutable.
- Supersession links preserve both the prior and successor object.
- Staleness records state which downstream objects require review or recomputation.

## 4. Canonical workflow

### 4.1 Primary-state resolution

The deal has one primary state selected by explicit state predicates and precedence. Parallel workstream status does not create a second primary state.

### 4.2 State contracts


#### S0_INTAKE — Opportunity intake and identity resolution

Create one canonical deal identity, target-company link, accountable owner, process type, and archetype context.

- **Entry:** `EXISTS ENT_DEAL WHERE ENT_DEAL.deal_id=$deal_id AND ENT_DEAL.current_state='S0_INTAKE' AND ENT_DEAL.status IN ['registered','active']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S0_INTAKE'`
- **Complete:** `ENT_DEAL.canonical_name IS NOT NULL AND ENT_DEAL.process_type IS NOT NULL AND ENT_DEAL.owner_role_assignment_id IS NOT NULL AND COUNT(REL_001 WHERE source_entity=$deal_id)=1 AND EXISTS ENT_ROLE_ASSIGNMENT WHERE ENT_ROLE_ASSIGNMENT.role_assignment_id=ENT_DEAL.owner_role_assignment_id AND ENT_ROLE_ASSIGNMENT.status='active'`
- **Exit:** A permitted transition from 'S0_INTAKE' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_ROLE_ASSIGNMENT
- **Required outputs:** ENT_DEAL
- **Hard blockers:** Canonical target company is not uniquely resolved.; ENT_DEAL.owner_role_assignment_id is null or does not reference an active deal owner.; ENT_DEAL.process_type is null.
- **Conditional blockers:** Archetype is unknown but process_type is known.
- **Authority:** An active ENT_AUTHORITY_RULE with action_type='other' or firm-configured intake authority must cover creation and ownership assignment; the owner is an active ENT_ROLE_ASSIGNMENT.
- **Permission:** An active ENT_PERMISSION_POLICY must allow the creating actor to create and administer ENT_DEAL.
- **Terminal:** False
- **Backtrack destinations:** None

#### S1_ACCESS_CLEARANCE — Access and confidentiality clearance

Establish lawful and policy-compliant rights to receive, store, review, and use source material.

- **Entry:** `ENT_DEAL.current_state='S1_ACCESS_CLEARANCE' AND ENT_DEAL.status='active'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S1_ACCESS_CLEARANCE'`
- **Complete:** `EXISTS ENT_ACCESS_GRANT WHERE ENT_ACCESS_GRANT.deal_id=$deal_id AND ENT_ACCESS_GRANT.status IN ['granted','waived_public_only'] AND ENT_ACCESS_GRANT.effective_from <= $now AND (ENT_ACCESS_GRANT.expires_at IS NULL OR ENT_ACCESS_GRANT.expires_at > $now)`
- **Exit:** A permitted transition from 'S1_ACCESS_CLEARANCE' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DEAL, ENT_ORGANIZATION, ENT_PERMISSION_POLICY, ENT_AUTHORITY_RULE
- **Required outputs:** ENT_ACCESS_GRANT, ENT_APPROVAL_RECORD
- **Hard blockers:** No effective ENT_ACCESS_GRANT covers the requested source and use scope.; ENT_PERMISSION_POLICY evaluates the requested action as deny.; Restricted-party or confidentiality conflict remains unresolved.
- **Conditional blockers:** Access is limited to 'waived_public_only'; confidential ingestion remains blocked.
- **Authority:** Issuance or waiver requires an ENT_APPROVAL_RECORD satisfying an active ENT_AUTHORITY_RULE; access denial may be recorded without investment authority but abandonment requires a decision.
- **Permission:** The requested view, store, export, share, and use_as_evidence actions must each be allowed by active ENT_PERMISSION_POLICY rules.
- **Terminal:** False
- **Backtrack destinations:** S0_INTAKE

#### S2_CASE_INGESTION — Source case ingestion

Create a traceable source-material set and extract structured evidence, initial claims, assumptions, and questions.

- **Entry:** `ENT_DEAL.current_state='S2_CASE_INGESTION' AND (EXISTS ENT_ACCESS_GRANT WHERE ENT_ACCESS_GRANT.deal_id=$deal_id AND ENT_ACCESS_GRANT.status IN ['granted','waived_public_only'])`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S2_CASE_INGESTION'`
- **Complete:** `EXISTS ENT_SOURCE_MATERIAL_SET WHERE ENT_SOURCE_MATERIAL_SET.deal_id=$deal_id AND ENT_SOURCE_MATERIAL_SET.index_status='indexed' AND ENT_SOURCE_MATERIAL_SET.provenance_quality!='unknown' AND COUNT(REL_019 WHERE source_entity=ENT_SOURCE_MATERIAL_SET.source_material_set_id)>=1`
- **Exit:** A permitted transition from 'S2_CASE_INGESTION' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DEAL, ENT_ACCESS_GRANT, ENT_DOCUMENT_ARTIFACT, ENT_DOCUMENT_VERSION
- **Required outputs:** ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_QUESTION
- **Hard blockers:** No indexed ENT_SOURCE_MATERIAL_SET exists.; Source use exceeds ENT_ACCESS_GRANT.permitted_use_scope.; Material source provenance is unknown without an active ENT_RISK_ACCEPTANCE_RECORD.
- **Conditional blockers:** A source set is incomplete but an ENT_MATERIALITY_ASSESSMENT.result IN ['warn','permit'] exists.
- **Authority:** Acceptance of materially incomplete or low-provenance materials requires ENT_RISK_ACCEPTANCE_RECORD backed by ENT_APPROVAL_RECORD.
- **Permission:** Each source, document version, and extracted evidence item must pass use_as_evidence permission evaluation.
- **Terminal:** False
- **Backtrack destinations:** S1_ACCESS_CLEARANCE

#### S3_SCREENING_ASSESSMENT — Initial assessment and resource-allocation screen

Decide whether to allocate diligence resources and define the initial investment thesis, risks, and required workstreams.

- **Entry:** `ENT_DEAL.current_state='S3_SCREENING_ASSESSMENT' AND EXISTS ENT_SOURCE_MATERIAL_SET WHERE ENT_SOURCE_MATERIAL_SET.deal_id=$deal_id AND ENT_SOURCE_MATERIAL_SET.index_status='indexed'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S3_SCREENING_ASSESSMENT'`
- **Complete:** `EXISTS ENT_SCREENING_ASSESSMENT WHERE ENT_SCREENING_ASSESSMENT.deal_id=$deal_id AND ENT_SCREENING_ASSESSMENT.status='final' AND ENT_SCREENING_ASSESSMENT.decision IN ['proceed','decline','defer','exception_proceed'] AND EXISTS ENT_DECISION_RECORD WHERE ENT_DECISION_RECORD.deal_id=$deal_id AND ENT_DECISION_RECORD.decision_type IN ['screen','proceed_to_diligence','decline'] AND ENT_DECISION_RECORD.status='effective'`
- **Exit:** A permitted transition from 'S3_SCREENING_ASSESSMENT' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_DEAL
- **Required outputs:** ENT_SCREENING_ASSESSMENT, ENT_INVESTMENT_THESIS, ENT_RISK, ENT_DECISION_RECORD, ENT_APPROVAL_RECORD
- **Hard blockers:** No final ENT_SCREENING_ASSESSMENT exists.; A proceed or exception_proceed decision lacks an effective ENT_APPROVAL_RECORD.; exception_proceed lacks an effective ENT_EXCEPTION_RECORD.
- **Conditional blockers:** Preliminary economics are absent but explicitly assessed non-material for the screening gate.
- **Authority:** Screening and exception-proceed actions must satisfy an active ENT_AUTHORITY_RULE.action_type='screen'.
- **Permission:** Reviewers must have view and use_as_evidence permission for all supporting objects.
- **Terminal:** False
- **Backtrack destinations:** S2_CASE_INGESTION

#### S4_QUESTION_PLANNING — Question engine and diligence planning

Convert uncertainty into owned questions, evidence requirements, and planned workstream runs.

- **Entry:** `ENT_DEAL.current_state='S4_QUESTION_PLANNING' AND EXISTS ENT_SCREENING_ASSESSMENT WHERE ENT_SCREENING_ASSESSMENT.deal_id=$deal_id AND ENT_SCREENING_ASSESSMENT.status='final' AND ENT_SCREENING_ASSESSMENT.decision IN ['proceed','exception_proceed']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S4_QUESTION_PLANNING'`
- **Complete:** `EXISTS ENT_QUESTION_REGISTER WHERE ENT_QUESTION_REGISTER.deal_id=$deal_id AND ENT_QUESTION_REGISTER.status='active' AND FOR_ALL ENT_QUESTION IN register WHERE ENT_QUESTION.criticality!='critical' OR (ENT_QUESTION.owner_workstream_run_id IS NOT NULL AND ENT_QUESTION.evidence_needed IS NOT NULL) OR ENT_QUESTION.status IN ['answered','risk_accepted','closed'] AND EXISTS ENT_WORKSTREAM_RUN WHERE ENT_WORKSTREAM_RUN.deal_id=$deal_id AND ENT_WORKSTREAM_RUN.status IN ['planned','active']`
- **Exit:** A permitted transition from 'S4_QUESTION_PLANNING' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_SCREENING_ASSESSMENT, ENT_INVESTMENT_THESIS, ENT_RISK, ENT_ASSUMPTION, ENT_EVIDENCE_ITEM
- **Required outputs:** ENT_QUESTION_REGISTER, ENT_QUESTION, ENT_WORKSTREAM_RUN
- **Hard blockers:** A critical ENT_QUESTION has no owner workstream and no effective risk acceptance.; No active ENT_QUESTION_REGISTER exists.; No required ENT_WORKSTREAM_RUN has been planned.
- **Conditional blockers:** Non-critical questions lack an owner but remain tracked.
- **Authority:** Risk acceptance requires ENT_RISK_ACCEPTANCE_RECORD and ENT_APPROVAL_RECORD under action_type='accept_risk'.
- **Permission:** Question and evidence visibility inherit deal and source restrictions; assignment does not grant source access.
- **Terminal:** False
- **Backtrack destinations:** S3_SCREENING_ASSESSMENT, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION

#### S5_DILIGENCE_ACTIVE — Parallel diligence workstreams active

Test questions, assumptions, risks, and transaction constraints through parallel workstream runs.

- **Entry:** `ENT_DEAL.current_state='S5_DILIGENCE_ACTIVE' AND EXISTS ENT_QUESTION_REGISTER WHERE ENT_QUESTION_REGISTER.deal_id=$deal_id AND ENT_QUESTION_REGISTER.status='active' AND EXISTS ENT_WORKSTREAM_RUN WHERE ENT_WORKSTREAM_RUN.deal_id=$deal_id AND ENT_WORKSTREAM_RUN.status='active'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S5_DILIGENCE_ACTIVE'`
- **Complete:** `FOR_ALL required ENT_WORKSTREAM_RUN WHERE ENT_WORKSTREAM_RUN.status IN ['completed','waived','cancelled'] AND FOR_ALL material ENT_DILIGENCE_FINDING WHERE ENT_DILIGENCE_FINDING.status IN ['validated','resolved','superseded'] AND (ENT_DILIGENCE_FINDING.decision_impact NOT IN ['block','reprice','restructure'] OR EXISTS effective ENT_RISK_ACCEPTANCE_RECORD OR mitigation successor) AND no critical ENT_QUESTION.status IN ['open','blocked']`
- **Exit:** A permitted transition from 'S5_DILIGENCE_ACTIVE' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_QUESTION_REGISTER, ENT_QUESTION, ENT_WORKSTREAM_RUN, ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM
- **Required outputs:** ENT_WORKSTREAM_RUN, ENT_DILIGENCE_FINDING, ENT_ASSUMPTION, ENT_RISK, ENT_VALUATION_INPUT
- **Hard blockers:** A required ENT_WORKSTREAM_RUN is active, blocked, or reopened.; A high or critical finding with decision_impact='block' lacks mitigation or effective risk acceptance.; A critical question remains open or blocked.; Evidence required by a model-critical assumption is missing or not permitted.
- **Conditional blockers:** A material tax, financing, or operational finding conditionally blocks only the dependent output identified by the graph.
- **Authority:** Waiver, risk acceptance, and materiality override require active authority rules and effective approval records.
- **Permission:** Each workstream run may consume only permitted sources and evidence; privilege restrictions are preserved downstream.
- **Terminal:** False
- **Backtrack destinations:** S4_QUESTION_PLANNING, S3_SCREENING_ASSESSMENT

#### S6_UNDERWRITING_VALUATION — Model, valuation and return underwriting

Transform tested assumptions, metrics, structure, and security terms into versioned model and valuation cases.

- **Entry:** `ENT_DEAL.current_state='S6_UNDERWRITING_VALUATION' AND EXISTS ENT_ANALYTICAL_MODEL WHERE ENT_ANALYTICAL_MODEL.deal_id=$deal_id AND ENT_ANALYTICAL_MODEL.status IN ['draft','reviewed','approved']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S6_UNDERWRITING_VALUATION'`
- **Complete:** `EXISTS ENT_MODEL_CASE JOIN ENT_ANALYTICAL_MODEL WHERE ENT_ANALYTICAL_MODEL.deal_id=$deal_id AND ENT_MODEL_CASE.status IN ['reviewed','approved'] AND EXISTS ENT_VALUATION_CASE WHERE ENT_VALUATION_CASE.deal_id=$deal_id AND ENT_VALUATION_CASE.status='decision_ready' AND FOR_ALL referenced ENT_VALUATION_INPUT WHERE ENT_VALUATION_INPUT.verification_status NOT IN ['unverified','disputed','superseded'] OR (ENT_VALUATION_INPUT.materiality_level NOT IN ['material','critical'] AND effective acceptance exists) AND no active ENT_STALENESS_RECORD object blocks the decision package`
- **Exit:** A permitted transition from 'S6_UNDERWRITING_VALUATION' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_ASSUMPTION, ENT_METRIC_OBSERVATION, ENT_VALUATION_INPUT, ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_WORKSTREAM_RUN, ENT_DILIGENCE_FINDING
- **Required outputs:** ENT_ANALYTICAL_MODEL, ENT_MODEL_CASE, ENT_VALUATION_CASE, ENT_BRIDGE_ANALYSIS, ENT_MATERIALITY_ASSESSMENT
- **Hard blockers:** No ENT_VALUATION_CASE.status='decision_ready'.; A material or critical ENT_VALUATION_INPUT is unverified, disputed, or stale.; A model-critical ENT_ASSUMPTION.status IN ['proposed','challenged','broken'] without effective risk acceptance.; Required security or capital-structure terms are absent.
- **Conditional blockers:** A non-material input remains a management or sponsor claim with result='warn'.
- **Authority:** Model review and any acceptance of unsupported material inputs require active authority rules and effective approvals.
- **Permission:** Model inputs and outputs inherit the most restrictive permissions of their source evidence; decision users require view and use_as_evidence permission.
- **Terminal:** False
- **Backtrack destinations:** S5_DILIGENCE_ACTIVE, S4_QUESTION_PLANNING

#### S7_INVESTMENT_DECISION — Investment decision and approval gate

Create an immutable decision basis and approve, reject, defer, or condition the investment action.

- **Entry:** `ENT_DEAL.current_state='S7_INVESTMENT_DECISION' AND EXISTS ENT_VALUATION_CASE WHERE ENT_VALUATION_CASE.deal_id=$deal_id AND ENT_VALUATION_CASE.status='decision_ready'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S7_INVESTMENT_DECISION'`
- **Complete:** `EXISTS ENT_DECISION_RECORD WHERE ENT_DECISION_RECORD.deal_id=$deal_id AND ENT_DECISION_RECORD.decision_type='investment_approval' AND ENT_DECISION_RECORD.status='effective' AND ENT_DECISION_RECORD.decision IN ['approved','rejected','conditional','deferred'] AND COUNT(REL_017 WHERE target_entity=ENT_DECISION_RECORD.decision_record_id)>=1 AND FOR_ALL critical questions WHERE status NOT IN ['open','blocked'] OR effective risk acceptance exists`
- **Exit:** A permitted transition from 'S7_INVESTMENT_DECISION' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_VALUATION_CASE, ENT_MODEL_CASE, ENT_QUESTION_REGISTER, ENT_RISK, ENT_DILIGENCE_FINDING, ENT_GATE, ENT_AUTHORITY_RULE
- **Required outputs:** ENT_DECISION_RECORD, ENT_APPROVAL_RECORD, ENT_RISK_ACCEPTANCE_RECORD, ENT_QUESTION_REGISTER, ENT_GATE
- **Hard blockers:** The decision gate lacks an effective approval under the applicable authority rule.; The valuation case or decision snapshot is stale.; A critical question remains open or blocked without effective risk acceptance.; A material finding has no decision treatment.
- **Conditional blockers:** The decision is conditional and one or more conditions remain unsatisfied; execution drafting may proceed but signing cannot.
- **Authority:** The action must match ENT_AUTHORITY_RULE.action_type='approve_investment'; approval is evidenced by ENT_APPROVAL_RECORD.
- **Permission:** All decision participants require permission to view the decision snapshot and supporting evidence; restricted evidence may be summarized but not silently omitted.
- **Terminal:** False
- **Backtrack destinations:** S6_UNDERWRITING_VALUATION, S5_DILIGENCE_ACTIVE, S4_QUESTION_PLANNING

#### S8_EXECUTION_DOCUMENTATION — Structuring, documentation and signing

Translate approved economics, rights, obligations, and conditions into versioned executable agreements.

- **Entry:** `ENT_DEAL.current_state='S8_EXECUTION_DOCUMENTATION' AND EXISTS ENT_DECISION_RECORD WHERE ENT_DECISION_RECORD.deal_id=$deal_id AND ENT_DECISION_RECORD.decision_type IN ['investment_approval','follow_on','rescue','restructure','sell'] AND ENT_DECISION_RECORD.decision IN ['approved','conditional'] AND ENT_DECISION_RECORD.status='effective'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S8_EXECUTION_DOCUMENTATION'`
- **Complete:** `EXISTS ENT_EXECUTION_DOCUMENT_SET WHERE ENT_EXECUTION_DOCUMENT_SET.deal_id=$deal_id AND ENT_EXECUTION_DOCUMENT_SET.status IN ['signed','complete'] AND ENT_EXECUTION_DOCUMENT_SET.economic_consistency_status IN ['consistent','exception_approved'] AND all required condition records or structured conditions are satisfied or effectively waived`
- **Exit:** A permitted transition from 'S8_EXECUTION_DOCUMENTATION' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DECISION_RECORD, ENT_APPROVAL_RECORD, ENT_SECURITY, ENT_CAPITAL_STRUCTURE, ENT_DILIGENCE_FINDING, ENT_GATE
- **Required outputs:** ENT_EXECUTION_DOCUMENT_SET, ENT_LEGAL_AGREEMENT, ENT_DOCUMENT_ARTIFACT, ENT_DOCUMENT_VERSION, ENT_COVENANT, ENT_GOVERNANCE_RIGHT, ENT_GATE
- **Hard blockers:** Execution terms materially differ from the effective decision basis without reapproval.; Required legal agreements are unsigned or not final.; A material legal, tax, permission, or authority issue remains unresolved.; The execution set is economically inconsistent.
- **Conditional blockers:** A conditional approval condition remains open; drafting may continue but signing or close is blocked.
- **Authority:** Signing requires ENT_AUTHORITY_RULE.action_type='sign' and effective ENT_APPROVAL_RECORD; deviation waivers require action_type='waive'.
- **Permission:** Only permitted actors may view, edit, share, or sign restricted agreements; legal privilege and confidentiality boundaries persist.
- **Terminal:** False
- **Backtrack destinations:** S7_INVESTMENT_DECISION, S6_UNDERWRITING_VALUATION, S5_DILIGENCE_ACTIVE

#### S9_CLOSING_ADMINISTRATION — Closing and capital administration

Confirm legal effectiveness, funding, security issuance, exposure creation, and a reconciled monitoring baseline.

- **Entry:** `ENT_DEAL.current_state='S9_CLOSING_ADMINISTRATION' AND EXISTS ENT_EXECUTION_DOCUMENT_SET WHERE ENT_EXECUTION_DOCUMENT_SET.deal_id=$deal_id AND ENT_EXECUTION_DOCUMENT_SET.status IN ['signed','complete']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S9_CLOSING_ADMINISTRATION'`
- **Complete:** `EXISTS ENT_CLOSING_RECORD WHERE ENT_CLOSING_RECORD.deal_id=$deal_id AND ENT_CLOSING_RECORD.status IN ['closed','partial'] AND (ENT_CLOSING_RECORD.status!='closed' OR COUNT(ENT_CLOSING_RECORD.created_exposure_ids)>=1) AND FOR_ALL created exposures WHERE ENT_INVESTMENT_EXPOSURE.status IN ['partially_funded','funded','partially_realized','realized'] AND EXISTS ENT_POSITION_RECORD WHERE ENT_POSITION_RECORD.investment_exposure_id IN created exposures AND ENT_POSITION_RECORD.status IN ['reconciled','final']`
- **Exit:** A permitted transition from 'S9_CLOSING_ADMINISTRATION' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_EXECUTION_DOCUMENT_SET, ENT_CLOSING_RECORD, ENT_SECURITY, ENT_APPROVAL_RECORD
- **Required outputs:** ENT_CLOSING_RECORD, ENT_INVESTMENT_EXPOSURE, ENT_CAPITAL_EVENT, ENT_POSITION_RECORD
- **Hard blockers:** Closing conditions are unsatisfied and not effectively waived.; Funds flow is unbalanced or funding lacks authority.; Issued security or created exposure is not recorded.; A closed exposure lacks a reconciled position record.
- **Conditional blockers:** ENT_CLOSING_RECORD.status='partial'; only funded or issued components may enter monitoring.
- **Authority:** Closing requires ENT_AUTHORITY_RULE.action_type='close'; commitment or funding requires applicable commit_capital authority and effective approvals.
- **Permission:** Banking, ownership, and capital data require restricted permissions; creation of exposure does not broaden access.
- **Terminal:** False
- **Backtrack destinations:** S8_EXECUTION_DOCUMENTATION, S7_INVESTMENT_DECISION

#### S10_MONITORING — Monitoring and portfolio reporting

Maintain a versioned view of live exposure against the approved underwriting baseline and detect actionable variance.

- **Entry:** `ENT_DEAL.current_state='S10_MONITORING' AND EXISTS ENT_INVESTMENT_EXPOSURE WHERE ENT_INVESTMENT_EXPOSURE.deal_id=$deal_id AND ENT_INVESTMENT_EXPOSURE.status IN ['partially_funded','funded','partially_realized','impaired']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S10_MONITORING'`
- **Complete:** `EXISTS ENT_MONITORING_RECORD WHERE ENT_MONITORING_RECORD.deal_id=$deal_id AND ENT_MONITORING_RECORD.status IN ['final','revised'] AND FOR_ALL referenced ENT_METRIC_OBSERVATION WHERE ENT_METRIC_OBSERVATION.status IN ['verified','disputed'] AND every material variance, covenant, liquidity, governance, or exit signal has either a validated or dismissed ENT_REUNDERWRITING_TRIGGER`
- **Exit:** A permitted transition from 'S10_MONITORING' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD, ENT_MODEL_CASE, ENT_METRIC_DEFINITION
- **Required outputs:** ENT_MONITORING_RECORD, ENT_METRIC_OBSERVATION, ENT_REUNDERWRITING_TRIGGER, ENT_RISK
- **Hard blockers:** A material or critical ENT_REUNDERWRITING_TRIGGER is validated but not acted.; Required monitoring metrics are absent without documented limitation.; A live exposure has no current reconciled position record.
- **Conditional blockers:** A disputed metric observation affects only a non-material monitoring conclusion.
- **Authority:** Dismissal of a critical trigger or acceptance of a material monitoring risk requires applicable authority and approval.
- **Permission:** Board, lender, and company materials retain source restrictions; monitoring users require permission to use them as evidence.
- **Terminal:** False
- **Backtrack destinations:** S9_CLOSING_ADMINISTRATION, S11_REUNDERWRITING, S12_EXIT_REALIZATION

#### S11_REUNDERWRITING — Re-underwriting and action selection

Compare current evidence with the original decision baseline and select hold, follow-on, rescue, restructure, sell, impair, or write-off action.

- **Entry:** `ENT_DEAL.current_state='S11_REUNDERWRITING' AND EXISTS ENT_REUNDERWRITING_TRIGGER WHERE ENT_REUNDERWRITING_TRIGGER.deal_id=$deal_id AND ENT_REUNDERWRITING_TRIGGER.status='validated'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S11_REUNDERWRITING'`
- **Complete:** `EXISTS ENT_REUNDERWRITING_RECORD WHERE ENT_REUNDERWRITING_RECORD.deal_id=$deal_id AND ENT_REUNDERWRITING_RECORD.status IN ['approved','closed'] AND EXISTS ENT_DECISION_RECORD WHERE ENT_DECISION_RECORD.deal_id=$deal_id AND ENT_DECISION_RECORD.decision_record_id=ENT_REUNDERWRITING_RECORD.decision_record_id AND ENT_DECISION_RECORD.status='effective'`
- **Exit:** A permitted transition from 'S11_REUNDERWRITING' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_REUNDERWRITING_TRIGGER, ENT_REUNDERWRITING_RECORD, ENT_MODEL_CASE, ENT_METRIC_OBSERVATION, ENT_INVESTMENT_EXPOSURE
- **Required outputs:** ENT_REUNDERWRITING_RECORD, ENT_MODEL_CASE, ENT_VALUATION_CASE, ENT_DECISION_RECORD, ENT_OUTCOME_RECORD
- **Hard blockers:** The review does not reference an original model case.; A material trigger has no explicit option analysis.; A follow-on, rescue, or restructure recommendation lacks old-money versus new-money analysis when applicable.; No effective decision record exists.
- **Conditional blockers:** A non-critical trigger remains under further diligence; no action decision is deferred with a due date.
- **Authority:** The selected action must satisfy its corresponding authority rule: approve_follow_on, sell, impair, write_off, accept_risk, or other configured action.
- **Permission:** Reviewers need permission to access both historical decision snapshots and current evidence; later permissions do not rewrite historical access records.
- **Terminal:** False
- **Backtrack destinations:** S10_MONITORING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION

#### S12_EXIT_REALIZATION — Exit, realization, impairment, and residual-exposure resolution

Execute or record a sale, partial realization, impairment, write-off, or failed exit and determine residual exposure.

- **Entry:** `ENT_DEAL.current_state='S12_EXIT_REALIZATION' AND EXISTS ENT_DECISION_RECORD WHERE ENT_DECISION_RECORD.deal_id=$deal_id AND ENT_DECISION_RECORD.decision_type IN ['sell','exit','impair','write_off'] AND ENT_DECISION_RECORD.status='effective'`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S12_EXIT_REALIZATION'`
- **Complete:** `EXISTS ENT_OUTCOME_RECORD WHERE ENT_OUTCOME_RECORD.deal_id=$deal_id AND ENT_OUTCOME_RECORD.status IN ['final','revised'] AND ENT_OUTCOME_RECORD.residual_exposure_status IN ['none','live','contingent','unknown'] AND (ENT_OUTCOME_RECORD.outcome_type NOT IN ['partial_realization','full_realization'] OR EXISTS ENT_CAPITAL_EVENT WHERE ENT_CAPITAL_EVENT.investment_exposure_id IN ENT_OUTCOME_RECORD.investment_exposure_ids AND ENT_CAPITAL_EVENT.event_type='sale_proceeds' AND ENT_CAPITAL_EVENT.status='confirmed')`
- **Exit:** A permitted transition from 'S12_EXIT_REALIZATION' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DECISION_RECORD, ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD, ENT_APPROVAL_RECORD, ENT_VALUATION_CASE
- **Required outputs:** ENT_OUTCOME_RECORD, ENT_CAPITAL_EVENT, ENT_POSITION_RECORD, ENT_INVESTMENT_EXPOSURE
- **Hard blockers:** Outcome authority is absent.; Proceeds, write-off, or impairment effects are not reconciled.; Residual exposure is unknown without a materiality and action assessment.; A partial outcome has no monitoring destination.
- **Conditional blockers:** A failed sale process returns the exposure to monitoring with an updated exit assumption.
- **Authority:** Sale, impairment, and write-off require the matching active authority rule and effective approval.
- **Permission:** Outcome, bidder, proceeds, and transaction materials remain governed by object-specific permission policy.
- **Terminal:** False
- **Backtrack destinations:** S11_REUNDERWRITING, S10_MONITORING, S9_CLOSING_ADMINISTRATION

#### S13_CLOSED_ARCHIVE — Closed-position archive

Preserve the immutable decision, analytical, execution, monitoring, and outcome lineage after exposure is fully resolved.

- **Entry:** `ENT_DEAL.current_state='S13_CLOSED_ARCHIVE' AND ENT_DEAL.status IN ['closed','realized','written_off']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'S13_CLOSED_ARCHIVE'`
- **Complete:** `EXISTS ENT_OUTCOME_RECORD WHERE ENT_OUTCOME_RECORD.outcome_record_id=ENT_DEAL.current_outcome_record_id AND ENT_OUTCOME_RECORD.status IN ['final','revised'] AND ENT_OUTCOME_RECORD.residual_exposure_status='none' AND NOT EXISTS ENT_INVESTMENT_EXPOSURE WHERE ENT_INVESTMENT_EXPOSURE.deal_id=$deal_id AND ENT_INVESTMENT_EXPOSURE.status IN ['proposed','approved','partially_funded','funded','partially_realized']`
- **Exit:** A permitted transition from 'S13_CLOSED_ARCHIVE' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DEAL, ENT_OUTCOME_RECORD, ENT_POSITION_RECORD
- **Required outputs:** ENT_DEAL, ENT_OUTCOME_RECORD
- **Hard blockers:** A live or partially realized exposure remains.; Residual exposure status is not 'none'.; Final outcome or position reconciliation is absent.
- **Conditional blockers:** None
- **Authority:** Permanent closure requires applicable close, sell, impair, or write-off authority reflected in the underlying decision and approval records.
- **Permission:** Archive access is read-only and governed by retention, confidentiality, and evidence-use policies.
- **Terminal:** True
- **Backtrack destinations:** S10_MONITORING, S11_REUNDERWRITING, S12_EXIT_REALIZATION

#### SX_TERMINATED_STALLED_DECLINED — Terminated, stalled, or declined process

Preserve the reason, last active state, evidence, and explicit revival conditions for a non-live or interrupted process.

- **Entry:** `ENT_DEAL.current_state='SX_TERMINATED_STALLED_DECLINED' AND ENT_DEAL.status IN ['declined','stalled','abandoned']`
- **Active:** `ENT_DEAL.deal_id = $deal_id AND ENT_DEAL.current_state = 'SX_TERMINATED_STALLED_DECLINED'`
- **Complete:** `EXISTS ENT_DECISION_RECORD WHERE ENT_DECISION_RECORD.deal_id=$deal_id AND ENT_DECISION_RECORD.decision_type IN ['decline','other'] AND ENT_DECISION_RECORD.status='effective' OR EXISTS ENT_OUTCOME_RECORD WHERE ENT_OUTCOME_RECORD.deal_id=$deal_id AND ENT_OUTCOME_RECORD.outcome_type='termination' AND ENT_OUTCOME_RECORD.status IN ['final','revised']`
- **Exit:** A permitted transition from 'SX_TERMINATED_STALLED_DECLINED' has atomically updated ENT_DEAL.current_state to its target state after all guards, gates, authority, permission, and materiality checks passed.
- **Required inputs:** ENT_DEAL, ENT_DECISION_RECORD, ENT_OUTCOME_RECORD, ENT_EXCEPTION_RECORD
- **Required outputs:** ENT_DEAL, ENT_DECISION_RECORD, ENT_OUTCOME_RECORD
- **Hard blockers:** A live investment exposure exists but no monitoring or outcome treatment is active.; No authoritative reason or revival condition is recorded.
- **Conditional blockers:** The process is stalled with a configured review date rather than permanently terminated.
- **Authority:** Decline, abandonment, or permanent termination requires configured decision authority; operational stall may be recorded by the accountable owner but cannot waive live-exposure duties.
- **Permission:** Historical objects remain subject to original permissions; revival requires current permission evaluation.
- **Terminal:** True
- **Backtrack destinations:** S0_INTAKE, S2_CASE_INGESTION, S4_QUESTION_PLANNING, S10_MONITORING

### 4.3 Transition contracts

Every transition is caused by an explicit event or canonical status change. The engine evaluates its guard, gate, permissions, authority, materiality, conditions, exception path, retry rule, skip/revival behavior, and idempotency key before updating the primary-state projection.

| ID | Source | Target | Trigger | Guard | Gate | Enforcement |
| --- | --- | --- | --- | --- | --- | --- |
| T001 | S0_INTAKE | S1_ACCESS_CLEARANCE | DEAL_IDENTITY_RESOLVED_ACCESS_REQUIRED | S0 completion predicate is true AND confidential or restricted source material is expected. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T002 | S0_INTAKE | S2_CASE_INGESTION | DEAL_IDENTITY_RESOLVED_PUBLIC_ROUTE | S0 completion predicate is true AND all intended sources are public AND ENT_EXCEPTION_RECORD.effect IN ['allow','temporary_override'] identifies public-only ingestion. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T003 | S1_ACCESS_CLEARANCE | S2_CASE_INGESTION | ACCESS_GRANTED | ENT_ACCESS_GRANT is effective, covers the intended use scope, and permission evaluation allows ingestion. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T004 | S2_CASE_INGESTION | S3_SCREENING_ASSESSMENT | SOURCE_SET_INDEXED | S2 completion predicate is true and material provenance limitations are either absent or explicitly accepted. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T005 | S3_SCREENING_ASSESSMENT | S4_QUESTION_PLANNING | SCREEN_PROCEED | A matching effective ENT_DECISION_RECORD and ENT_APPROVAL_RECORD exist; exception_proceed also has effective ENT_EXCEPTION_RECORD. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T006 | S4_QUESTION_PLANNING | S5_DILIGENCE_ACTIVE | WORKSTREAM_RUNS_ACTIVATED | S4 completion predicate is true and every activated run has an active owner role assignment and permitted source access. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T007 | S5_DILIGENCE_ACTIVE | S4_QUESTION_PLANNING | MATERIAL_FINDING_CREATES_QUESTION | A materiality assessment result='reopen' OR the finding changes a thesis, risk, assumption, valuation input, or required evidence. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T008 | S5_DILIGENCE_ACTIVE | S6_UNDERWRITING_VALUATION | DILIGENCE_DECISION_BASIS_READY | S5 completion predicate is true; every waiver is effective and every material finding has decision treatment. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T009 | S6_UNDERWRITING_VALUATION | S4_QUESTION_PLANNING | MODEL_CRITICAL_GAP_DETECTED | The input or linked assumption is material or critical and changes decision outputs or downside. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T010 | S6_UNDERWRITING_VALUATION | S7_INVESTMENT_DECISION | VALUATION_DECISION_READY | S6 completion predicate is true and the decision snapshot has no unresolved material staleness. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T011 | S7_INVESTMENT_DECISION | S8_EXECUTION_DOCUMENTATION | INVESTMENT_APPROVED | S7 completion predicate is true and conditional items are explicitly represented in condition_set or ENT_CONDITION_RECORD objects. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T012 | S8_EXECUTION_DOCUMENTATION | S7_INVESTMENT_DECISION | MATERIAL_TERMS_DEVIATION | A materiality assessment result IN ['block','reopen'] OR a changed security, governance, tax, or economic term differs from the effective decision basis. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T013 | S8_EXECUTION_DOCUMENTATION | S9_CLOSING_ADMINISTRATION | EXECUTION_SET_SIGNED | S8 completion predicate is true and all signing conditions are satisfied or explicitly waived. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T014 | S9_CLOSING_ADMINISTRATION | S10_MONITORING | EXPOSURE_OPENED | S9 completion predicate is true and at least one created exposure remains live. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T015 | S10_MONITORING | S11_REUNDERWRITING | REUNDERWRITING_TRIGGER_VALIDATED | ENT_REUNDERWRITING_TRIGGER.severity IN ['material','critical'] OR trigger_type creates a new capital, covenant, liquidity, exit, or action decision. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T016 | S11_REUNDERWRITING | S10_MONITORING | HOLD_OR_NO_ACTION_APPROVED | ENT_REUNDERWRITING_RECORD.status IN ['approved','closed'] AND the exposure remains live AND revised monitoring actions are recorded. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T017 | S11_REUNDERWRITING | S8_EXECUTION_DOCUMENTATION | FOLLOW_ON_RESCUE_OR_RESTRUCTURE_APPROVED | The review contains option analysis and, when applicable, old_money_new_money_analysis; authority approval is effective. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T018 | S11_REUNDERWRITING | S12_EXIT_REALIZATION | OUTCOME_ACTION_APPROVED | The selected outcome action has an effective approval and current valuation or impairment basis; residual exposure assessment is initiated. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T019 | S12_EXIT_REALIZATION | S9_CLOSING_ADMINISTRATION | REALIZATION_REQUIRES_ADMINISTRATION | The outcome includes proceeds, impairment, write-off, or a capital-structure change requiring exposure and position reconciliation. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T020 | S12_EXIT_REALIZATION | S10_MONITORING | PARTIAL_OR_FAILED_EXIT_RETURNS_TO_MONITORING | Outcome type is partial_realization OR exit process failed or was deferred AND a live or contingent exposure remains. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T021 | S9_CLOSING_ADMINISTRATION | S13_CLOSED_ARCHIVE | FINAL_EXPOSURE_RECONCILED | No live or partially realized exposure exists, the final outcome has residual_exposure_status='none', and S13 completion predicate is true. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T022 | S3_SCREENING_ASSESSMENT | SX_TERMINATED_STALLED_DECLINED | SCREEN_DECLINED | A final screening assessment has decision='decline' and the deal has no live exposure. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T023 | S3_SCREENING_ASSESSMENT | S3_SCREENING_ASSESSMENT | SCREEN_DEFERRED | The decision condition_set specifies a review trigger or due date and no proceed authority exists. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T024 | S1_ACCESS_CLEARANCE | SX_TERMINATED_STALLED_DECLINED | ACCESS_DENIED_AND_PROCESS_ABANDONED | No permitted public-only route exists and an effective decline or abandonment decision is recorded. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T025 | S5_DILIGENCE_ACTIVE | SX_TERMINATED_STALLED_DECLINED | DILIGENCE_ABANDONED | A validated material finding, lost process, inability to obtain critical evidence, or owner decision ends diligence and no live exposure exists. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T026 | S5_DILIGENCE_ACTIVE | S4_QUESTION_PLANNING | UNRESOLVED_CRITICAL_QUESTION | ENT_QUESTION.criticality='critical' AND evidence_needed is unmet AND no effective risk acceptance exists. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T027 | S5_DILIGENCE_ACTIVE | S4_QUESTION_PLANNING | MATERIAL_ASSUMPTION_REJECTED | The assumption is material to thesis, model, valuation, structure, or decision and no successor assumption is accepted. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T028 | S6_UNDERWRITING_VALUATION | S5_DILIGENCE_ACTIVE | MODEL_NOT_DECISION_READY | A material input, operating assumption, diligence finding, or structure term is absent, disputed, or stale and requires workstream evidence rather than question-only resolution. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T029 | S7_INVESTMENT_DECISION | SX_TERMINATED_STALLED_DECLINED | INVESTMENT_DECISION_REJECTED | The investment approval decision is rejected and no live exposure exists. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T030 | S7_INVESTMENT_DECISION | S5_DILIGENCE_ACTIVE | CONDITIONAL_APPROVAL_UNSATISFIED_DILIGENCE | The failed condition requires additional diligence evidence, not merely document negotiation. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T031 | S7_INVESTMENT_DECISION | S6_UNDERWRITING_VALUATION | CONDITIONAL_APPROVAL_UNSATISFIED_ECONOMICS | The failed condition changes valuation, returns, capital structure, security terms, or exposure size. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T032 | S8_EXECUTION_DOCUMENTATION | SX_TERMINATED_STALLED_DECLINED | SIGNING_FAILED_OR_TRANSACTION_ABANDONED | Signing failed, counterparty withdrew, terms became unacceptable, or required authority expired; no funded exposure exists. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T033 | S9_CLOSING_ADMINISTRATION | S8_EXECUTION_DOCUMENTATION | CLOSING_FAILED_REQUIRES_DOCUMENT_REMEDIATION | Closing failed because an agreement, condition, authority, security issuance, or funds-flow document must be corrected. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T034 | S9_CLOSING_ADMINISTRATION | S9_CLOSING_ADMINISTRATION | FUNDING_DELAY_RECORDED | The delay does not terminate the transaction and an explicit revised funding date, owner, and consequence assessment exist. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T035 | S9_CLOSING_ADMINISTRATION | SX_TERMINATED_STALLED_DECLINED | CLOSING_CANCELLED_WITHOUT_EXPOSURE | No live exposure was created and an effective abandonment decision exists. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T036 | S10_MONITORING | S11_REUNDERWRITING | COVENANT_BREACH_VALIDATED | The underlying covenant finding or observation is verified or disputed but material; dismissal is not effective. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T037 | S10_MONITORING | S11_REUNDERWRITING | LIQUIDITY_SHORTFALL_VALIDATED | Liquidity runway or capital need is material or critical under the configured rule. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T038 | S11_REUNDERWRITING | S8_EXECUTION_DOCUMENTATION | RESCUE_OR_FOLLOW_ON_REQUEST_APPROVED | The request has current evidence, option analysis, old-money versus new-money analysis, security terms, materiality treatment, and effective authority approval. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T039 | S11_REUNDERWRITING | S12_EXIT_REALIZATION | IMPAIRMENT_OR_WRITE_OFF_APPROVED | A current valuation or impairment basis, materiality assessment, and effective authority approval exist. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T040 | S12_EXIT_REALIZATION | S10_MONITORING | EXIT_PROCESS_FAILED | No sale completed, exposure remains live, and an effective hold or no-action decision plus revised exit assumptions exist. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T041 | S13_CLOSED_ARCHIVE | S10_MONITORING | RESIDUAL_EXPOSURE_DISCOVERED | New evidence proves a material live or contingent exposure; an effective workflow exception authorizes reopening and original archive records remain immutable. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T042 | SX_TERMINATED_STALLED_DECLINED | S0_INTAKE | DEAL_REVIVED_NEW_PROCESS | New material evidence, terms, access, or process exists; no live exposure requires direct monitoring; owner and process type are current. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T043 | SX_TERMINATED_STALLED_DECLINED | S2_CASE_INGESTION | DEAL_REVIVED_EXISTING_IDENTITY | Canonical identity and owner remain valid, current access is effective, and new material source evidence is the revival trigger. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T044 | S3_SCREENING_ASSESSMENT | S5_DILIGENCE_ACTIVE | ACCELERATED_DILIGENCE_EXCEPTION | A final proceed or exception_proceed screening decision exists, a provisional active question register exists, critical questions have owners, and the exception names the skipped S4 completion requirements. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T045 | S11_REUNDERWRITING | S5_DILIGENCE_ACTIVE | REUNDERWRITING_RETURNS_TO_DILIGENCE | The review identifies specific unresolved evidence and activates successor workstream runs with owners and output requirements. | ENT_GATE | LOAD_BEARING / ENFORCE |
| T046 | S6_UNDERWRITING_VALUATION | S6_UNDERWRITING_VALUATION | ANALYTICAL_OBJECT_SUPERSEDED | A successor model case or valuation case has been created with explicit supersedes reference and lineage. | ENT_GATE | LOAD_BEARING / ENFORCE |

### 4.4 Gates, failures, skips, and revival

- A failed guard or gate leaves the deal in the source state and records the blocking objects.
- A skipped state requires a scoped exception or waiver record; absence of an objection never constitutes a skip approval.
- A backtrack appends an event and stales downstream outputs whose basis is no longer current.
- A stalled or terminated process retains its history and may be revived only through an explicit authority action and successor workflow event.
- A partial outcome retains the position and residual-exposure objects required for continued monitoring or later realization.

## 5. Workstream dependency graph

Workstreams are typed, parallel, and iterative. A node may start when its start predicate and input contracts are satisfied. It may not complete while an applicable blocking edge remains unsatisfied.

### 5.1 Edge modes

- `BLOCKS` — the target cannot proceed or complete without the source output.
- `BLOCKS_FINAL_OUTPUT` — preliminary target work may run, but final completion is blocked.
- `BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL` — final completion is blocked when the dependency is material.
- `CONDITIONAL_BLOCKS` — policy, archetype, materiality, or transaction terms determine whether the edge blocks.
- `PARALLEL_SOFT` — nodes may run concurrently; the source improves or constrains the target but does not normally block.
- `ITERATIVE_RETURN` — the source returns questions or changes to an upstream workstream.
- `TRIGGERS` — the source creates an event that activates the target.
- `LOOP_RETURN` — the source returns the lifecycle to monitoring or another ongoing state after a decision.

### 5.2 Node contracts


#### access_clearance — Access / confidentiality

**Governing question:** May the requested actors receive, store, review, and use the intended material?

- Required/optional inputs: ENT_DEAL, ENT_ORGANIZATION, ENT_PERMISSION_POLICY, ENT_AUTHORITY_RULE
- Outputs: ENT_ACCESS_GRANT, ENT_APPROVAL_RECORD
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active'] AND ENT_DEAL.current_state IN ['S0_INTAKE','S1_ACCESS_CLEARANCE']`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND an effective ENT_ACCESS_GRANT exists or an explicit denial/abandonment path is recorded.`
- Blocked: `Required permission evaluates to deny, or no authorized access grant can be issued.`
- Stale: `Any output is stale when the grant is revoked, expires, its scope changes, or the governing policy version changes.`
- State hooks: S0_INTAKE, S1_ACCESS_CLEARANCE, S2_CASE_INGESTION

#### source_case_ingestion — Source case ingestion

**Governing question:** What source materials exist, may be used, and what evidence, claims, assumptions, and questions can be extracted?

- Required/optional inputs: ENT_DEAL, ENT_ACCESS_GRANT, ENT_DOCUMENT_ARTIFACT, ENT_DOCUMENT_VERSION
- Outputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_QUESTION
- Start: `ENT_ACCESS_GRANT is effective and at least one permitted ENT_DOCUMENT_VERSION exists.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND at least one ENT_SOURCE_MATERIAL_SET.index_status='indexed' with provenance_quality!='unknown'.`
- Blocked: `No permitted investable source exists, or indexing/provenance requirements fail materially.`
- Stale: `Outputs are stale when a material source version is superseded, access is revoked, or extraction lineage changes.`
- State hooks: S1_ACCESS_CLEARANCE, S2_CASE_INGESTION, S3_SCREENING_ASSESSMENT, S5_DILIGENCE_ACTIVE

#### screening_assessment — Initial assessment / screening

**Governing question:** Is the opportunity sufficiently aligned, attractive, and feasible to justify diligence resources?

- Required/optional inputs: ENT_DEAL, ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM
- Outputs: ENT_SCREENING_ASSESSMENT, ENT_INVESTMENT_THESIS, ENT_RISK, ENT_DECISION_RECORD
- Start: `ENT_DEAL.current_state IN ['S2_CASE_INGESTION','S3_SCREENING_ASSESSMENT'] AND indexed source evidence exists.`
- Done: `A final ENT_SCREENING_ASSESSMENT and matching effective ENT_DECISION_RECORD exist.`
- Blocked: `Fit, preliminary economics, target identity, or authority is unresolved.`
- Stale: `Assessment is stale when a material source, target identity, process type, or preliminary economics changes before final investment decision.`
- State hooks: S2_CASE_INGESTION, S3_SCREENING_ASSESSMENT, S4_QUESTION_PLANNING

#### question_engine — Question engine

**Governing question:** What uncertainty must be resolved, by whom, with what evidence, before a decision or action?

- Required/optional inputs: ENT_SCREENING_ASSESSMENT, ENT_INVESTMENT_THESIS, ENT_RISK, ENT_ASSUMPTION, ENT_DILIGENCE_FINDING, ENT_VALUATION_INPUT, ENT_QUESTION
- Outputs: ENT_QUESTION_REGISTER, ENT_QUESTION, ENT_WORKSTREAM_RUN
- Start: `A proceed screening decision, material finding, model gap, monitoring issue, or re-underwriting need creates unresolved uncertainty.`
- Done: `Every critical question is answered, risk-accepted, closed, or has owner, evidence_needed, and active/planned workstream run.`
- Blocked: `A critical question lacks owner/evidence need or is blocked without accepted treatment.`
- Stale: `A decision snapshot is immutable; the active register becomes stale when a material finding, assumption change, or model gap is not reflected.`
- State hooks: S3_SCREENING_ASSESSMENT, S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S10_MONITORING, S11_REUNDERWRITING

#### financial_qoe — Financial / QoE

**Governing question:** What earnings, cash flow, working-capital, and adjustment basis is reliable for underwriting?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_ADJUSTMENT_ITEM, ENT_VALUATION_INPUT, ENT_METRIC_OBSERVATION
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### commercial_market — Commercial / market

**Governing question:** Are market size, growth, competition, customer behavior, and revenue assumptions supportable?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_VALUATION_INPUT, ENT_METRIC_OBSERVATION
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### operational — Operational / KPI / execution feasibility

**Governing question:** Can the operating plan, cost structure, capacity, value-creation actions, and integration requirements be executed?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_VALUE_CREATION_PLAN, ENT_BRIDGE_ANALYSIS
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### management_sponsor — Management and sponsor assessment

**Governing question:** Do management, sponsor, governance, incentives, and execution capabilities support the investment case?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_ORGANIZATION, ENT_ACTOR, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_GOVERNANCE_RIGHT
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### legal — Legal diligence

**Governing question:** What rights, liabilities, contracts, permissions, and legal conditions affect signing, closing, ownership, or value?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_LEGAL_AGREEMENT, ENT_COVENANT, ENT_GOVERNANCE_RIGHT
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### tax — Tax / tax structuring

**Governing question:** What tax structure, leakage, obligations, and conditions affect economics, security, signing, or closing?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_VALUATION_INPUT, ENT_SECURITY
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### financing — Financing / debt package

**Governing question:** What financing package, debt capacity, covenants, funds flow, and downside liquidity are feasible?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_CAPITAL_STRUCTURE, ENT_QUESTION
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_COVENANT, ENT_SOURCES_USES
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### structuring — Security / vehicle / rights structuring

**Governing question:** What legal, tax, financing, security, governance, and exposure structure implements the approved economics?

- Required/optional inputs: ENT_SOURCE_MATERIAL_SET, ENT_EVIDENCE_ITEM, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_DILIGENCE_FINDING, ENT_QUESTION, ENT_REUNDERWRITING_RECORD
- Outputs: ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_ASSUMPTION, ENT_RISK, ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_SOURCES_USES, ENT_GOVERNANCE_RIGHT
- Start: `ENT_WORKSTREAM_RUN.status IN ['planned','active','reopened'] AND assigned questions or required gate outputs exist.`
- Done: `ENT_WORKSTREAM_RUN.status='completed' AND every material finding is validated, linked to evidence, and routed to assumptions, questions, valuation inputs, risk treatment, or a gate.`
- Blocked: `Required evidence is unavailable or not permitted, or a material finding is unresolved without mitigation/acceptance.`
- Stale: `Outputs are stale when a material source, evidence item, assumption, metric, legal term, or upstream finding changes.`
- State hooks: S4_QUESTION_PLANNING, S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING

#### investment_decision — Investment decisioning

**Governing question:** Should the proposed investment or material action be approved, rejected, deferred, or conditioned?

- Required/optional inputs: ENT_VALUATION_CASE, ENT_QUESTION_REGISTER, ENT_RISK, ENT_DILIGENCE_FINDING, ENT_MATERIALITY_ASSESSMENT, ENT_AUTHORITY_RULE, ENT_REUNDERWRITING_RECORD
- Outputs: ENT_DECISION_RECORD, ENT_APPROVAL_RECORD, ENT_RISK_ACCEPTANCE_RECORD, ENT_GATE
- Start: `A decision-ready valuation or action basis and an open decision gate exist.`
- Done: `An effective ENT_DECISION_RECORD and all required ENT_APPROVAL_RECORD objects exist; conditions and risk acceptances are explicit.`
- Blocked: `Decision basis is stale, critical question unresolved, authority unavailable, or gate blocked.`
- Stale: `The immutable decision snapshot becomes historically fixed; later changes stale only the current action package and require a successor decision.`
- State hooks: S3_SCREENING_ASSESSMENT, S7_INVESTMENT_DECISION, S11_REUNDERWRITING, S12_EXIT_REALIZATION

#### transaction_documentation — Transaction documentation

**Governing question:** Do the executable documents faithfully implement approved economics, rights, obligations, and conditions?

- Required/optional inputs: ENT_DECISION_RECORD, ENT_SECURITY, ENT_CAPITAL_STRUCTURE, ENT_DILIGENCE_FINDING, ENT_APPROVAL_RECORD
- Outputs: ENT_EXECUTION_DOCUMENT_SET, ENT_LEGAL_AGREEMENT, ENT_DOCUMENT_ARTIFACT, ENT_DOCUMENT_VERSION, ENT_COVENANT, ENT_GOVERNANCE_RIGHT
- Start: `An effective approved or conditional decision exists and documentation ownership is assigned.`
- Done: `The execution set is signed or complete, economically consistent or exception-approved, and all required conditions are satisfied or effectively waived.`
- Blocked: `Material deviation, unsigned required document, legal authority gap, or unresolved material condition.`
- Stale: `The execution set becomes stale when approved terms, security terms, condition status, or required agreement version changes; signed snapshots remain immutable.`
- State hooks: S7_INVESTMENT_DECISION, S8_EXECUTION_DOCUMENTATION, S9_CLOSING_ADMINISTRATION, S11_REUNDERWRITING, S12_EXIT_REALIZATION

#### closing_admin — Closing / capital administration

**Governing question:** Has the transaction or realization become legally and economically effective, and are exposure, cash flow, and position records reconciled?

- Required/optional inputs: ENT_EXECUTION_DOCUMENT_SET, ENT_APPROVAL_RECORD, ENT_SECURITY, ENT_OUTCOME_RECORD
- Outputs: ENT_CLOSING_RECORD, ENT_INVESTMENT_EXPOSURE, ENT_CAPITAL_EVENT, ENT_POSITION_RECORD
- Start: `A signed execution set or approved realization event exists and a closing/administration owner is assigned.`
- Done: `Closing or realization is recorded, funds and exposures reconcile, and each live exposure has a reconciled position record.`
- Blocked: `Unmet condition, authority gap, unbalanced funds flow, missing security/exposure, or unreconciled proceeds.`
- Stale: `Position outputs are stale when a capital event is reversed/corrected, exposure terms change, or final outcome changes; historical dated positions remain immutable.`
- State hooks: S8_EXECUTION_DOCUMENTATION, S9_CLOSING_ADMINISTRATION, S10_MONITORING, S12_EXIT_REALIZATION, S13_CLOSED_ARCHIVE

#### monitoring — Monitoring

**Governing question:** How is live exposure performing relative to the approved baseline, and has any event created a new decision need?

- Required/optional inputs: ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD, ENT_MODEL_CASE, ENT_METRIC_DEFINITION, ENT_SOURCE_MATERIAL_SET, ENT_DECISION_RECORD, ENT_OUTCOME_RECORD
- Outputs: ENT_MONITORING_RECORD, ENT_METRIC_OBSERVATION, ENT_REUNDERWRITING_TRIGGER, ENT_RISK
- Start: `At least one live or residual exposure exists and the monitoring cadence or event trigger is due.`
- Done: `The monitoring record is final/revised and every material signal is represented by a trigger with status validated, dismissed, or acted.`
- Blocked: `Required metrics absent, live exposure unreconciled, or material trigger not treated.`
- Stale: `Monitoring conclusions are stale when source reports, metric observations, baseline model, or position records are revised or superseded.`
- State hooks: S9_CLOSING_ADMINISTRATION, S10_MONITORING, S11_REUNDERWRITING, S12_EXIT_REALIZATION

#### reunderwriting — Re-underwriting / update / outcome calibration

**Governing question:** What changed relative to the original case, what options exist now, and what action should be taken?

- Required/optional inputs: ENT_REUNDERWRITING_TRIGGER, ENT_MODEL_CASE, ENT_METRIC_OBSERVATION, ENT_INVESTMENT_EXPOSURE, ENT_RISK
- Outputs: ENT_REUNDERWRITING_RECORD, ENT_MODEL_CASE, ENT_VALUATION_CASE, ENT_DECISION_RECORD, ENT_OUTCOME_RECORD
- Start: `At least one material or critical re-underwriting trigger is validated or a material action request exists.`
- Done: `The review compares current evidence to the original model case, analyzes alternatives, and has an effective action decision.`
- Blocked: `Original baseline missing, current evidence insufficient, action alternatives absent, or authority unavailable.`
- Stale: `The review becomes stale when current metrics, revised cases, valuation, exposure, or trigger evidence changes; approved review snapshots remain immutable.`
- State hooks: S10_MONITORING, S11_REUNDERWRITING, S5_DILIGENCE_ACTIVE, S8_EXECUTION_DOCUMENTATION, S12_EXIT_REALIZATION

#### exit_realization — Exit / realization

**Governing question:** Should and can exposure be sold, partially realized, impaired, written off, or returned to hold, and what residual remains?

- Required/optional inputs: ENT_DECISION_RECORD, ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD, ENT_VALUATION_CASE, ENT_APPROVAL_RECORD, ENT_REUNDERWRITING_TRIGGER
- Outputs: ENT_OUTCOME_RECORD, ENT_CAPITAL_EVENT, ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD
- Start: `An effective sell, exit, impair, or write-off decision exists, or an external realization event requires treatment.`
- Done: `A final/revised outcome record exists, economic effects are reconciled, and residual exposure status is explicit.`
- Blocked: `Outcome authority absent, proceeds or impairment unreconciled, or residual exposure unknown without treatment.`
- Stale: `Outcome analysis is stale when valuation, bids, legal terms, proceeds, or exposure status changes; final outcome records are immutable and corrections create successors.`
- State hooks: S11_REUNDERWRITING, S12_EXIT_REALIZATION, S9_CLOSING_ADMINISTRATION, S10_MONITORING, S13_CLOSED_ARCHIVE

#### financial_model — Financial model

**Governing question:** How do operating assumptions, cash flows, financing terms and exit conditions translate into internally consistent model cases?

- Required/optional inputs: ENT_DEAL, ENT_ANALYTICAL_MODEL, ENT_ASSUMPTION, ENT_METRIC_OBSERVATION, ENT_CAPITAL_STRUCTURE, ENT_DILIGENCE_FINDING, ENT_SOURCES_USES, ENT_SECURITY, ENT_COVENANT, ENT_VALUE_CREATION_PLAN, ENT_SYNERGY_PLAN
- Outputs: ENT_ANALYTICAL_MODEL, ENT_MODEL_CASE, ENT_METRIC_OBSERVATION, ENT_BRIDGE_ANALYSIS, ENT_QUESTION, ENT_EXCEPTION_RECORD
- Start: `The deal or live exposure is in an applicable workflow state; required objects exist in permitted current versions; the workstream run is planned or active; and no unresolved hard blocker prevents use of the required evidence.`
- Done: `All material subquestions have a disposition; required outputs exist in current versions; evidence sufficiency has been assessed for the phase; critical exceptions are resolved, risk-accepted or explicitly authorized; and downstream lineage is recorded.`
- Blocked: `A required input is absent, inaccessible, stale or unreliable; a critical question is unresolved; a required gate has failed; or a material conflict lacks an authorized exception.`
- Stale: `Any material upstream evidence, assumption, metric definition, model case, valuation input, security term, capital-structure term or decision baseline referenced by the output has a newer non-equivalent version or is challenged, superseded or withdrawn.`
- State hooks: S5_DILIGENCE_ACTIVE, S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S10_MONITORING, S11_REUNDERWRITING, S12_EXIT_REALIZATION

#### valuation_returns — Valuation and returns

**Governing question:** What is the value and investor return of each security under the current evidence, model cases, capital structure and exit routes?

- Required/optional inputs: ENT_DEAL, ENT_MODEL_CASE, ENT_VALUATION_INPUT, ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_DILIGENCE_FINDING, ENT_SOURCES_USES, ENT_BRIDGE_ANALYSIS, ENT_RISK, ENT_OUTCOME_RECORD
- Outputs: ENT_VALUATION_CASE, ENT_BRIDGE_ANALYSIS, ENT_VALUATION_INPUT, ENT_METRIC_OBSERVATION, ENT_QUESTION
- Start: `The deal or live exposure is in an applicable workflow state; required objects exist in permitted current versions; the workstream run is planned or active; and no unresolved hard blocker prevents use of the required evidence.`
- Done: `All material subquestions have a disposition; required outputs exist in current versions; evidence sufficiency has been assessed for the phase; critical exceptions are resolved, risk-accepted or explicitly authorized; and downstream lineage is recorded.`
- Blocked: `A required input is absent, inaccessible, stale or unreliable; a critical question is unresolved; a required gate has failed; or a material conflict lacks an authorized exception.`
- Stale: `Any material upstream evidence, assumption, metric definition, model case, valuation input, security term, capital-structure term or decision baseline referenced by the output has a newer non-equivalent version or is challenged, superseded or withdrawn.`
- State hooks: S6_UNDERWRITING_VALUATION, S7_INVESTMENT_DECISION, S11_REUNDERWRITING, S12_EXIT_REALIZATION

### 5.3 Dependency edges

| ID | Source | Target | Mode | Output → Input | Consequence |
| --- | --- | --- | --- | --- | --- |
| E01 | access_clearance | source_case_ingestion | BLOCKS | ENT_ACCESS_GRANT → ENT_ACCESS_GRANT | The team needs permission before ingesting confidential materials. |
| E02 | source_case_ingestion | screening_assessment | BLOCKS | ENT_EVIDENCE_ITEM → ENT_EVIDENCE_ITEM | Screening must evaluate a case, not an empty folder. |
| E03 | screening_assessment | question_engine | BLOCKS | ENT_SCREENING_ASSESSMENT → ENT_SCREENING_ASSESSMENT | Questions should flow from an articulated thesis/risk, not passive data-room browsing. |
| E04 | source_case_ingestion | financial_qoe | BLOCKS | ENT_EVIDENCE_ITEM → ENT_EVIDENCE_ITEM | Financial diligence tests financial claims. |
| E05 | source_case_ingestion | commercial_market | BLOCKS | ENT_EVIDENCE_ITEM → ENT_EVIDENCE_ITEM | Commercial diligence tests market and growth claims. |
| E06 | source_case_ingestion | management_sponsor | BLOCKS | ENT_EVIDENCE_ITEM → ENT_EVIDENCE_ITEM | Capability assessment requires identifying who is responsible for executing the case. |
| E07 | question_engine | financial_qoe | PARALLEL_SOFT | ENT_QUESTION → ENT_QUESTION | Questions guide financial diligence, but diligence can also start from available data. |
| E08 | question_engine | commercial_market | PARALLEL_SOFT | ENT_QUESTION → ENT_QUESTION | Questions and commercial diligence iterate. |
| E09 | financial_qoe | question_engine | ITERATIVE_RETURN | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Financial findings can invalidate or refine the original questions. |
| E10 | commercial_market | question_engine | ITERATIVE_RETURN | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Commercial findings can challenge growth and valuation assumptions. |
| E11 | operational | question_engine | ITERATIVE_RETURN | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Operational evidence can create new diligence questions. |
| E12 | management_sponsor | question_engine | ITERATIVE_RETURN | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Sponsor/management risk often reframes underwriting rather than simply adding a checklist item. |
| E13M | financial_qoe | financial_model | BLOCKS_FINAL_OUTPUT | ENT_VALUATION_INPUT → ENT_VALUATION_INPUT | You cannot set final valuation on an unverified or unaccepted earnings basis. |
| E13V | financial_qoe | valuation_returns | BLOCKS_FINAL_OUTPUT | ENT_VALUATION_INPUT → ENT_VALUATION_INPUT | You cannot set final valuation on an unverified or unaccepted earnings basis. |
| E14M | commercial_market | financial_model | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_ASSUMPTION → ENT_ASSUMPTION | Commercial evidence drives growth/margin/exit multiple inputs. |
| E14V | commercial_market | valuation_returns | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_ASSUMPTION → ENT_ASSUMPTION | Commercial evidence drives growth/margin/exit multiple inputs. |
| E15M | operational | financial_model | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_ASSUMPTION → ENT_ASSUMPTION | Operational feasibility changes cash flows and value creation. |
| E15V | operational | valuation_returns | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_ASSUMPTION → ENT_ASSUMPTION | Operational feasibility changes cash flows and value creation. |
| E16M | financing | financial_model | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_CAPITAL_STRUCTURE → ENT_CAPITAL_STRUCTURE | Debt terms change return distribution and downside. |
| E16V | financing | valuation_returns | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_CAPITAL_STRUCTURE → ENT_CAPITAL_STRUCTURE | Debt terms change return distribution and downside. |
| E17 | tax | structuring | CONDITIONAL_BLOCKS | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Tax is a blocker only where it materially changes economics or feasibility. |
| E18 | legal | structuring | BLOCKS | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Legal rights and liabilities must be reflected in structure and docs. |
| E19M | structuring | financial_model | BLOCKS_FINAL_OUTPUT | ENT_SECURITY → ENT_SECURITY | Security terms and rights are part of the economics, not a legal afterthought. |
| E19V | structuring | valuation_returns | BLOCKS_FINAL_OUTPUT | ENT_SECURITY → ENT_SECURITY | Security terms and rights are part of the economics, not a legal afterthought. |
| E20M | financial_model | question_engine | ITERATIVE_RETURN | ENT_QUESTION → ENT_QUESTION | The model reveals which assumptions matter and what evidence is missing. |
| E20V | valuation_returns | question_engine | ITERATIVE_RETURN | ENT_QUESTION → ENT_QUESTION | The model reveals which assumptions matter and what evidence is missing. |
| E21V | valuation_returns | investment_decision | BLOCKS | ENT_VALUATION_CASE → ENT_VALUATION_CASE | Authority needs a risk/return case. |
| E22 | question_engine | investment_decision | BLOCKS | ENT_QUESTION_REGISTER → ENT_QUESTION_REGISTER | IC should not unknowingly approve unresolved critical uncertainty. |
| E23 | investment_decision | transaction_documentation | BLOCKS | ENT_DECISION_RECORD → ENT_DECISION_RECORD | Execution should implement approved terms, not create them silently. |
| E24 | legal | transaction_documentation | BLOCKS | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Legal authority and document consistency are hard execution blockers. |
| E25 | tax | transaction_documentation | CONDITIONAL_BLOCKS | ENT_DILIGENCE_FINDING → ENT_DILIGENCE_FINDING | Tax can be either a true blocker or a review layer depending on materiality. |
| E26 | transaction_documentation | closing_admin | BLOCKS | ENT_EXECUTION_DOCUMENT_SET → ENT_EXECUTION_DOCUMENT_SET | Capital records require executed commitments or realization evidence. |
| E27 | closing_admin | monitoring | BLOCKS | ENT_INVESTMENT_EXPOSURE → ENT_INVESTMENT_EXPOSURE | Monitoring requires a position and baseline. |
| E28 | monitoring | reunderwriting | TRIGGERS | ENT_REUNDERWRITING_TRIGGER → ENT_REUNDERWRITING_TRIGGER | Material post-close evidence requires outcome calibration. |
| E29 | reunderwriting | investment_decision | BLOCKS_FINAL_OUTPUT_WHEN_MATERIAL | ENT_REUNDERWRITING_RECORD → ENT_REUNDERWRITING_RECORD | Material post-close actions need decision authority. |
| E30 | reunderwriting | structuring | CONDITIONAL_BLOCKS | ENT_REUNDERWRITING_RECORD → ENT_REUNDERWRITING_RECORD | New-money and restructuring decisions require updated rights/security/economics. |
| E31 | reunderwriting | transaction_documentation | CONDITIONAL_BLOCKS | ENT_DECISION_RECORD → ENT_DECISION_RECORD | Post-close action changes exposure and must be documented. |
| E32 | reunderwriting | monitoring | LOOP_RETURN | ENT_DECISION_RECORD → ENT_DECISION_RECORD | A hold decision still changes what the system should monitor. |
| E33 | reunderwriting | exit_realization | CONDITIONAL_BLOCKS | ENT_DECISION_RECORD → ENT_DECISION_RECORD | Exit requires current outcome-calibration, not a generic update label. |
| E34 | monitoring | exit_realization | TRIGGERS | ENT_REUNDERWRITING_TRIGGER → ENT_REUNDERWRITING_TRIGGER | Some exit events arise before a formal update/re-underwriting report document is produced. |
| E35 | exit_realization | closing_admin | BLOCKS | ENT_OUTCOME_RECORD → ENT_OUTCOME_RECORD | Outcomes must be reconciled into capital records. |
| E36 | exit_realization | monitoring | LOOP_RETURN | ENT_OUTCOME_RECORD → ENT_OUTCOME_RECORD | Partial realization does not close the workflow. |
| E_MODEL_TO_VALUATION | financial_model | valuation_returns | BLOCKS_FINAL_OUTPUT | ENT_MODEL_CASE → ENT_MODEL_CASE | Separates operating and financing computation from the application of valuation methods, security waterfalls, and investor-return interpretation. |

## 6. Epistemic workstream schemas

Each workstream contract defines its governing question, testable subquestions, typed inputs and outputs, reasoning operators, evidence thresholds, assumptions, risks, metrics, materiality behavior, human judgment points, automation boundary, feedback loops, and failure modes.


### Market / commercial diligence (`commercial_market`)

Defines the relevant market and tests demand, customer behavior, competition, pricing, concentration and revenue durability before those propositions enter model cases or valuation.

**Governing question:** Can the company generate durable revenue and defend its economic position under the underwriting horizon?

**Subquestions**

- What economic activity, customer set, geography, product and value-chain layer define the addressable market?
- What is current market size, and how much is directly addressable by the company?
- Which causal drivers support market growth, and what would cause them to weaken?
- Why does the company win, lose, retain or displace business relative to alternatives?
- Is realized pricing power distinct from inflation, mix and temporary shortage effects?
- How dependent is revenue or gross profit on correlated customers, channels, products or geographies?
- What do retention, churn, expansion and cohort behavior imply about revenue durability?
- How do channel economics, incentives and conflicts affect acquisition, margin and control of the customer?
- How would demand, price and mix behave across a realistic adverse cycle?
- Which regulatory or policy changes can alter demand, market access, pricing or exitability?
- How do market structure and buyer economics constrain feasible exit routes and multiples?

- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_SOURCE_MATERIAL_SET, ENT_QUESTION_REGISTER, ENT_ASSUMPTION
- **Optional inputs:** ENT_EVIDENCE_ITEM, ENT_METRIC_OBSERVATION, ENT_RISK, ENT_VENDOR_DILIGENCE_PACKAGE
- **Required outputs:** ENT_DILIGENCE_FINDING, ENT_ASSUMPTION, ENT_RISK, ENT_METRIC_OBSERVATION, ENT_QUESTION
- **Reasoning operators:** OP_TRIANGULATE, OP_COHORT, OP_UNIT_ECON, OP_BENCHMARK, OP_FALSIFY, OP_CONCENTRATION, OP_RETENTION, OP_PRICING, OP_SCENARIO
- **Materiality behavior:** Material commercial findings challenge linked assumptions, stale affected model cases, and block final underwriting until resolved, risk-accepted, or explicitly excepted.
- **Authority behavior:** Waiver of a material unresolved commercial question requires an effective authority rule, approval record and risk-acceptance record.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** New customer or market evidence reopens linked questions and assumptions; a changed commercial assumption stales dependent model cases and valuation cases.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Financial diligence / quality of earnings (`financial_qoe`)

Reconciles reported accounting to a normalized economic basis while preserving management, sponsor, adviser and accepted views separately.

**Governing question:** What historical earnings, cash flow, working-capital and debt-like basis is reliable enough to underwrite?

**Subquestions**

- Do reported financial statements reconcile to source accounting records and transaction schedules?
- Which earnings are recurring, operational and available to the owner?
- For each adjustment, is it evidenced, non-recurring, non-duplicative and economically appropriate?
- How reliably do earnings convert to operating cash and free cash flow?
- What normalized working-capital investment is required through the cycle and at closing?
- What portion of capex is maintenance, compliance, integration, growth or discretionary?
- Which obligations are debt-like, quasi-debt, off-balance-sheet or purchase-price deductions?
- How do seasonality, cut-off and growth distort point-in-time earnings and working capital?
- Which accounting policies or estimates create material comparability or recognition risk?
- How credible is the forecast relative to historical accuracy, current trading and operational drivers?
- What is the accepted normalized financial basis, and which items remain disputed?

- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_SOURCE_MATERIAL_SET, ENT_QUESTION_REGISTER, ENT_METRIC_OBSERVATION
- **Optional inputs:** ENT_ADJUSTMENT_ITEM, ENT_EVIDENCE_ITEM, ENT_RISK, ENT_VENDOR_DILIGENCE_PACKAGE
- **Required outputs:** ENT_DILIGENCE_FINDING, ENT_ADJUSTMENT_ITEM, ENT_METRIC_OBSERVATION, ENT_VALUATION_INPUT, ENT_RISK, ENT_QUESTION
- **Reasoning operators:** OP_NORMALIZE, OP_RECONCILE, OP_VARIANCE, OP_SOURCE_WEIGHT, OP_HIST_FORECAST, OP_WC, OP_CASH_CONVERSION, OP_CAPEX, OP_DEBTLIKE, OP_CONSISTENCY
- **Materiality behavior:** A material unresolved adjustment or reconciliation difference prevents a valuation case from becoming decision-ready unless explicitly risk-accepted.
- **Authority behavior:** Acceptance of a disputed material adjustment requires financial workstream sign-off and the applicable investment authority.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** New ledger data or changed adjustment classification reopens the financial basis and stales dependent model, valuation, financing and purchase-price outputs.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Financial model (`financial_model`)

Creates a versioned computational representation of historical baseline, operating drivers, capital structure, cash movement and investor outcomes; it does not decide the valuation method or recommendation.

**Governing question:** How do operating assumptions, cash flows, financing terms and exit conditions translate into internally consistent model cases?

**Subquestions**

- Does the historical baseline reconcile to the accepted financial basis?
- What unit, price, volume, mix, cohort, pipeline or acquisition drivers produce revenue?
- What operational mechanisms create or erode gross and EBITDA margin?
- How do growth, seasonality and terms drive working-capital cash needs?
- How do maintenance, compliance, integration and growth capex affect capacity and cash?
- How do entity, jurisdiction and timing assumptions affect cash tax and exit proceeds?
- How do draw, amortization, interest, maturity and cash sweep evolve under each case?
- How are acquisitions, cost-to-achieve and synergies phased without double counting?
- What timing, metric and capital structure determine equity proceeds at exit?
- Are base, downside, upside and management cases internally coherent and distinguishable?
- Which assumptions carry the greatest return, covenant and liquidity sensitivity?
- Do model checks detect imbalance, circularity, stale input and definition mismatch?

- **Required inputs:** ENT_DEAL, ENT_ANALYTICAL_MODEL, ENT_ASSUMPTION, ENT_METRIC_OBSERVATION, ENT_CAPITAL_STRUCTURE
- **Optional inputs:** ENT_DILIGENCE_FINDING, ENT_SOURCES_USES, ENT_SECURITY, ENT_COVENANT, ENT_VALUE_CREATION_PLAN, ENT_SYNERGY_PLAN
- **Required outputs:** ENT_ANALYTICAL_MODEL, ENT_MODEL_CASE, ENT_METRIC_OBSERVATION, ENT_BRIDGE_ANALYSIS, ENT_QUESTION, ENT_EXCEPTION_RECORD
- **Reasoning operators:** OP_RECONCILE, OP_BRIDGE, OP_UNIT_ECON, OP_HIST_FORECAST, OP_SCENARIO, OP_DOWNSIDE, OP_SENSITIVITY, OP_CASH_CONVERSION, OP_COVENANT, OP_LIQUIDITY, OP_LINEAGE
- **Materiality behavior:** A model cannot be decision-ready while a material input is disputed, stale or disconnected from an assumption and evidence lineage; provisional cases may run but must be visibly non-final.
- **Authority behavior:** Model approval is an analytical sign-off; capital authority remains with the decision workstream.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Any changed material assumption, accepted financial basis, term or security creates a successor case and stales dependent valuation and decision packages.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Valuation and returns (`valuation_returns`)

Applies appropriate valuation methods, reconciles enterprise value to security-specific proceeds, and separates operating improvement, leverage, multiple movement, dilution and preference effects.

**Governing question:** What is the value and investor return of each security under the current evidence, model cases, capital structure and exit routes?

**Subquestions**

- Which valuation methods fit the asset economics, data quality and transaction context?
- What verified economic metric is being capitalized or discounted?
- Which comparables are definition-consistent, and what differences justify adjustment?
- Which precedent transactions are comparable on cycle, control, growth and quality?
- How does enterprise value bridge to equity value after debt-like items, cash and other claims?
- How do priority, participation, conversion, dilution and governance affect each security?
- What entry and exit multiples are supported without assuming unexplained rerating?
- How much return comes from operating growth, margin, leverage, multiple and dilution?
- What is recovery under plausible operating, financing and exit stresses?
- What MOIC, IRR, cash yield and timing result for each security and case?
- How does current realization compare with risk-adjusted hold value and residual exposure?

- **Required inputs:** ENT_DEAL, ENT_MODEL_CASE, ENT_VALUATION_INPUT, ENT_CAPITAL_STRUCTURE, ENT_SECURITY
- **Optional inputs:** ENT_DILIGENCE_FINDING, ENT_SOURCES_USES, ENT_BRIDGE_ANALYSIS, ENT_RISK, ENT_OUTCOME_RECORD
- **Required outputs:** ENT_VALUATION_CASE, ENT_BRIDGE_ANALYSIS, ENT_VALUATION_INPUT, ENT_METRIC_OBSERVATION, ENT_QUESTION
- **Reasoning operators:** OP_BENCHMARK, OP_SENSITIVITY, OP_SCENARIO, OP_DOWNSIDE, OP_WATERFALL, OP_MULTIPLE, OP_ALT_VALUE, OP_EXIT_ROUTE, OP_RISK_RECOMMEND
- **Materiality behavior:** Final valuation is blocked when its primary metric, capital structure, security terms or material commercial assumptions are not decision-ready; alternative methods are required when the primary method is unusually assumption-sensitive.
- **Authority behavior:** Approval of a valuation case does not authorize an investment; unresolved material method risk requires explicit risk acceptance by investment authority.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Changed model case, capital structure, security term or comparable evidence stales affected valuation cases and any decision package that cites them.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Operational diligence (`operational`)

Tests the physical and organizational feasibility of the plan and converts initiatives into measurable milestones, resources, costs and risks.

**Governing question:** Can the operating plan, capacity, systems, capex and value-creation initiatives be executed with identified owners and dependencies?

**Subquestions**

- Which operational KPIs causally drive revenue, margin, cash and service quality?
- What is current capacity, bottleneck, utilization and feasible expansion path?
- What productivity gains are evidenced, who owns them and what investment is required?
- Is capex sufficient, feasible and correctly classified for the plan?
- What purchasing savings are addressable after volume, specification and supplier constraints?
- Which systems are critical, what technical debt exists and what change dependencies affect the plan?
- Can acquisitions or separated operations be integrated on the assumed timeline and cost?
- Are synergies baseline-correct, owned, timed, costed and free of double count?
- What milestones demonstrate that the value-creation plan is on track?
- How do operational constraints behave in the downside case?

- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_METRIC_OBSERVATION
- **Optional inputs:** ENT_VALUE_CREATION_PLAN, ENT_SYNERGY_PLAN, ENT_INTEGRATION_PLAN, ENT_STANDALONE_COST_BASELINE, ENT_EVIDENCE_ITEM
- **Required outputs:** ENT_DILIGENCE_FINDING, ENT_ASSUMPTION, ENT_RISK, ENT_METRIC_OBSERVATION, ENT_VALUE_CREATION_PLAN, ENT_QUESTION
- **Reasoning operators:** OP_VARIANCE, OP_UNIT_ECON, OP_BENCHMARK, OP_CAUSAL, OP_CAPEX, OP_SYNERGY, OP_SCENARIO, OP_FALSIFY
- **Materiality behavior:** Material initiatives without an owner, evidence-supported baseline, cost, dependency and timing remain challenged and cannot support a final model case.
- **Authority behavior:** Acceptance of execution risk beyond configured limits requires explicit ownership and risk acceptance by the applicable authority.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Missed milestones or changed operating evidence reopen linked assumptions, stale affected model cases, and may create a re-underwriting trigger.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Management and sponsor assessment (`management_sponsor`)

Separates reputation from deal-specific evidence and tests capability, alignment, governance, key-person dependence and behavior under stress.

**Governing question:** Do the relevant people and organizations have the capability, incentives, governance, bandwidth and credibility to execute the plan?

**Subquestions**

- What capabilities are required by the plan, and who has demonstrated them in comparable conditions?
- Is the relevant track record attributable to the current people, strategy and context?
- How do ownership, compensation, carry, fees and downside exposure shape behavior?
- What rights and forums allow information, challenge, intervention and remedy?
- Does the responsible team have sufficient time, resources and operating support?
- Which individuals are essential, what happens if they leave, and what mitigants exist?
- How accurate have prior plans, explanations and reported metrics been?
- Do independent references corroborate capability, integrity and behavior under stress?
- Which assumptions depend primarily on sponsor conviction rather than independent evidence?
- What intervention rights and practical options exist if execution deteriorates?

- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_ORGANIZATION, ENT_ACTOR, ENT_ROLE_ASSIGNMENT
- **Optional inputs:** ENT_SPONSOR_TRACK_RECORD, ENT_KEY_PERSON_DEPENDENCY, ENT_GOVERNANCE_RIGHT, ENT_EVIDENCE_ITEM, ENT_SECURITY
- **Required outputs:** ENT_DILIGENCE_FINDING, ENT_RISK, ENT_ASSUMPTION, ENT_QUESTION, ENT_ROLE_ASSIGNMENT, ENT_KEY_PERSON_DEPENDENCY
- **Reasoning operators:** OP_TRIANGULATE, OP_SOURCE_WEIGHT, OP_FALSIFY, OP_GOV_ALIGN, OP_BENCHMARK, OP_CAUSAL
- **Materiality behavior:** Material reliance on an unverified actor or organization must be identified as an assumption and risk; reputation alone cannot satisfy a critical execution question.
- **Authority behavior:** Risk acceptance for material alignment, key-person or governance weakness requires the applicable investment authority and recorded mitigants.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Management change, sponsor behavior, missed plan or governance failure reopens capability and alignment assumptions and may trigger re-underwriting.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Legal diligence (`legal`)

Translates legal facts into explicit economic, control and workflow consequences, with conditions and exceptions tracked to evidence and authority.

**Governing question:** What legal rights, liabilities, contracts, regulatory conditions and execution requirements affect ownership, value, signing or closing?

**Subquestions**

- Do all parties and signatories have authority to enter and perform the transaction?
- What is owned, encumbered, excluded or subject to third-party rights?
- Which contracts are material, assignable, terminable, consent-dependent or economically restrictive?
- Which actual or contingent liabilities can transfer, crystallize or reduce value?
- What litigation, investigation or dispute can affect value, operation or closing?
- Which licenses, approvals, notifications or change-of-control conditions apply?
- Do governance, information, transfer and minority rights match the approved control model?
- What conditions precedent, covenants and deliverables must be satisfied before signing or closing?
- Do all execution documents consistently implement the approved economics and rights?
- Are key rights and remedies enforceable in the relevant jurisdictions?

- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_ORGANIZATION, ENT_SOURCE_MATERIAL_SET, ENT_QUESTION_REGISTER
- **Optional inputs:** ENT_LEGAL_AGREEMENT, ENT_COVENANT, ENT_GOVERNANCE_RIGHT, ENT_EVIDENCE_ITEM, ENT_PUBLIC_MARKET_TRANSACTION
- **Required outputs:** ENT_DILIGENCE_FINDING, ENT_RISK, ENT_GATE, ENT_EXCEPTION_RECORD, ENT_LEGAL_AGREEMENT, ENT_QUESTION
- **Reasoning operators:** OP_RECONCILE, OP_CONSISTENCY, OP_SOURCE_WEIGHT, OP_LEGAL_MAP, OP_GOV_ALIGN, OP_DEBTLIKE
- **Materiality behavior:** A material legal condition is a hard blocker unless the authoritative legal finding supports an exception and the authorized decision-maker records the waiver or acceptance.
- **Authority behavior:** Only designated legal authority may conclude enforceability; business authority may accept residual economic risk but may not deem a legal condition satisfied without evidence.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Changed agreed terms stale affected structure, financing, valuation and approval outputs; failed conditions route to exception, backtrack or termination.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Tax diligence (`tax`)

Identifies historical exposure and models prospective leakage, filing obligations and structural alternatives without treating tax as a universal hard blocker when immaterial.

**Governing question:** How do tax obligations, structure, jurisdiction and attributes affect cash economics, ownership constraints and execution?

**Subquestions**

- What historical tax positions, audits and exposures may transfer or crystallize?
- Which entity or investor bears each tax, filing and reporting obligation?
- What recurring cash-tax and structural leakage affects free cash flow and distributions?
- What withholding applies to interest, dividends, fees, proceeds or distributions?
- Is a blocker, feeder or alternative vehicle required, and what cost or constraint does it create?
- What tax attributes exist, who owns them, and what limits their use?
- What tax arises under each plausible exit route and security treatment?
- Which technical positions remain uncertain and how sensitive are economics?

- **Required inputs:** ENT_DEAL, ENT_COMPANY, ENT_ORGANIZATION, ENT_SOURCE_MATERIAL_SET, ENT_QUESTION_REGISTER
- **Optional inputs:** ENT_SECURITY, ENT_FUND_VEHICLE, ENT_EVIDENCE_ITEM, ENT_LEGAL_AGREEMENT, ENT_MODEL_CASE
- **Required outputs:** ENT_DILIGENCE_FINDING, ENT_RISK, ENT_VALUATION_INPUT, ENT_ASSUMPTION, ENT_QUESTION, ENT_GATE
- **Reasoning operators:** OP_RECONCILE, OP_SCENARIO, OP_TAX_LEAK, OP_CONSISTENCY, OP_SOURCE_WEIGHT
- **Materiality behavior:** Material tax exposure or structural leakage blocks affected final outputs until quantified, structured, risk-accepted or excepted; immaterial matters may warn rather than block.
- **Authority behavior:** Tax specialists determine technical treatment; the applicable investment authority accepts residual economic risk and structure trade-offs.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Changed law, structure, investor status or tax characterization stales tax inputs, model cases, valuation and execution documents.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Structuring and security design (`structuring`)

Converts approved economic intent and investor constraints into securities, rights, ownership, waterfall and governance without losing legal, tax or financing consistency.

**Governing question:** What ownership, security, governance and vehicle structure implements the approved economics and protects against identified risks?

**Subquestions**

- Which security type and terms match the risk, return and downside objectives?
- How is ownership allocated across investors, rollover, management and future dilution?
- What is the priority, preference, participation and conversion behavior in each outcome?
- Which board, consent, information, transfer and intervention rights are required?
- What fees, carry, monitoring charges and expenses affect economics and alignment?
- Which vehicle and ownership route satisfy investor, tax, regulatory and operational constraints?
- How do future rounds, option pools, earnouts and anti-dilution terms affect each position?
- For additional capital, how do old-money exposure and new-money security interact?
- Are economic, legal, tax, financing and governance terms mutually consistent?
- Which investor-specific constraints remain unresolved, waived or accepted?

- **Required inputs:** ENT_DEAL, ENT_DECISION_RECORD, ENT_CAPITAL_STRUCTURE, ENT_AUTHORITY_RULE, ENT_RISK
- **Optional inputs:** ENT_SECURITY, ENT_SOURCES_USES, ENT_GOVERNANCE_RIGHT, ENT_FUND_VEHICLE, ENT_DILIGENCE_FINDING
- **Required outputs:** ENT_SECURITY, ENT_CAPITAL_STRUCTURE, ENT_SOURCES_USES, ENT_GOVERNANCE_RIGHT, ENT_DILIGENCE_FINDING, ENT_QUESTION
- **Reasoning operators:** OP_WATERFALL, OP_SCENARIO, OP_GOV_ALIGN, OP_CONSISTENCY, OP_OLD_NEW, OP_RISK_RECOMMEND
- **Materiality behavior:** Material mismatch between approved economics and proposed structure blocks documentation; protection cannot be assumed from document labels or sponsor intent.
- **Authority behavior:** Changes to approved economic terms require the authority specified by the decision record; legal and tax specialists approve technical implementation within delegated scope.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Changed security or ownership terms stale model, valuation, financing, approval package and execution documents.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Financing / debt package (`financing`)

Tests financing availability and resilience, translates legal definitions into model behavior, and identifies when leverage changes the decision rather than merely increasing returns.

**Governing question:** What debt capacity, pricing, maturity, covenant and liquidity package is feasible across the underwriting cases?

**Subquestions**

- What debt amount is supportable by cash flow, asset value, market appetite and downside resilience?
- What interest, fees, OID and hedging costs apply under each funding scenario?
- How do mandatory amortization, cash sweep and optional repayment affect liquidity and returns?
- Does maturity create refinancing dependence within the expected hold or downside period?
- How are covenants defined, what is headroom, and when can breach occur?
- What minimum cash and liquidity runway exist under operational and timing stress?
- Which financing conditions must be satisfied at signing and closing?
- What collateral, guarantees, priority and intercreditor terms affect recovery and flexibility?
- Which baskets, cure rights and restricted-payment limits constrain value creation or rescue?
- How does the financing package behave when EBITDA, working capital, capex or exit timing deteriorate?

- **Required inputs:** ENT_DEAL, ENT_MODEL_CASE, ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_SOURCES_USES
- **Optional inputs:** ENT_COVENANT, ENT_DILIGENCE_FINDING, ENT_EVIDENCE_ITEM, ENT_RISK, ENT_LEGAL_AGREEMENT
- **Required outputs:** ENT_CAPITAL_STRUCTURE, ENT_SECURITY, ENT_COVENANT, ENT_SOURCES_USES, ENT_DILIGENCE_FINDING, ENT_RISK, ENT_QUESTION
- **Reasoning operators:** OP_RECONCILE, OP_SCENARIO, OP_DOWNSIDE, OP_COVENANT, OP_LIQUIDITY, OP_CONSISTENCY, OP_RISK_RECOMMEND
- **Materiality behavior:** Material financing uncertainty, failed funds-certainty condition, covenant breach in a decision case, or inadequate liquidity blocks final approval or closing unless explicitly accepted under authority.
- **Authority behavior:** Financing specialists validate feasibility; only authorized decision-makers may accept leverage, liquidity or refinancing risk beyond configured policy.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Changed debt term, covenant definition or funding condition stales model, valuation, structure, approval and execution documents; post-close covenant warning may trigger re-underwriting.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Investment committee decisioning (`investment_decision`)

Synthesizes evidence, thesis, model cases, valuation, questions, risks and conditions into an immutable decision basis distinct from the recommendation and from later superseding decisions.

**Governing question:** Should the proposed investment or material action be approved, declined, deferred or conditioned on the current evidence and unresolved risk?

**Subquestions**

- What is the investment thesis, and which assumptions are indispensable to it?
- Which conclusions are supported, disputed, proxy-based or unresolved?
- Which questions remain open, reframed, risk-accepted or immaterial?
- What outcome does the supported base case produce and why is it plausible?
- What can cause permanent capital loss and how does the downside case behave?
- Is entry or current value supported independently of the sponsor or management case?
- Which risks are mitigated, accepted, unresolved or decision-fatal?
- What conditions must be satisfied before signing, closing or funding?
- What exposure is appropriate given return, downside, concentration and portfolio constraints?
- Who is authorized to decide, waive, accept risk and record dissent?

- **Required inputs:** ENT_DEAL, ENT_INVESTMENT_THESIS, ENT_QUESTION_REGISTER, ENT_DILIGENCE_FINDING, ENT_VALUATION_CASE, ENT_RISK
- **Optional inputs:** ENT_MODEL_CASE, ENT_MATERIALITY_ASSESSMENT, ENT_RISK_ACCEPTANCE_RECORD, ENT_EXCEPTION_RECORD, ENT_CHALLENGE_ASSESSMENT, ENT_SOURCES_USES
- **Required outputs:** ENT_DECISION_RECORD, ENT_APPROVAL_RECORD, ENT_RISK_ACCEPTANCE_RECORD, ENT_GATE, ENT_EXCEPTION_RECORD, ENT_QUESTION_REGISTER
- **Reasoning operators:** OP_SOURCE_WEIGHT, OP_FALSIFY, OP_SCENARIO, OP_DOWNSIDE, OP_RISK_RECOMMEND, OP_CONSISTENCY, OP_LINEAGE
- **Materiality behavior:** A decision cannot become effective while a critical question is unresolved, a required gate is failed, or a material input is stale unless an authorized exception and risk acceptance explicitly permit continuation.
- **Authority behavior:** Only actors satisfying the applicable authority rule may approve, decline, condition, waive or commit capital; analytical contributors may recommend but not authorize.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** New material evidence before signing can reopen the decision; later decisions create successors and preserve the original snapshot.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Monitoring (`monitoring`)

Maintains a versioned approved baseline, collects reliable observations, attributes variance, tests covenants and assumptions, and creates alerts rather than merely storing reports.

**Governing question:** How is live exposure performing against the approved underwriting baseline, and has any deviation created a new decision need?

**Subquestions**

- What immutable underwriting and decision snapshot is the comparison baseline?
- Which metrics test the thesis, downside and covenant rather than merely report activity?
- Are current observations reliable, definition-consistent and timely?
- What changed versus plan, and which causal drivers explain the variance?
- How has the forward outlook changed after current performance and actions?
- What do cash conversion, liquidity and funding needs imply?
- What is current and projected covenant headroom under defined terms?
- Are value-creation, integration and remediation milestones on track?
- What is current value, methodology and sensitivity relative to prior marks?
- Which missing, late or conflicting information is itself a risk or trigger?
- Has a material event or broken assumption created a re-underwriting need?

- **Required inputs:** ENT_DEAL, ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD, ENT_DECISION_RECORD, ENT_MODEL_CASE
- **Optional inputs:** ENT_METRIC_DEFINITION, ENT_METRIC_OBSERVATION, ENT_COVENANT, ENT_DOCUMENT_ARTIFACT, ENT_VALUE_CREATION_PLAN, ENT_GOVERNANCE_RIGHT
- **Required outputs:** ENT_MONITORING_RECORD, ENT_METRIC_OBSERVATION, ENT_RISK, ENT_REUNDERWRITING_TRIGGER, ENT_QUESTION, ENT_VALUATION_CASE
- **Reasoning operators:** OP_RECONCILE, OP_VARIANCE, OP_COHORT, OP_COVENANT, OP_LIQUIDITY, OP_CAUSAL, OP_LINEAGE, OP_SOURCE_WEIGHT
- **Materiality behavior:** A configured material variance, covenant warning/breach, liquidity shortfall, repeated data gap, governance event or broken assumption creates a validated trigger or warning according to policy.
- **Authority behavior:** Monitoring may generate alerts automatically; dismissal of a material trigger or acceptance of missing information requires applicable authority and an immutable record.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** A validated trigger opens re-underwriting; resolved variance updates monitoring but does not overwrite the original underwriting baseline.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Re-underwriting (`reunderwriting`)

Uses a validated trigger to compare actuals with immutable underwriting, diagnose broken assumptions, rebuild the model and valuation, and choose among hold, sell, follow-on, restructure, impair or write-off.

**Governing question:** What changed relative to the original approved case, what options exist now, and what action best protects or creates value?

**Subquestions**

- What event or evidence crossed the threshold for re-underwriting?
- What did the original decision assume, approve and accept?
- How do actual operating, cash, leverage and milestone outcomes differ from underwriting?
- Which assumptions broke, which were merely delayed, and what caused the change?
- What is the updated operating, liquidity, covenant and downside case?
- What is current value and security-specific recovery across scenarios?
- What has management or sponsor done, and is the response credible and funded?
- What are feasible hold, sell, follow-on, restructure, impair and write-off options?
- For new capital, what return and protection apply to the incremental investment versus sunk exposure?
- Which action maximizes risk-adjusted value, and what conditions or monitoring reset are required?
- How will the trigger be closed, retained or escalated after the decision?

- **Required inputs:** ENT_DEAL, ENT_REUNDERWRITING_TRIGGER, ENT_DECISION_RECORD, ENT_MONITORING_RECORD, ENT_INVESTMENT_EXPOSURE
- **Optional inputs:** ENT_MODEL_CASE, ENT_VALUATION_CASE, ENT_RISK, ENT_SECURITY, ENT_COVENANT, ENT_OUTCOME_RECORD
- **Required outputs:** ENT_REUNDERWRITING_RECORD, ENT_DECISION_RECORD, ENT_MODEL_CASE, ENT_VALUATION_CASE, ENT_RISK, ENT_ASSUMPTION, ENT_OUTCOME_RECORD
- **Reasoning operators:** OP_VARIANCE, OP_CAUSAL, OP_HIST_FORECAST, OP_SCENARIO, OP_DOWNSIDE, OP_OLD_NEW, OP_WATERFALL, OP_COVENANT, OP_LIQUIDITY, OP_EXIT_ROUTE, OP_RISK_RECOMMEND, OP_LINEAGE
- **Materiality behavior:** A material trigger requires explicit disposition; no action is not an implicit decision. Additional capital must be underwritten on an incremental basis, separately from sunk exposure.
- **Authority behavior:** Hold, follow-on, restructure, sell, impair or write-off decisions require the applicable investment authority; lender/legal/tax authority applies to technical implementation.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Action returns to monitoring with a new approved baseline, routes to execution/funding, or opens exit; unresolved triggers remain active and cannot be archived.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Exit / realization (`exit_realization`)

Compares current executable liquidity with risk-adjusted hold value, transaction certainty, costs, timing and residual claims; it reconciles final proceeds without assuming every outcome is a full sale.

**Governing question:** Should and can the position be realized now, by which route, at what net value, and with what residual exposure or risk?

**Subquestions**

- What event, offer, market window, maturity or thesis change creates an exit decision?
- Which routes are feasible: strategic sale, sponsor sale, public sale, recap, partial sale, liquidation or hold?
- What is executable net value for each route after fees, taxes, debt and waterfall?
- What risk-adjusted value and cash flows are available from continued ownership?
- What conditions, financing, approvals and market risks affect completion probability and timing?
- What is the downside of waiting, including deterioration, market closure and refinancing?
- What exposure, rights, liabilities or restrictions remain after a partial realization?
- When should value be impaired or written off, and which recovery claims remain?
- Do cash proceeds, fees, taxes and position changes reconcile to the outcome?
- What did the outcome reveal about original assumptions, process and evidence quality?

- **Required inputs:** ENT_DEAL, ENT_INVESTMENT_EXPOSURE, ENT_POSITION_RECORD, ENT_VALUATION_CASE, ENT_DECISION_RECORD
- **Optional inputs:** ENT_OUTCOME_RECORD, ENT_PUBLIC_MARKET_TRANSACTION, ENT_SECURITY, ENT_CAPITAL_STRUCTURE, ENT_RISK, ENT_CAPITAL_EVENT
- **Required outputs:** ENT_DECISION_RECORD, ENT_OUTCOME_RECORD, ENT_CAPITAL_EVENT, ENT_POSITION_RECORD, ENT_CLOSING_RECORD, ENT_RISK
- **Reasoning operators:** OP_EXIT_ROUTE, OP_ALT_VALUE, OP_SCENARIO, OP_WATERFALL, OP_RISK_RECOMMEND, OP_RECONCILE, OP_MULTIPLE
- **Materiality behavior:** A realization cannot be treated as closed until proceeds, fees, ownership, residual rights and position records reconcile; a partial exit returns residual exposure to monitoring.
- **Authority behavior:** Exit authorization, impairment or write-off requires investment authority; execution and closing authority confirm legal and economic effectiveness.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Failed process or changed market conditions reopens hold valuation; partial outcome creates a new monitored baseline; final outcome feeds calibration without overwriting original decisions.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Question engine (`question_engine`)

Converts discomfort, contradictory evidence and assumption dependence into testable questions with ownership, evidence requirements, status, materiality, decision impact and reopening conditions.

**Governing question:** What uncertainty must be resolved, by whom, with what evidence, before a decision or action?

**Subquestions**

- What proposition or uncertainty is the question testing?
- What observation would confirm, challenge or falsify the proposition?
- What evidence category, independence and recency are required?
- Which workstream and actor own resolution and by when?
- What decision or gate changes if the answer is adverse or unavailable?
- Is the question open, answered, reframed, risk-accepted, obsolete or closed?
- Does the answer address the question with reliable evidence rather than assertion?
- What later evidence or change should reopen the question?

- **Required inputs:** ENT_DEAL, ENT_QUESTION_REGISTER, ENT_ASSUMPTION, ENT_RISK, ENT_EVIDENCE_ITEM
- **Optional inputs:** ENT_DILIGENCE_FINDING, ENT_INVESTMENT_THESIS, ENT_CHALLENGE_ASSESSMENT, ENT_MATERIALITY_ASSESSMENT
- **Required outputs:** ENT_QUESTION_REGISTER, ENT_QUESTION, ENT_WORKSTREAM_RUN, ENT_MATERIALITY_ASSESSMENT, ENT_EXCEPTION_RECORD
- **Reasoning operators:** OP_FALSIFY, OP_TRIANGULATE, OP_SOURCE_WEIGHT, OP_CONSISTENCY, OP_LINEAGE, OP_RISK_RECOMMEND
- **Materiality behavior:** A critical question must be answered, risk-accepted or explicitly excepted before the affected gate can be satisfied; absence of response is not resolution.
- **Authority behavior:** Question owners may propose resolution; authority to accept unresolved material uncertainty follows the applicable authority rule.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** New contradictory evidence, stale answer, changed assumption or downstream inconsistency reopens the question and dependent workstream outputs.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Adversarial challenge / why-not-to-invest (`question_engine`)

Applies structured challenge to thesis, adjustments, sponsor credibility, management execution, security, valuation, exit and missing evidence; the function is universal even when the historical artifact is configurable.

**Governing question:** What must be true for the case to work, what evidence could disprove it, and where is the downside understated?

**Subquestions**

- Which propositions must be true for the recommendation to work?
- Does the downside reflect plausible failure mechanisms and feedback loops?
- Which earnings adjustments would fail under an independent recurrence test?
- Are we underwriting independent evidence or sponsor credibility?
- What execution claim lacks demonstrated capability, owner or milestone?
- Where can priority, dilution, covenants or waterfall fail to protect capital?
- Which valuation input or multiple has the weakest independent support?
- What if the expected exit route, timing or buyer set does not materialize?
- What material evidence is absent, stale, conflicted or common-sourced?
- Would we invest the incremental capital if we had no existing exposure?

- **Required inputs:** ENT_INVESTMENT_THESIS, ENT_ASSUMPTION, ENT_MODEL_CASE, ENT_VALUATION_CASE, ENT_RISK
- **Optional inputs:** ENT_QUESTION_REGISTER, ENT_DILIGENCE_FINDING, ENT_SECURITY, ENT_SPONSOR_TRACK_RECORD, ENT_KEY_PERSON_DEPENDENCY
- **Required outputs:** ENT_CHALLENGE_ASSESSMENT, ENT_QUESTION, ENT_RISK, ENT_ASSUMPTION, ENT_EXCEPTION_RECORD
- **Reasoning operators:** OP_FALSIFY, OP_DOWNSIDE, OP_SOURCE_WEIGHT, OP_MGMT_SPONSOR, OP_HIST_FORECAST, OP_WATERFALL, OP_EXIT_ROUTE, OP_RISK_RECOMMEND
- **Materiality behavior:** A material thesis component without a credible disconfirmation test remains challenged; a standalone presentation is optional, but the challenge disposition is not.
- **Authority behavior:** Only authorized decision-makers may accept a material challenged assumption; the challenger need not hold approval authority.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** New sponsor claim, model revision or adverse evidence triggers another challenge cycle and may reopen questions.
- **Structural classification:** MIXED
- **Configuration level:** mixed_or_uncertain

### Evidence provenance and sufficiency (`source_case_ingestion`)

Maintains source, version, extraction, independence, reliability, conflict and lineage so that a conclusion cannot be stronger than its evidence.

**Governing question:** Is the evidence available, relevant, reliable and sufficient to support the proposition for the current phase?

**Subquestions**

- Is the evidence physically and permission-wise available for the intended use?
- Does the evidence directly address the proposition, period, perimeter and definition?
- Is the source method, incentive, control environment and completeness reliable enough?
- Is corroboration genuinely independent or derived from a common source?
- Is the evidence current enough for the decision phase and volatility of the fact?
- Does it cover the required population, period and exceptions?
- Is the combined evidence sufficient for the phase, confidence and materiality?

- **Required inputs:** ENT_SOURCE_MATERIAL_SET, ENT_DOCUMENT_ARTIFACT, ENT_DOCUMENT_VERSION, ENT_EVIDENCE_ITEM
- **Optional inputs:** ENT_PERMISSION_POLICY, ENT_ACCESS_GRANT, ENT_QUESTION, ENT_ASSUMPTION, ENT_DILIGENCE_FINDING
- **Required outputs:** ENT_EVIDENCE_ITEM, ENT_DILIGENCE_FINDING, ENT_QUESTION, ENT_EXCEPTION_RECORD, ENT_MATERIALITY_ASSESSMENT
- **Reasoning operators:** OP_SOURCE_WEIGHT, OP_TRIANGULATE, OP_RECONCILE, OP_CONSISTENCY, OP_LINEAGE, OP_FALSIFY
- **Materiality behavior:** An evidence item can exist without being sufficient; phase-specific sufficiency must be explicitly assessed before a conclusion or gate relies on it.
- **Authority behavior:** Permission controls use; workstream owners assess relevance and reliability; authority may accept residual uncertainty but cannot retroactively make unreliable evidence reliable.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Newer, corrected or conflicting evidence may supersede an evidence item, challenge linked assumptions, reopen questions and stale downstream outputs while preserving history.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Materiality and risk acceptance (`investment_decision`)

Applies configurable materiality rules to findings, questions and risks, separates technical assessment from authority, and records any override or risk acceptance immutably.

**Governing question:** Does the uncertainty or risk matter enough to block, warn, reopen, trigger or permit continuation, and who may accept it?

**Subquestions**

- What finding, question, risk or condition is being assessed?
- Which configurable rule, threshold or decision sensitivity applies?
- What magnitude, probability, timing, reversibility and correlated exposure result?
- Should the result block, warn, reopen, trigger or permit continuation?
- What control or mitigant changes residual risk, and is it evidenced?
- Who may accept or override the residual risk, for how long and under what conditions?

- **Required inputs:** ENT_MATERIALITY_ASSESSMENT, ENT_RISK, ENT_DILIGENCE_FINDING, ENT_QUESTION, ENT_AUTHORITY_RULE
- **Optional inputs:** ENT_DECISION_RECORD, ENT_GATE, ENT_EXCEPTION_RECORD, ENT_RISK_ACCEPTANCE_RECORD, ENT_APPROVAL_RECORD
- **Required outputs:** ENT_MATERIALITY_ASSESSMENT, ENT_RISK_ACCEPTANCE_RECORD, ENT_EXCEPTION_RECORD, ENT_GATE, ENT_APPROVAL_RECORD
- **Reasoning operators:** OP_SOURCE_WEIGHT, OP_SCENARIO, OP_RISK_RECOMMEND, OP_CONSISTENCY, OP_LINEAGE
- **Materiality behavior:** Materiality must produce an executable consequence. No blocker is waived by silence, elapsed time or document circulation.
- **Authority behavior:** Only an actor satisfying the configured authority rule may accept risk or override a blocker; permission to view or edit does not confer authority.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Changed magnitude, probability, evidence or decision context expires or reopens the assessment and may invalidate prior acceptance.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

### Assumption lineage and staleness propagation (`question_engine`)

Preserves assumption versions and historical decision snapshots while propagating challenge, supersession and staleness to dependent analytical objects.

**Governing question:** Which evidence, questions, models, valuations and decisions depend on each assumption, and what must reopen when it changes?

**Subquestions**

- What is the stable identity and current version of the assumption?
- Which evidence supports, challenges or supersedes it?
- Which model cases, valuations, decisions, risks and questions consume it?
- Is it proposed, supported, challenged, accepted, broken, superseded or retired?
- What change reopens it and what downstream objects become stale?

- **Required inputs:** ENT_ASSUMPTION, ENT_EVIDENCE_ITEM, ENT_QUESTION, ENT_MODEL_CASE, ENT_DECISION_RECORD
- **Optional inputs:** ENT_DILIGENCE_FINDING, ENT_VALUATION_CASE, ENT_MONITORING_RECORD, ENT_REUNDERWRITING_TRIGGER, ENT_EXCEPTION_RECORD
- **Required outputs:** ENT_ASSUMPTION, ENT_QUESTION, ENT_EXCEPTION_RECORD, ENT_WORKSTREAM_RUN, ENT_REUNDERWRITING_TRIGGER
- **Reasoning operators:** OP_LINEAGE, OP_CONSISTENCY, OP_FALSIFY, OP_VARIANCE, OP_SOURCE_WEIGHT
- **Materiality behavior:** A changed material assumption stales dependent outputs according to lineage; continued use requires recomputation or an explicit, authorized exception.
- **Authority behavior:** Analytical owners may create versions and mark staleness; only the applicable authority can accept use of a stale material output for a decision.
- **Human judgment:** scope and proposition definition; source reliability; causal interpretation; materiality; residual uncertainty; recommendation or acceptance
- **Automatable components:** ingestion and extraction; definition checks; reconciliation tests; lineage capture; variance calculation; threshold alerts; staleness propagation; structured view generation
- **Feedback loops:** Evidence challenges assumption; assumption stales model; model stales valuation; valuation stales approval package; term changes stale execution documents; monitoring creates re-underwriting trigger.
- **Structural classification:** LOAD-BEARING
- **Configuration level:** domain_logic

## 7. Permission, authority, and governance model

### 7.1 Control-plane separation

- Permission and authority are distinct and independently evaluated.
- Ownership, preparation, recommendation, approval, capital authorization, and funding execution are distinct responsibilities.
- Approval, waiver, override, risk acceptance, and capital action are never inferred from silence, circulation, attendance, or elapsed time.
- Every authority action produces an immutable record referencing the effective rule, role assignment, permission evaluations, evidence basis, conditions, conflicts, and expiry.
- Delegation is explicit, scoped, time-bound, revocable, and prohibited for configured non-delegable actions.
- Conflict recusal recalculates quorum; a conflicted actor cannot approve an exception to the actor’s own conflict.
- System administration cannot confer investment authority.

### 7.2 Contextual roles

| Role ID | Role | Scope | Authority types | Delegation |
| --- | --- | --- | --- | --- |
| ROLE_PERSON_PRINCIPAL | Person principal | Assigned by object and lifecycle scope. |  | May receive scoped delegated roles. |
| ROLE_ORGANIZATION_PRINCIPAL | Organization principal | Deal, company, agreement, vehicle, or global scope. |  | Delegation operates through authorized representatives, not by implication. |
| ROLE_DEAL_TEAM_MEMBER | Deal team member | Deal scope. | recommend | May receive limited task delegation; authority delegation is separate. |
| ROLE_WORKSTREAM_OWNER | Workstream owner | Workstream run within a deal. | analytical_signoff; recommend | May delegate preparation tasks but not final accountability unless reassigned. |
| ROLE_WORKSTREAM_CONTRIBUTOR | Workstream contributor | Workstream run. |  | Preparation tasks may be delegated. |
| ROLE_DEAL_LEAD | Deal lead | Deal scope. | screen; approve_scope; recommend; request_authority_action | Operational coordination may be delegated; accountability remains explicit. |
| ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment committee member | Decision and outcome actions for a deal. | approve; reject; defer; condition; accept_risk; sell; impair; write_off; approve_follow_on | Delegation is governed by the authority rule and may be prohibited for collective votes. |
| ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Committee chair or decision owner | Authority action scope. | record_collective_outcome; defer; confirm_conditions; confirm_quorum | Substitution must be explicit and time-bounded. |
| ROLE_CAPITAL_AUTHORITY_HOLDER | Capital authority holder | Vehicle, deal, capital event, and exposure scope. | commit_capital; release_funds; approve_follow_on; approve_restructuring; sell; impair; write_off | Delegation is only permitted if the authority rule expressly permits it. |
| ROLE_MODEL_OWNER | Model owner | Analytical model and model-case scope. | submit_model_for_review | Preparation may be delegated; identity of owner remains recorded. |
| ROLE_MODEL_REVIEWER | Model reviewer | Analytical model, model case, and valuation case scope. | analytical_signoff; approve_model_basis; approve_valuation_basis | May be delegated only to a qualified independent reviewer. |
| ROLE_LEGAL_REVIEWER | Legal reviewer | Legal workstream and transaction-document scope. | legal_signoff; confirm_legal_condition; recommend_waiver | Technical work may be delegated; final legal conclusion requires qualified sign-off. |
| ROLE_TAX_REVIEWER | Tax reviewer | Tax workstream and structure scope. | tax_signoff; recommend_structure; identify_residual_tax_risk | Technical work may be delegated to qualified contributors. |
| ROLE_FINANCE_FUNDING_OPERATOR | Finance or funding operator | Vehicle, closing, capital event, and position scope. | confirm_funds_ready; execute_authorized_funding; reconcile_position | Operational tasks may be delegated within controlled scope. |
| ROLE_RISK_COMPLIANCE_REVIEWER | Risk or compliance reviewer | Deal, workstream, gate, and authority scope. | review_materiality; review_risk_acceptance; review_exception; confirm_policy_compliance | May delegate evidence gathering but not independent review accountability. |
| ROLE_BOARD_REPRESENTATIVE_OBSERVER | Board representative or observer | Company governance and portfolio monitoring scope. | exercise_governance_right_if_authorized; escalate_monitoring_issue | Delegation follows the underlying governance right. |
| ROLE_EXTERNAL_ADVISER | External adviser | Assigned deal, workstream, document, or agreement scope. | technical_opinion | Subcontracting requires explicit permission and scope. |
| ROLE_COUNTERPARTY_REPRESENTATIVE | Sponsor or seller representative | Counterparty, source-material, and agreement scope. | counterparty_consent; authorized_signature_if_applicable | Authority derives from the represented organization and transaction documents. |
| ROLE_FINANCING_PARTY | Lender or financing party | Financing, agreement, covenant, and closing scope. | lender_consent; covenant_waiver; funding_confirmation | Delegation follows financing documents and authorized representatives. |
| ROLE_SYSTEM_ADMINISTRATOR | System administrator | Global or configured technical scope. |  | Technical duties may be delegated with expiry and logging. |
| ROLE_DELEGATED_AUTHORITY_HOLDER | Delegated authority holder | Specific action, object, threshold, and time window. | only_actions_explicitly_delegated | Cannot exceed scope, threshold, object, duration, or subdelegation rule. |

### 7.3 Authority actions

| Action ID | Authority action | Subject | Role | Approval structure | Result record |
| --- | --- | --- | --- | --- | --- |
| AUTH_001 | Approve progression to diligence | ENT_DECISION_RECORD | ROLE_DEAL_LEAD | Single screening authority or configured collective authority. | ENT_APPROVAL_RECORD |
| AUTH_002 | Approve material diligence scope | ENT_WORKSTREAM_RUN | ROLE_DEAL_LEAD | Single accountable decision owner with workstream-owner consultation. | ENT_APPROVAL_RECORD |
| AUTH_003 | Accept unresolved diligence item | ENT_QUESTION | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Authority rule may require single or collective investment authority. | ENT_APPROVAL_RECORD |
| AUTH_004 | Accept material risk | ENT_RISK_ACCEPTANCE_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Collective or threshold-based investment authority. | ENT_APPROVAL_RECORD |
| AUTH_005 | Approve valuation basis | ENT_VALUATION_CASE | ROLE_MODEL_REVIEWER | Independent analytical sign-off; investment authority adopts the basis separately. | ENT_APPROVAL_RECORD |
| AUTH_006 | Approve recommendation | ENT_DECISION_RECORD | ROLE_DEAL_LEAD | Recommendation sign-off by accountable deal owner; not capital authority. | ENT_APPROVAL_RECORD |
| AUTH_007 | Approve investment | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Collective or configured threshold-based investment authority with quorum. | ENT_APPROVAL_RECORD |
| AUTH_008 | Conditionally approve investment | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Collective or configured threshold-based authority. | ENT_APPROVAL_RECORD |
| AUTH_009 | Defer decision | ENT_DECISION_RECORD | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Decision owner records deferral under the applicable authority process. | ENT_APPROVAL_RECORD |
| AUTH_010 | Decline investment | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Screening authority or investment authority according to stage and threshold. | ENT_APPROVAL_RECORD |
| AUTH_011 | Approve signing | ENT_EXECUTION_DOCUMENT_SET | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Investment/signing authority plus required legal sign-off. | ENT_APPROVAL_RECORD |
| AUTH_012 | Waive signing condition | ENT_EXCEPTION_RECORD | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Applicable authority rule plus legal finding and risk acceptance where material. | ENT_APPROVAL_RECORD |
| AUTH_013 | Approve closing | ENT_CLOSING_RECORD | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Closing authority with legal and funding readiness confirmations. | ENT_APPROVAL_RECORD |
| AUTH_014 | Waive closing condition | ENT_EXCEPTION_RECORD | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Applicable authority rule plus required technical sign-offs. | ENT_APPROVAL_RECORD |
| AUTH_015 | Commit capital | ENT_CAPITAL_EVENT | ROLE_CAPITAL_AUTHORITY_HOLDER | Single or collective authority according to vehicle, amount, and action. | ENT_APPROVAL_RECORD |
| AUTH_016 | Release funds | ENT_CAPITAL_EVENT | ROLE_CAPITAL_AUTHORITY_HOLDER | Dual control: valid capital authority plus funding-operator execution. | ENT_APPROVAL_RECORD |
| AUTH_017 | Approve follow-on or rescue capital | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment and capital authority under configured threshold. | ENT_APPROVAL_RECORD |
| AUTH_018 | Approve restructuring | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment authority plus legal, tax, financing, and structure sign-offs as applicable. | ENT_APPROVAL_RECORD |
| AUTH_019 | Approve impairment or write-off | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment authority with valuation and position-control evidence. | ENT_APPROVAL_RECORD |
| AUTH_020 | Approve exit or full realization | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment authority with execution and closing confirmations. | ENT_APPROVAL_RECORD |
| AUTH_021 | Approve partial exit | ENT_DECISION_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment authority with explicit residual-exposure treatment. | ENT_APPROVAL_RECORD |
| AUTH_022 | Approve residual exposure | ENT_OUTCOME_RECORD | ROLE_INVESTMENT_COMMITTEE_MEMBER | Investment authority confirms treatment and monitoring/closure status. | ENT_APPROVAL_RECORD |
| AUTH_023 | Override a blocker | ENT_EXCEPTION_RECORD | ROLE_COMMITTEE_CHAIR_DECISION_OWNER | Override authority specified by the applicable authority rule; may require collective approval. | ENT_APPROVAL_RECORD |
| AUTH_024 | Revive a terminated or stalled process | ENT_DECISION_RECORD | ROLE_DEAL_LEAD | Screening authority or investment authority based on prior stage and requested route. | ENT_APPROVAL_RECORD |

### 7.4 Permission policies

Permission policies are evaluated for a contextual role assignment, object, action, scope, lifecycle stage, sensitivity, ownership, relationship, and materiality context. The evaluation result is `allow`, `deny`, `conditional`, or `require_approval`, and is written as an immutable permission-evaluation record. Permission inheritance may narrow access but cannot create investment authority.

### 7.5 Delegation, conflicts, and segregation

- Delegation specifies action types, object scope, thresholds, start, expiry, revocation, and non-delegable exclusions.
- Conflicted actors are recused and quorum is recalculated.
- No actor approves an exception to the actor’s own conflict.
- Preparation and approval are separated where the authority class requires independent review.
- Model ownership and model approval are distinct.
- Recommendation and capital authorization are distinct.
- Capital authorization and funding execution are distinct.
- System administration does not confer investment authority.

### 7.6 Immutable governance records

| Record | Canonical entity | Trigger | Expiry | Supersession |
| --- | --- | --- | --- | --- |
| permission_grant | ENT_ACCESS_GRANT | Permission is granted. | Status becomes expired or revoked; historical grant remains. | Successor grant replaces scope without deleting prior grant. |
| permission_denial | ENT_ACCESS_GRANT | Permission request is denied. | No expiry unless request is resubmitted. | A later grant is a separate successor record. |
| permission_policy_evaluation | DELTA_ENT_PERMISSION_EVALUATION_RECORD | A sensitive action requests permission evaluation. | Evaluation is point-in-time and does not mutate. | A new action or changed context creates a new evaluation. |
| approval | ENT_APPROVAL_RECORD | Authority approves an action or object. | May lapse under attached conditions or rule; record remains immutable. | Successor approval links to prior record and marks prior superseded if appropriate. |
| rejection | ENT_APPROVAL_RECORD | Authority rejects an action or object. | No automatic expiry. | A later approval is a successor, not an edit. |
| deferral | ENT_DECISION_RECORD | Authority defers a decision. | Expires at next-review date or condition deadline. | Successor decision resolves or extends deferral. |
| conditional_approval | ENT_APPROVAL_RECORD | Authority grants approval subject to explicit conditions. | Lapses on condition deadline or material change. | Condition change requires successor approval. |
| waiver | ENT_EXCEPTION_RECORD | Authority waives a gate or condition. | Expires at stated date, event, or changed evidence. | Extension or changed scope creates successor exception. |
| override | ENT_EXCEPTION_RECORD | Authority overrides a blocker or materiality result. | Expires at stated date or context change. | New override creates successor record. |
| risk_acceptance | ENT_RISK_ACCEPTANCE_RECORD | Authority accepts residual risk or unresolved question. | Expires or reopens on review date, trigger, or material evidence change. | Successor acceptance links to prior acceptance. |
| delegation | ENT_ROLE_ASSIGNMENT | Authority is delegated for a scoped period. | Automatically expires or is revoked. | New assignment supersedes or replaces scope. |
| recusal | DELTA_ENT_RECUSAL_RECORD | A conflict requires an actor to withdraw from an authority process. | Ends only by explicit resolution or process completion. | Successor resolution record closes recusal. |
| dissent | DELTA_ENT_DISSENT_RECORD | An eligible participant records disagreement with a collective decision. | No expiry. | Clarification appends a successor note; original remains. |
| capital_commitment | ENT_CAPITAL_EVENT | Authorized capital commitment is created. | Unused commitment may expire under rule; historical commitment remains. | Amendment or cancellation creates a successor capital event. |
| funding_release | ENT_CAPITAL_EVENT | Authorized funds are released. | No expiry after execution; failed release is separately recorded. | Correction creates a new capital event and reconciliation link. |
| transition_authorization | ENT_APPROVAL_RECORD | An authority-dependent workflow transition is authorized. | Lapses when gate, evidence, conditions, or rule changes. | Reapproval creates successor record. |
| exception | ENT_EXCEPTION_RECORD | A state, blocker, rule, or process exception is requested or approved. | Expires on date, event, or context change. | Successor exception required for changes. |
| supersession | ENT_APPROVAL_RECORD | An approval or authority basis is superseded. | Permanent historical status. | Successor remains separate. |
| permission_evaluation | ENT_PERMISSION_EVALUATION_RECORD | A permission-sensitive action is requested. | Re-evaluate when policy, role, object sensitivity, relationship, or action scope changes. | A later evaluation is a separate record. |
| delegation | ENT_DELEGATION_RECORD | Scoped authority is delegated. | Expires automatically or is explicitly revoked. | Scope changes require a successor delegation. |
| recusal | ENT_RECUSAL_RECORD | A conflict requires removal from review, approval, or quorum. | Ends only under the recorded scope or successor action. | Changes require a successor record. |
| dissent | ENT_DISSENT_RECORD | A participant records a reasoned disagreement. | No silent expiry. | A clarification or withdrawal creates a successor record. |
| condition | ENT_CONDITION_RECORD | An approval, gate, execution, funding, or outcome action is conditional. | Condition may expire or fail under its explicit rule. | Changed condition requires a successor record. |
| workflow_event | ENT_WORKFLOW_EVENT | Any controlled state, transition, workstream, permission, or authority event occurs. | Never expires. | Never overwritten. |

## 8. Outcome and re-underwriting loop

1. A decision record freezes the approved thesis, assumptions, risks, model cases, valuation cases, terms, evidence basis, conditions, and authority record.
2. Closing creates the legal and capital-position basis for monitoring.
3. Monitoring collects metric observations, board/sponsor/lender evidence, covenant tests, valuation changes, events, and data-quality gaps against the approved baseline.
4. A material breach, variance, liquidity issue, covenant issue, changed term, sponsor/management issue, delayed exit, strategic event, or other configured condition creates a re-underwriting trigger.
5. Re-underwriting attributes variance, reopens questions, changes or rejects assumptions, updates model and valuation cases, and assesses old-money exposure separately from new-money economics where additional capital is requested.
6. A successor decision authorizes hold, sell, follow-on, rescue, restructure, impair, defer, or another action. It does not overwrite the prior decision.
7. Exit and realization reconcile proceeds, costs, residual exposure, position records, capital events, and the outcome record. Partial or failed exits return the remaining exposure to monitoring or re-underwriting.
8. The closed archive retains all identities, versions, events, decisions, approvals, dissent, exceptions, and outcomes.

## 9. Enforce-versus-configure register

| Control | Component | Classification | Rule | Rationale |
| --- | --- | --- | --- | --- |
| EC_001 | Stable identity and lineage | ENFORCE | Stable entity identities, version lineage, supersession, and immutable decision references are mandatory. | Without stable identity and lineage, historical decisions cannot be audited or safely reopened. |
| EC_002 | Explicit workflow events | ENFORCE | Every state or transition change requires an explicit triggering event and append-only workflow record. | Time, silence, document circulation, or user interpretation cannot determine state. |
| EC_003 | State predicates | ENFORCE | Entry, active, completion, and exit predicates must resolve deterministically from canonical objects and statuses. | Deterministic resolution is required for code, audit, and recovery. |
| EC_004 | Transition controls | ENFORCE | Triggers, guards, gates, permission checks, authority actions, materiality behavior, exceptions, and idempotency are mandatory. | A transition is a controlled business action, not a sequence hint. |
| EC_005 | Unhappy paths | ENFORCE | Decline, defer, abandonment, failure, backtrack, skip, revival, partial outcome, and residual exposure are first-class paths. | Exceptional outcomes affect capital, accountability, and analytical freshness. |
| EC_006 | Permission versus authority | ENFORCE | Permission to access or edit never creates authority to approve, waive, accept risk, commit capital, or release funds. | Access administration and investment authority are distinct control planes. |
| EC_007 | Approval records | ENFORCE | Every approval, waiver, override, risk acceptance, commitment, funding release, or exit authorization creates an immutable record. | Authority cannot be inferred or overwritten. |
| EC_008 | Evidence sufficiency | ENFORCE | Evidence availability, relevance, reliability, completeness, recency, corroboration, sufficiency, and conclusion support remain distinct. | A document’s existence does not make a conclusion decision-ready. |
| EC_009 | Question linkage | ENFORCE | Material uncertainty becomes an owned question linked to assumptions, evidence needs, status, resolution, decision effect, and reopening conditions. | Unstructured discomfort cannot be governed or tested. |
| EC_010 | Model versus valuation | ENFORCE | Financial modeling and valuation/returns are separate workstreams connected by typed model-case dependencies. | Computation of operating and financing outcomes is epistemically distinct from applying valuation methods and security waterfalls. |
| EC_011 | Staleness propagation | ENFORCE | Material upstream changes stale downstream assumptions, models, valuations, decision packages, execution documents, or monitoring conclusions. | Downstream outputs cannot remain current after their basis changes. |
| EC_012 | Monitoring baseline | ENFORCE | Monitoring tests actual evidence against an immutable approved baseline and may create a re-underwriting trigger. | Storage of periodic reporting alone does not control investment performance. |
| EC_013 | Re-underwriting | ENFORCE | Re-underwriting compares current evidence with the approved basis and supports hold, sell, follow-on, restructure, impair, or other successor decisions. | Portfolio decisions require explicit outcome calibration. |
| EC_014 | Conflict and segregation | ENFORCE | Recusal, quorum recalculation, self-approval prohibitions, preparer/approver separation, and commitment/funding separation apply where configured by authority class. | Control quality depends on independent authority and attributable action. |
| EC_015 | Materiality thresholds | CONFIGURE | Numerical and qualitative materiality thresholds are governed by versioned firm policy. | Materiality depends on mandate, exposure, stage, object type, and risk appetite. |
| EC_016 | Role labels and quorum | CONFIGURE | Role names, committee composition, quorum, authority limits, and delegation eligibility are configurable. | Governance structures differ while the underlying authority mechanics remain constant. |
| EC_017 | Document templates | CONFIGURE | Templates, section ordering, labels, and presentation conventions are configurable views over canonical objects. | Presentation convention should not define domain identity. |
| EC_018 | Evidence phase thresholds | CONFIGURE | Minimum evidence categories, recency, corroboration, proxy acceptance, and waiver authority vary by phase and policy. | Screening and capital commitment require different proof levels. |
| EC_019 | Valuation methods | CONFIGURE | Permitted valuation methods, peer criteria, sensitivity ranges, and scenario weighting are configurable by asset and mandate. | No single method applies to every asset or security. |
| EC_020 | Archetype extensions | CONFIGURE | Carve-out, founder, public-market, auction, buy-and-build, rescue, and sponsor-context extensions activate under explicit conditions. | The universal core should not force irrelevant objects onto every transaction. |
| EC_021 | Workstream review cadence | CONFIGURE | Review frequency, monitoring schedules, escalation windows, and service levels are configurable. | Timing depends on exposure, volatility, covenants, and policy. |
| EC_022 | Automation level | CONFIGURE_WITH_GUARDRAILS | Extraction, reconciliation, calculation, alerts, and structured views may be automated; causal judgment, materiality, recommendation, risk acceptance, and authority remain explicitly assigned. | Automation should reduce movement and consistency work without obscuring judgment or authority. |

## 10. Data and object model

The implementable model is defined in `data_object_model.json` and `data_object_model.md`. The following rules govern all objects:

- A successful transition updates the current-state projection and appends its event atomically.
- An authority action is effective only when permission, role eligibility, authority rule, quorum, conflict, evidence, materiality, condition, and expiry checks succeed.
- A stale analytical object cannot satisfy a final-output gate unless an explicit approved exception permits provisional use.
- Historical approval, decision, evidence, assumption, model, valuation, and term versions remain addressable after supersession.
- Capital commitment and funding release are separate actions and records.
- Skipped states and overridden blockers create explicit exception or waiver records.
- Object deletion cannot remove a referenced historical basis; archival preserves identity and lineage.

### Draft versus committed

- Draft analysis is editable within its version but non-binding.
- Review or analytical approval does not commit capital.
- Investment approval remains approved-but-not-committed unless the authority contract explicitly makes it binding.
- Capital commitment and funding release are separate authority actions, records, and audit events.

## 11. Product requirements

| ID | Priority | Capability | Requirement |
| --- | --- | --- | --- |
| PR_001 | MUST | Canonical object registry | Create and maintain stable identities, aliases, relationships, current projections, versions, supersession, and archive status for canonical objects. |
| PR_002 | MUST | Deterministic state resolution | Resolve one primary workflow state from explicit predicates and precedence, without user interpretation. |
| PR_003 | MUST | Controlled transitions | Execute transitions only from explicit events after guard, gate, permission, authority, materiality, condition, and idempotency checks. |
| PR_004 | MUST | Unhappy-path execution | Support decline, defer, stall, abandonment, failure, backtrack, skip, revival, partial exit, residual exposure, and permanent closure. |
| PR_005 | MUST | Typed workstream orchestration | Start, block, complete, reopen, and parallelize workstreams according to typed input/output and dependency contracts. |
| PR_006 | MUST | Question engine | Create, assign, link, resolve, reopen, and escalate questions with assumption, evidence, owner, phase, and decision-impact lineage. |
| PR_007 | MUST | Evidence provenance | Preserve source, permitted use, version, extraction, relevance, reliability, recency, completeness, corroboration, and sufficiency. |
| PR_008 | MUST | Reasoning records | Capture analytical proposition, evidence, operator, alternatives, finding, confidence, uncertainty, and downstream effect. |
| PR_009 | MUST | Assumption lifecycle | Version assumption states and preserve the exact assumption versions used by each model, valuation, and decision. |
| PR_010 | MUST | Financial model control | Maintain model cases, checks, scenarios, sensitivities, capital structure, debt, liquidity, and return outputs with lineage and staleness. |
| PR_011 | MUST | Valuation and waterfall control | Maintain valuation inputs, methods, enterprise-to-equity bridges, security waterfalls, dilution, returns, downside, and hold-versus-sell cases separately from financial models. |
| PR_012 | MUST | Evidence sufficiency | Evaluate phase-specific relevance, reliability, completeness, recency, corroboration, proxy acceptance, confidence, and residual uncertainty. |
| PR_013 | SHOULD | Adversarial challenge | Support structured challenges to thesis, downside, adjustments, execution, sponsor/management credibility, security, valuation, exit, missing evidence, and old-money/new-money economics. |
| PR_014 | MUST | IC decision package | Assemble a versioned decision basis with recommendation, supporting and opposing evidence, unresolved questions, risks, model and valuation versions, conditions, dissent, and authority record. |
| PR_015 | MUST | Execution conditions | Track signing, closing, funding, and other conditions with evidence, status, waiver authority, expiry, and successor lineage. |
| PR_016 | MUST | Monitoring baseline | Compare metric observations, covenants, reporting, events, and valuation updates against the immutable approved baseline. |
| PR_017 | MUST | Trigger and re-underwriting loop | Create re-underwriting triggers, diagnose variances, update assumptions/models/valuations, and support hold, sell, follow-on, restructure, impair, or other successor decisions. |
| PR_018 | MUST | Outcome and realization | Track exit routes, sale decisions, proceeds, costs, partial outcomes, residual exposure, write-offs, and reconciliation to position and capital records. |
| PR_019 | MUST | Permission evaluation | Evaluate object/action permission independently from authority and create immutable permission-evaluation records. |
| PR_020 | MUST | Authority actions | Require explicit, effective authority rules and records for approval, rejection, deferral, waiver, risk acceptance, signing, closing, commitment, funding, follow-on, restructure, impairment, exit, override, and revival. |
| PR_021 | MUST | Delegation and conflict | Support scoped delegation, expiry, revocation, recusal, quorum recalculation, self-approval prevention, and segregation of duties. |
| PR_022 | MUST | Staleness propagation | Create staleness records and reopen/recompute dependent workstreams when material upstream evidence, assumptions, terms, models, or baselines change. |
| PR_023 | MUST | Immutable audit trail | Preserve workflow, permission, authority, analytical, capital, exception, and outcome events with actor-role attribution and idempotency. |
| PR_024 | MUST | Materiality engine | Apply versioned configurable rules that produce explicit block, warn, reopen, trigger, escalate, accept, permit, or terminate consequences. |
| PR_025 | SHOULD | Archetype activation | Activate only the objects, relationships, questions, workstreams, and gates required by the transaction archetype. |
| PR_026 | SHOULD | Structured document views | Generate and ingest document representations without treating a document as the underlying decision, finding, assumption, or authority object. |
| PR_027 | MUST | Automation boundary | Automate extraction, reconciliation, calculation, consistency, lineage, alerts, and views while requiring attributed human judgment and authority where specified. |
| PR_028 | MUST | Configuration management | Version role definitions, policies, authority rules, thresholds, templates, methods, archetype extensions, retention, and review cadence. |
| PR_029 | MUST | Data quality and exception handling | Surface missing, conflicting, stale, inaccessible, or definition-inconsistent objects and require explicit disposition. |
| PR_030 | SHOULD | Exportable machine contracts | Expose the final state, graph, ontology, epistemic, governance, and requirement contracts in machine-readable form for downstream implementation planning. |

## 12. Implementation boundaries

This specification defines domain objects, state and transition contracts, workstream dependencies, reasoning and proof contracts, governance controls, versioning, staleness, and product behavior. It intentionally does not define:

- application screens or user journeys;
- API endpoints or integration protocols;
- physical database tables or migrations;
- vendor-specific identity, storage, workflow, document, or analytics services;
- organization-specific people, groups, committees, thresholds, or authority limits;
- implementation code;
- model formulas, valuation templates, legal clause libraries, or investment recommendations.

Implementation may choose technologies and interfaces freely provided the structural contracts, identities, lineage, immutable records, authority separations, and enforce-versus-configure boundaries remain intact.
