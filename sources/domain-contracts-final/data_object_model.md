# PE Buyout Data and Object Model

## Object-state architecture

Canonical objects use six complementary state mechanisms:

1. **Stable identity** — identifiers are immutable and never reused.
2. **Current projection** — operational fields expose the current state without erasing history.
3. **Versioned analysis** — analytical changes create successor versions.
4. **Immutable decision basis** — decisions and authority records reference exact versions and snapshots.
5. **Append-only events** — workflow, governance, capital, permission, and outcome events are append-only.
6. **Supersession** — successor objects link to prior objects; supersession does not delete or rewrite them.

## Draft, approval, commitment, and funding

- A draft analytical object may be edited within its version until submitted or referenced by a controlled record.
- A reviewed or approved analytical object remains a representation, not a capital commitment.
- An approved investment decision is **approved but not committed** unless the applicable authority contract explicitly makes it binding.
- A capital commitment exists only when the capital-commitment authority action succeeds, the decision record is marked `committed`, and an immutable event is written.
- Funding release is a separate authority action and execution record. Permission to operate funding processes does not confer authority to commit capital.

## Entity catalog

| Entity ID | Name | Class | Status | Identity rule | Versioning rule |
| --- | --- | --- | --- | --- | --- |
| ENT_DEAL | Deal Record | core_aggregate | canonical | deal_id is immutable and never reused; aliases and related transactions do not create duplicate identities. | State and status change only through append-only transition events; decision and outcome snapshots remain immutable. |
| ENT_COMPANY | Company | party | canonical | company_id remains stable through name changes; legal combinations create successor relationships. | Mutable descriptive fields retain history; observations and decisions are never rewritten. |
| ENT_ORGANIZATION | Organization | party | canonical | organization_id is stable across deals and name changes. | Descriptive attributes mutate with history; deal roles remain separate objects. |
| ENT_ACTOR | Actor | party | canonical | actor_id is stable and never reassigned. | Status may change; historical approvals retain the original actor identity. |
| ENT_ROLE_ASSIGNMENT | Role Assignment | governance | canonical | Each assignment has a unique identity and effective period. | Changes create a new assignment or close the existing period; history is immutable. |
| ENT_FUND_VEHICLE | Fund or Vehicle | economic | canonical | fund_vehicle_id is stable across legal-name changes and administrative migrations. | Legal amendments create versioned terms; historical capital events remain immutable. |
| ENT_INVESTMENT_EXPOSURE | Investment Exposure | economic | canonical | One stable identity per vehicle-security tranche relationship. | Current totals are calculated from immutable capital events; material economic changes create a successor exposure or security version. |
| ENT_POSITION_RECORD | Position Record | portfolio | canonical | Unique by exposure and as-of date; corrections create a successor version. | Final snapshots are immutable. |
| ENT_ACCESS_GRANT | Access Grant | governance | canonical | Each grant is immutable for its scope and effective period. | Changes create a new grant or revocation event. |
| ENT_PERMISSION_POLICY | Permission Policy | governance | configurable | Policy identity is stable across versions. | Changes create a new version and effective period. |
| ENT_AUTHORITY_RULE | Authority Rule | governance | configurable | Rule identity is stable; versions have effective periods. | Changes create a new version; approvals retain the version used. |
| ENT_APPROVAL_RECORD | Approval Record | governance | canonical | Each approval action has a unique immutable identity. | Revocation or supersession creates a linked record. |
| ENT_WORKSTREAM_DEFINITION | Workstream Definition | configuration | configurable | Identifier remains stable while versions evolve. | Changes create a new version; runs retain the instantiated version. |
| ENT_WORKSTREAM_RUN | Workstream Run | workflow_control | canonical | One identity per deal, definition version, and activation cycle. | Status changes through append-only run events; reopening preserves prior completion. |
| ENT_SOURCE_MATERIAL_SET | Source Material Set | knowledge | canonical | Identity represents one source-and-purpose collection. | Membership may evolve before indexing; finalized set versions remain auditable. |
| ENT_DOCUMENT_ARTIFACT | Document Artifact | knowledge | canonical | Logical identity persists across revisions; materially different purpose creates a new artifact. | File changes create DocumentVersion objects; logical status may mutate. |
| ENT_DOCUMENT_VERSION | Document Version | knowledge | canonical | Every content version has a unique immutable identity. | Immutable; changes create a successor version. |
| ENT_EVIDENCE_ITEM | Evidence Item | knowledge | canonical | Identity binds content, source version, and locator. | Immutable; corrections create successor evidence. |
| ENT_SCREENING_ASSESSMENT | Screening Assessment | analytical | canonical | One identity per screening cycle. | Draft may mutate; final assessment is immutable and reconsideration creates a successor. |
| ENT_QUESTION_REGISTER | Question Register | knowledge | canonical | Stable register identity with explicit versions and decision snapshots. | Active register mutates through events; each decision creates an immutable snapshot. |
| ENT_QUESTION | Question | knowledge | canonical | Identity persists through answer attempts; reframing creates a successor. | Status evolves through events; original text is preserved. |
| ENT_ASSUMPTION | Assumption | knowledge | canonical | Identity represents one proposition; substantive revision creates a successor. | Status evolves; statement changes create a successor rather than overwrite. |
| ENT_RISK | Risk | knowledge | canonical | Identity persists for the same causal risk; a materially different risk creates a new object. | Status evolves through events; causal changes create a successor. |
| ENT_METRIC_DEFINITION | Metric Definition | analytical | canonical | Identifier is stable per semantic definition. | Formula or scope changes create a new version; observations retain the version used. |
| ENT_METRIC_OBSERVATION | Metric Observation | analytical | canonical | Unique by metric definition, subject, period, basis, and source version. | Immutable; corrections create a superseding observation. |
| ENT_DILIGENCE_FINDING | Diligence Finding | knowledge | canonical | Identity represents one conclusion; substantive change creates a successor. | Status evolves; validated conclusion text is preserved. |
| ENT_INVESTMENT_THESIS | Investment Thesis | analytical | canonical | Identity persists for one causal thesis; material reframing creates a successor. | Versioned; decisions reference immutable thesis versions. |
| ENT_CHALLENGE_ASSESSMENT | Challenge Assessment | analytical | configurable | One identity per review cycle and thesis version. | Draft may mutate; final assessment is immutable and later challenge creates a successor. |
| ENT_ANALYTICAL_MODEL | Analytical Model | analytical | canonical | Identity represents one model purpose and logic lineage. | Logic changes create a new model version; decisions reference immutable model and case snapshots. |
| ENT_MODEL_CASE | Model Case | analytical | canonical | Every case version has a unique identity. | Immutable after review; changes create a successor case. |
| ENT_VALUATION_INPUT | Valuation Input | analytical | canonical | Identity binds type, value, as-of date, and source basis. | Immutable; updates create a successor input. |
| ENT_VALUATION_CASE | Valuation Case | analytical | canonical | Every decision-relevant valuation snapshot has a unique identity. | Immutable after review; changes create a successor. |
| ENT_ADJUSTMENT_ITEM | Adjustment Item | analytical | canonical | One identity per adjustment claim and basis. | Status evolves; material amount or rationale changes create a successor. |
| ENT_BRIDGE_ANALYSIS | Bridge Analysis | analytical | canonical | Unique by type, endpoints, and version. | Immutable after review; changes create a successor. |
| ENT_VALUE_CREATION_PLAN | Value Creation Plan | analytical | canonical | Stable identity per approved value-creation program. | Versioned; original decision-basis version remains immutable. |
| ENT_CAPITAL_STRUCTURE | Capital Structure | economic | canonical | Unique by deal and as-of snapshot. | Snapshots are immutable; changes create successors. |
| ENT_SECURITY | Security | economic | canonical | Stable identity for an instrument or tranche. | Terms are versioned; executed terms are immutable and amendments create successors. |
| ENT_SOURCES_USES | Sources and Uses | economic | canonical | Unique by deal and transaction scenario. | Immutable after agreement; changes create a successor. |
| ENT_MATERIALITY_ASSESSMENT | Materiality Assessment | workflow_control | canonical | Unique by subject, rule version, and evaluation time. | Immutable; reevaluation creates a new assessment. |
| ENT_GATE | Gate | workflow_control | canonical | Unique per deal, transition, and activation cycle. | Status evolves through append-only evaluations; definition changes create a new instance. |
| ENT_DECISION_RECORD | Decision Record | governance | canonical | Every decision event has a unique identity. | Draft may mutate; effective decisions are immutable and later changes create a successor. |
| ENT_RISK_ACCEPTANCE_RECORD | Risk Acceptance Record | governance | canonical | Unique per accepted object, scope, and decision cycle. | Immutable; changes create a successor or revocation. |
| ENT_EXCEPTION_RECORD | Exception Record | workflow_control | canonical | Unique for one deviation, scope, and period. | Immutable; changes create a successor or revocation. |
| ENT_EXECUTION_DOCUMENT_SET | Execution Document Set | execution | canonical | Stable identity per execution cycle. | Versioned during negotiation; signed-set snapshot is immutable. |
| ENT_LEGAL_AGREEMENT | Legal Agreement | execution | canonical | Stable identity for one agreement through amendments. | Executed versions are immutable; amendments create successors. |
| ENT_COVENANT | Covenant | execution | canonical | Stable identity for the covenant term; material amendment creates a successor. | Test results are immutable events; terms version through agreement amendments. |
| ENT_GOVERNANCE_RIGHT | Governance Right | execution | canonical | Stable identity under the source agreement. | Terms changes create successors through agreement amendment. |
| ENT_CLOSING_RECORD | Closing Record | execution | canonical | Unique per closing event; partial closings receive distinct records. | Immutable; corrections create linked correction records. |
| ENT_CAPITAL_EVENT | Capital Event | portfolio | canonical | Unique immutable event identity. | Immutable; reversal is a separate event. |
| ENT_MONITORING_RECORD | Monitoring Record | portfolio | canonical | Unique by deal, period, and version. | Final snapshot is immutable; revisions create successors. |
| ENT_REUNDERWRITING_TRIGGER | Re-underwriting Trigger | portfolio | canonical | Unique per causal event and detection cycle. | Immutable; later evidence creates a successor or status event. |
| ENT_REUNDERWRITING_RECORD | Re-underwriting Record | portfolio | canonical | One identity per review cycle; multiple triggers may feed one record. | Draft may mutate; approved snapshot is immutable and subsequent review creates a successor. |
| ENT_OUTCOME_RECORD | Outcome Record | portfolio | canonical | Each partial or final outcome event has a unique identity. | Final records are immutable; corrections create a revised successor. |
| ENT_SYNERGY_PLAN | Synergy Plan | archetype_extension | archetype_extension | Stable identity per synergy program. | Versioned; decision-basis version remains immutable. |
| ENT_INTEGRATION_PLAN | Integration Plan | archetype_extension | archetype_extension | Stable identity per integration program. | Versioned; milestone status events are append-only. |
| ENT_ADD_ON_PIPELINE | Add-on Pipeline | archetype_extension | archetype_extension | Stable identity per platform pipeline and planning cycle. | Versioned; target progression is event-driven. |
| ENT_PLATFORM_ADD_ON_LINK | Platform–Add-on Link | archetype_extension | archetype_extension | Stable identity for one platform-add-on relationship. | Status evolves through events; identity remains stable. |
| ENT_SEPARATION_PERIMETER | Separation Perimeter | archetype_extension | archetype_extension | Stable identity per carve-out transaction. | Versioned; agreed and final versions are immutable and amendments create successors. |
| ENT_TRANSITION_SERVICE_AGREEMENT | Transition Service Agreement | archetype_extension | archetype_extension | Stable identity through amendments. | Terms version through the linked agreement; service-performance events are append-only. |
| ENT_STANDALONE_COST_BASELINE | Standalone Cost Baseline | archetype_extension | archetype_extension | Stable identity per baseline cycle. | Versioned; decision-basis and actualized versions remain immutable. |
| ENT_FOUNDER_ROLLOVER | Founder Rollover | archetype_extension | archetype_extension | Stable identity per holder-security arrangement. | Executed terms are versioned; funding and realization are capital events. |
| ENT_AUCTION_PROCESS | Auction Process | archetype_extension | archetype_extension | Stable identity per sale process. | Round updates are events; process rules and deadlines are versioned. |
| ENT_VENDOR_DILIGENCE_PACKAGE | Vendor Diligence Package | archetype_extension | archetype_extension | Stable identity per adviser package and scope. | Updates create successor versions. |
| ENT_PUBLIC_MARKET_TRANSACTION | Public Market Transaction | archetype_extension | archetype_extension | Stable identity per public-market transaction. | Milestone events are append-only; terms are versioned. |
| ENT_SHAREHOLDER_APPROVAL | Shareholder Approval | archetype_extension | archetype_extension | Unique immutable approval event. | Immutable; corrections create a linked revision. |
| ENT_SPONSOR_TRACK_RECORD | Sponsor Track Record | archetype_extension | archetype_extension | Stable identity per organization, strategy scope, and version. | Versioned; source basis and effective period are preserved. |
| ENT_KEY_PERSON_DEPENDENCY | Key-Person Dependency | archetype_extension | archetype_extension | Stable identity per causal dependency. | Status evolves through events; causal change creates a successor. |
| ENT_WORKFLOW_EVENT | Workflow Event | immutable_event | canonical | workflow_event_id is immutable and never reused. | Immutable append-only record. |
| ENT_STALENESS_RECORD | Staleness Record | lineage_control | canonical | staleness_record_id is immutable and never reused. | Immutable record; resolution references a successor output. |
| ENT_CONDITION_RECORD | Condition Record | governance_control | canonical | condition_record_id is immutable and never reused. | Immutable condition definition; state changes are evented. |
| ENT_PERMISSION_EVALUATION_RECORD | Permission Evaluation Record | governance_control | canonical | permission_evaluation_id is immutable and never reused. | Immutable evaluation snapshot. |
| ENT_EVIDENCE_SUFFICIENCY_ASSESSMENT | Evidence Sufficiency Assessment | epistemic_control | canonical | sufficiency_assessment_id is immutable and never reused. | New assessment for each phase, question, or evidence-set version. |
| ENT_REASONING_RECORD | Reasoning Record | epistemic_record | canonical | reasoning_record_id is immutable and never reused. | Every analytical revision creates a successor; decision-used versions remain immutable. |
| ENT_ROLE_DEFINITION | Role Definition | governance_configuration | canonical | role_definition_id is immutable and never reused. | Versioned configuration; assignments reference a specific effective version. |
| ENT_DELEGATION_RECORD | Delegation Record | governance_record | canonical | delegation_record_id is immutable and never reused. | Immutable record; revocation creates an event and status transition. |
| ENT_RECUSAL_RECORD | Recusal Record | governance_record | canonical | recusal_record_id is immutable and never reused. | Immutable record; scope changes require a successor. |
| ENT_DISSENT_RECORD | Dissent Record | governance_record | canonical | dissent_record_id is immutable and never reused. | Immutable; later clarification creates a successor record. |

## Field catalog by entity


### ENT_DEAL — Deal Record

A persistent record for an investment opportunity or portfolio investment across screening, diligence, decisioning, execution, monitoring, re-underwriting, and outcome.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| deal_id | string | required | Stable unique identifier. | immutable |
| canonical_name | string | required | Current canonical label. | mutable with alias history |
| alias_names | structured object | optional | Former names, project names, and external aliases. | append-only alias entries |
| process_type | enum | required | Primary process form. | stored on current object |
| archetype | enum | optional | Primary deal archetype. | stored on current object |
| current_state | enum | required | Current workflow state identifier. | stored on current object |
| status | enum | required | Business status. | stored on current object |
| owner_role_assignment_id | reference | required | Accountable deal owner. | stored on current object |
| priority | enum | optional | Operating priority. | stored on current object |
| parent_deal_id | reference | optional | Parent transaction for follow-on, add-on, or continuation context. | stored on current object |
| current_outcome_record_id | reference | optional | Latest outcome record. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_COMPANY — Company

An operating business, asset, or legally distinct operating perimeter that is underwritten, monitored, or realized.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| company_id | string | required | Stable unique identifier. | immutable |
| legal_name | string | required | Current legal name. | stored on current object |
| aliases | structured object | optional | Former names, trade names, and project aliases. | append-only alias entries |
| business_description | text | optional | Description of the operating business. | stored on current object |
| sector | enum | optional | Sector classification. | stored on current object |
| geography | structured object | optional | Headquarters and operating geographies. | stored on current object |
| ownership_status | enum | optional | Ownership context. | stored on current object |
| status | enum | required | Company record status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ORGANIZATION — Organization

A legal or operating organization participating in the investment process, including sponsors, sellers, buyers, lenders, advisers, administrators, and regulators.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| organization_id | string | required | Stable unique identifier. | immutable |
| legal_name | string | required | Authoritative organization name. | stored on current object |
| organization_type | enum | required | Primary type. | stored on current object |
| jurisdiction | string | optional | Formation or operating jurisdiction. | stored on current object |
| status | enum | required | Organization status. | stored on current object |
| conflict_flags | structured object | optional | Potential conflicts. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ACTOR — Actor

A person, team, committee, or system principal capable of owning work, viewing objects, making recommendations, or exercising authority.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| actor_id | string | required | Stable unique identifier. | immutable |
| actor_type | enum | required | Principal type. | stored on current object |
| display_name | string | required | Display label. | stored on current object |
| organization_id | reference | optional | Affiliated organization. | stored on current object |
| status | enum | required | Actor status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ROLE_ASSIGNMENT — Role Assignment

A time-bounded assignment of a role to an actor or organization within a deal, entity, workstream, vehicle, agreement, or global scope.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| role_assignment_id | string | required | Stable assignment identifier. | immutable |
| actor_id | reference | optional | Assigned actor. | stored on current object |
| organization_id | reference | optional | Assigned organization. | stored on current object |
| role_type | enum | required | Role performed. | stored on current object |
| scope_type | enum | required | Assignment scope. | stored on current object |
| scope_id | reference | required | Object to which the assignment applies. | stored on current object |
| effective_from | datetime | required | Assignment start. | stored on current object |
| effective_to | datetime | optional | Assignment end. | stored on current object |
| status | enum | required | Assignment status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| role_definition_id | reference | required | Effective role definition used by this contextual assignment. | stored on current object |

### ENT_FUND_VEHICLE — Fund or Vehicle

A legal or accounting vehicle through which capital is committed, held, allocated, or administered.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| fund_vehicle_id | string | required | Stable vehicle identifier. | immutable |
| vehicle_type | enum | required | Vehicle type. | stored on current object |
| legal_name | string | required | Legal name. | stored on current object |
| jurisdiction | string | optional | Formation jurisdiction. | stored on current object |
| base_currency | string | required | Reporting currency. | stored on current object |
| status | enum | required | Vehicle status. | stored on current object |
| commitment_limit | money | optional | Applicable commitment limit. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_INVESTMENT_EXPOSURE — Investment Exposure

The economic relationship connecting a vehicle to a security or contractual investment position in a deal.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| investment_exposure_id | string | required | Stable exposure identifier. | immutable |
| deal_id | reference | required | Related deal. | stored on current object |
| fund_vehicle_id | reference | required | Holding vehicle. | stored on current object |
| security_id | reference | required | Security or instrument. | stored on current object |
| exposure_role | enum | required | Exposure role. | stored on current object |
| committed_amount | money | optional | Approved commitment. | stored on current object |
| funded_amount | money | optional | Cumulative funded amount. | stored on current object |
| cost_basis | money | optional | Current cost basis. | stored on current object |
| status | enum | required | Exposure status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_POSITION_RECORD — Position Record

An as-of snapshot of the accounting, ownership, valuation, liquidity, and return state of an investment exposure.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| position_record_id | string | required | Stable snapshot identifier. | immutable |
| investment_exposure_id | reference | required | Exposure summarized. | stored on current object |
| as_of_date | date | required | Snapshot date. | immutable |
| cost_basis | money | required | Cost basis. | stored on current object |
| fair_value | money | optional | Fair value. | stored on current object |
| unfunded_commitment | money | optional | Remaining commitment. | stored on current object |
| cumulative_proceeds | money | optional | Cumulative proceeds. | stored on current object |
| ownership_percentage | percentage | optional | Economic ownership. | stored on current object |
| moic | decimal | optional | Multiple of invested capital. | stored on current object |
| irr | percentage | optional | Internal rate of return. | stored on current object |
| status | enum | required | Snapshot status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ACCESS_GRANT — Access Grant

A time-bounded authorization to receive, store, review, or use defined information under specified confidentiality and use restrictions.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| access_grant_id | string | required | Stable grant identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| grantee_actor_or_role_id | reference | required | Authorized principal or role. | stored on current object |
| source_organization_id | reference | optional | Information provider. | stored on current object |
| permitted_use_scope | structured object | required | Permitted activities and restrictions. | stored on current object |
| confidentiality_class | enum | required | Classification. | stored on current object |
| effective_from | datetime | required | Grant start. | stored on current object |
| expires_at | datetime | optional | Grant expiry. | stored on current object |
| status | enum | required | Grant status. | stored on current object |
| legal_agreement_id | reference | optional | Agreement supporting the grant. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_PERMISSION_POLICY — Permission Policy

A configurable rule that allows or denies an action on an object based on actor, role, scope, classification, and context.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| permission_policy_id | string | required | Stable policy identifier. | immutable |
| object_type | enum | required | Governed entity type. | stored on current object |
| action | enum | required | Controlled action. | stored on current object |
| subject_role_types | structured object | required | Roles to which the rule applies. | stored on current object |
| condition_expression | text | optional | Executable condition. | stored on current object |
| effect | enum | required | Policy effect. | stored on current object |
| priority | integer | required | Conflict-resolution priority. | stored on current object |
| status | enum | required | Policy status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| allowed_actions | structured object | required | Actions governed by the policy. | stored on current object |
| effect_rules | structured object | required | Allow, deny, conditional, or approval-required outcomes. | stored on current object |
| confidentiality_condition | structured object | optional | Sensitivity conditions. | stored on current object |
| ownership_condition | structured object | optional | Ownership conditions. | stored on current object |
| relationship_condition | structured object | optional | Contextual relationship conditions. | stored on current object |
| materiality_condition | structured object | optional | Materiality conditions. | stored on current object |
| inheritance_rule | structured object | required | Policy inheritance. | stored on current object |
| delegation_rule | structured object | required | Delegated permission constraints. | stored on current object |
| expiry_rule | structured object | required | Expiry behavior. | stored on current object |
| audit_requirement | structured object | required | Evaluation and event requirements. | stored on current object |

### ENT_AUTHORITY_RULE — Authority Rule

A configurable rule specifying who may approve, waive, accept risk, override a blocker, commit capital, or authorize an outcome.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| authority_rule_id | string | required | Stable rule identifier. | immutable |
| action_type | enum | required | Governed action. | stored on current object |
| scope_expression | text | required | Applicable objects and contexts. | stored on current object |
| threshold_rule | structured object | optional | Configurable threshold. | stored on current object |
| required_role_types | structured object | required | Approver roles and quorum. | stored on current object |
| override_role_types | structured object | optional | Permitted override roles. | stored on current object |
| status | enum | required | Rule status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| authority_action_ids | reference array | required | Actions governed by this rule. | stored on current object |
| approval_structure | structured object | required | Single or collective approval structure. | stored on current object |
| quorum_rule | structured object | optional | Quorum requirement. | stored on current object |
| delegation_rule | structured object | required | Delegability and scope. | stored on current object |
| non_delegable_actions | structured object | optional | Actions that cannot be delegated. | stored on current object |
| conflict_rule | structured object | required | Conflict and recusal requirement. | stored on current object |
| segregation_rule | structured object | required | Segregation-of-duties requirement. | stored on current object |
| effective_from | datetime | required | Rule start. | stored on current object |
| effective_to | datetime | optional | Rule end. | stored on current object |

### ENT_APPROVAL_RECORD — Approval Record

An immutable record of an authority decision applied to a decision, gate, exception, risk acceptance, commitment, or outcome.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| approval_record_id | string | required | Stable approval identifier. | immutable |
| authority_rule_id | reference | required | Rule used. | stored on current object |
| subject_type | enum | required | Type of approved object. | stored on current object |
| subject_id | reference | required | Approved object. | stored on current object |
| approver_role_assignment_ids | reference array | required | Approving roles. | stored on current object |
| decision | enum | required | Outcome. | stored on current object |
| conditions | structured object | optional | Attached conditions. | stored on current object |
| effective_at | datetime | required | Effective time. | stored on current object |
| status | enum | required | Record status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| authority_action_id | reference | required | Authority action contract exercised. | immutable |
| authority_rule_version | string | required | Effective authority-rule version. | immutable |
| quorum_snapshot | structured object | optional | Collective approval and quorum snapshot. | immutable |
| permission_evaluation_ids | reference array | required | Permission evaluations supporting the action. | immutable |
| decision_basis_snapshot | structured object | required | Immutable snapshot of the analytical and evidentiary basis. | immutable |
| condition_record_ids | reference array | optional | Conditions attached to the approval. | immutable |
| recusal_record_ids | reference array | optional | Recusals applied. | immutable |
| dissent_record_ids | reference array | optional | Dissent attached to the action. | immutable |
| expires_at | datetime | optional | Approval lapse timestamp. | immutable |
| supersedes_approval_record_id | reference | optional | Prior authority record superseded. | immutable |
| idempotency_key | string | required | Unique authority-action execution key. | immutable |

### ENT_WORKSTREAM_DEFINITION — Workstream Definition

A configurable definition of a recurring analytical, control, execution, or portfolio workstream, including typed inputs, outputs, dependencies, and completion criteria.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| workstream_definition_id | string | required | Stable identifier matching a workflow graph node. | immutable |
| name | string | required | Workstream name. | stored on current object |
| node_type | enum | required | Workstream class. | stored on current object |
| typed_inputs | structured object | required | Input object contracts. | stored on current object |
| typed_outputs | structured object | required | Output object contracts. | stored on current object |
| start_condition | text | required | Executable activation condition. | stored on current object |
| done_condition | text | required | Executable completion condition. | stored on current object |
| applicable_archetypes | structured object | optional | Default applicability by archetype. | stored on current object |
| status | enum | required | Definition status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_WORKSTREAM_RUN — Workstream Run

A deal-specific execution instance of a workstream definition with owners, inputs, outputs, blockers, and status.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| workstream_run_id | string | required | Stable run identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| workstream_definition_id | reference | required | Instantiated definition. | stored on current object |
| owner_role_assignment_id | reference | required | Accountable owner. | stored on current object |
| status | enum | required | Run status. | stored on current object |
| input_object_refs | reference array | optional | Input objects consumed. | stored on current object |
| output_object_refs | reference array | optional | Output objects produced. | stored on current object |
| blocking_dependency_refs | reference array | optional | Unresolved blockers. | stored on current object |
| started_at | datetime | optional | Start time. | stored on current object |
| completed_at | datetime | optional | Completion time. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SOURCE_MATERIAL_SET — Source Material Set

A provenance-scoped collection of source documents or public materials received or assembled for a deal.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| source_material_set_id | string | required | Stable set identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| source_organization_id | reference | optional | Primary source organization. | stored on current object |
| set_type | enum | required | Material-set type. | stored on current object |
| access_grant_id | reference | optional | Access authorization. | stored on current object |
| index_status | enum | required | Index status. | stored on current object |
| provenance_quality | enum | required | Source quality. | stored on current object |
| document_artifact_ids | reference array | optional | Included documents. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_DOCUMENT_ARTIFACT — Document Artifact

A stable logical document identity that may have one or more immutable versions and may represent, support, or record domain objects.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| document_artifact_id | string | required | Stable logical document identifier. | immutable |
| deal_id | reference | optional | Deal scope. | stored on current object |
| document_type | enum | required | Type from the document taxonomy. | stored on current object |
| source_organization_id | reference | optional | Producing organization. | stored on current object |
| source_role | enum | optional | Producer role. | stored on current object |
| confidentiality_class | enum | required | Classification. | stored on current object |
| current_version_id | reference | optional | Current version. | stored on current object |
| status | enum | required | Logical status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_DOCUMENT_VERSION — Document Version

An immutable content version of a document artifact with content date, hash, locator, and supersession relationship.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| document_version_id | string | required | Stable version identifier. | immutable |
| document_artifact_id | reference | required | Logical document. | stored on current object |
| version_label | string | optional | Human-readable version label. | stored on current object |
| content_date | date | optional | Date to which content refers. | stored on current object |
| content_hash | string | required | Cryptographic content hash. | immutable |
| storage_locator | string | required | Controlled storage locator. | stored on current object |
| supersedes_version_id | reference | optional | Prior version. | stored on current object |
| version_status | enum | required | Version status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_EVIDENCE_ITEM — Evidence Item

A bounded fact, observation, assertion, calculation, or excerpt with explicit provenance that can support, challenge, or contextualize a claim.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| evidence_item_id | string | required | Stable evidence identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| document_version_id | reference | optional | Source document version. | stored on current object |
| evidence_type | enum | required | Evidence type. | stored on current object |
| content_or_locator | text | required | Evidence content or precise locator. | stored on current object |
| as_of_date | date | optional | Effective date. | stored on current object |
| reliability | enum | required | Reliability. | stored on current object |
| status | enum | required | Evidence status. | stored on current object |
| materiality_level | enum | optional | Materiality. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SCREENING_ASSESSMENT — Screening Assessment

A preliminary assessment of fit, investability, known risks, information sufficiency, and whether an opportunity should consume diligence resources.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| screening_assessment_id | string | required | Stable assessment identifier. | immutable |
| deal_id | reference | required | Deal assessed. | stored on current object |
| fit_assessment | structured object | required | Strategy, vehicle, size, and portfolio fit. | stored on current object |
| preliminary_economics | structured object | optional | Indicative economics. | stored on current object |
| initial_thesis_id | reference | optional | Preliminary thesis. | stored on current object |
| initial_risk_ids | reference array | optional | Known risks. | stored on current object |
| decision | enum | required | Screening result. | stored on current object |
| rationale | text | required | Reason for the result. | stored on current object |
| status | enum | required | Assessment status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_QUESTION_REGISTER — Question Register

A versioned collection of diligence questions, ownership, criticality, evidence needs, resolution state, and decision impact.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| question_register_id | string | required | Stable register identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| version_number | integer | required | Register version. | stored on current object |
| question_ids | reference array | required | Questions in the register. | stored on current object |
| critical_open_count | integer | required | Unresolved critical questions. | stored on current object |
| status | enum | required | Register status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_QUESTION — Question

A testable uncertainty that requires evidence, analysis, risk acceptance, or explicit non-resolution before a decision.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| question_id | string | required | Stable question identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| question_text | text | required | Current formulation. | stored on current object |
| category | enum | required | Category. | stored on current object |
| criticality | enum | required | Decision criticality. | stored on current object |
| owner_workstream_run_id | reference | optional | Responsible workstream. | stored on current object |
| evidence_needed | text | optional | Evidence required. | stored on current object |
| status | enum | required | Resolution status. | stored on current object |
| resolution_summary | text | optional | Resolution or reason for non-resolution. | stored on current object |
| successor_question_id | reference | optional | Reframed successor. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ASSUMPTION — Assumption

A proposition about market, operations, economics, structure, execution, or outcome that is used in reasoning and may be supported, challenged, broken, or superseded.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| assumption_id | string | required | Stable assumption identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| category | enum | required | Assumption category. | stored on current object |
| statement | text | required | Testable proposition. | stored on current object |
| owner_role_assignment_id | reference | optional | Accountable owner. | stored on current object |
| status | enum | required | Assumption status. | stored on current object |
| confidence | enum | required | Current confidence. | stored on current object |
| model_impact | structured object | optional | Cases or outputs affected. | stored on current object |
| successor_assumption_id | reference | optional | Successor when revised. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_RISK — Risk

A potential adverse condition or event with likelihood, impact, mitigation, ownership, and decision consequences.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| risk_id | string | required | Stable risk identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| category | enum | required | Risk category. | stored on current object |
| description | text | required | Risk statement. | stored on current object |
| likelihood | enum | optional | Likelihood. | stored on current object |
| impact | enum | required | Impact. | stored on current object |
| owner_role_assignment_id | reference | optional | Risk owner. | stored on current object |
| mitigation_plan | text | optional | Mitigation or monitoring plan. | stored on current object |
| status | enum | required | Risk status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_METRIC_DEFINITION — Metric Definition

A versioned definition of a quantitative or categorical measure, including unit, formula, scope, aggregation, and source rules.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| metric_definition_id | string | required | Stable definition identifier. | immutable |
| name | string | required | Metric name. | stored on current object |
| metric_type | enum | required | Metric class. | stored on current object |
| unit | string | required | Unit of measure. | stored on current object |
| formula | text | optional | Calculation formula. | stored on current object |
| scope_rule | text | required | Included and excluded items. | stored on current object |
| aggregation_rule | text | optional | Aggregation method. | stored on current object |
| status | enum | required | Definition status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_METRIC_OBSERVATION — Metric Observation

An immutable measured, normalized, budgeted, forecast, or target value for a metric, subject, period, and basis.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| metric_observation_id | string | required | Stable observation identifier. | immutable |
| metric_definition_id | reference | required | Metric definition. | stored on current object |
| subject_type | enum | required | Measured subject. | stored on current object |
| subject_id | reference | required | Measured object. | stored on current object |
| period_start | date | optional | Period start. | stored on current object |
| period_end | date | required | Period end or as-of date. | stored on current object |
| basis | enum | required | Observation basis. | stored on current object |
| value | structured object | required | Typed value. | stored on current object |
| status | enum | required | Observation status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_DILIGENCE_FINDING — Diligence Finding

A workstream conclusion that synthesizes evidence into a validated, disputed, or unresolved finding with decision impact.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| diligence_finding_id | string | required | Stable finding identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| workstream_run_id | reference | required | Producing run. | stored on current object |
| finding_type | enum | required | Finding type. | stored on current object |
| summary | text | required | Finding conclusion. | stored on current object |
| severity | enum | required | Severity. | stored on current object |
| status | enum | required | Finding status. | stored on current object |
| decision_impact | enum | optional | Expected consequence. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_INVESTMENT_THESIS — Investment Thesis

A versioned set of causal claims explaining why an investment should create or preserve value, what must be true, and what could invalidate the case.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| investment_thesis_id | string | required | Stable thesis identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| thesis_source | enum | required | Thesis origin. | stored on current object |
| thesis_statement | text | required | Core causal thesis. | stored on current object |
| value_driver_assumption_ids | reference array | required | Value-driving assumptions. | stored on current object |
| risk_ids | reference array | optional | Risks that could invalidate the thesis. | stored on current object |
| status | enum | required | Thesis status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_CHALLENGE_ASSESSMENT — Challenge Assessment

A structured adversarial review that identifies the propositions required for an investment to work, assembles counterevidence, and states whether residual risk is acceptable.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| challenge_assessment_id | string | required | Stable assessment identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| thesis_id | reference | required | Thesis challenged. | stored on current object |
| challenged_assumption_ids | reference array | required | Assumptions tested. | stored on current object |
| counterevidence_item_ids | reference array | optional | Counterevidence considered. | stored on current object |
| conclusion | enum | required | Assessment conclusion. | stored on current object |
| status | enum | required | Assessment status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ANALYTICAL_MODEL — Analytical Model

A versioned computational model that transforms assumptions, observations, capital structure, and transaction terms into operating, cash-flow, valuation, or return outputs.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| analytical_model_id | string | required | Stable model identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| model_type | enum | required | Model type. | stored on current object |
| owner_role_assignment_id | reference | required | Model owner. | stored on current object |
| model_logic_version | string | required | Version of model logic. | stored on current object |
| status | enum | required | Model status. | stored on current object |
| storage_document_artifact_id | reference | optional | Representing document. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_MODEL_CASE — Model Case

A versioned scenario instance of an analytical model defined by a coherent set of assumptions and outputs.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| model_case_id | string | required | Stable case-version identifier. | immutable |
| analytical_model_id | reference | required | Parent model. | stored on current object |
| case_type | enum | required | Scenario type. | stored on current object |
| assumption_ids | reference array | required | Assumptions used. | stored on current object |
| output_metric_observation_ids | reference array | required | Produced outputs. | stored on current object |
| effective_date | date | required | Case as-of date. | stored on current object |
| status | enum | required | Case status. | stored on current object |
| supersedes_model_case_id | reference | optional | Prior case version. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_VALUATION_INPUT — Valuation Input

A typed and provenance-linked input used to derive enterprise value, equity value, security value, or expected returns.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| valuation_input_id | string | required | Stable input identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| input_type | enum | required | Input type. | stored on current object |
| value | structured object | required | Typed input value. | stored on current object |
| as_of_date | date | required | Effective date. | stored on current object |
| verification_status | enum | required | Verification state. | stored on current object |
| materiality_level | enum | required | Decision materiality. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_VALUATION_CASE — Valuation Case

A versioned valuation and return conclusion produced from specified model cases, valuation inputs, security terms, and methods.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| valuation_case_id | string | required | Stable valuation-version identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| model_case_ids | reference array | required | Model cases used. | stored on current object |
| valuation_input_ids | reference array | required | Inputs used. | stored on current object |
| methodologies | structured object | required | Valuation methods and weights. | stored on current object |
| enterprise_value | money | optional | Implied enterprise value. | stored on current object |
| equity_value | money | optional | Implied equity value. | stored on current object |
| return_outputs | structured object | optional | Return metrics and sensitivities. | stored on current object |
| status | enum | required | Valuation status. | stored on current object |
| supersedes_valuation_case_id | reference | optional | Prior valuation version. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ADJUSTMENT_ITEM — Adjustment Item

A proposed or accepted adjustment to a reported metric, debt item, working-capital item, or valuation basis with amount, rationale, evidence, and status.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| adjustment_item_id | string | required | Stable adjustment identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| adjustment_type | enum | required | Adjustment type. | stored on current object |
| amount | money | optional | Adjustment amount. | stored on current object |
| rationale | text | required | Adjustment rationale. | stored on current object |
| status | enum | required | Adjustment status. | stored on current object |
| affected_metric_definition_id | reference | optional | Affected metric. | stored on current object |
| affected_valuation_input_id | reference | optional | Affected valuation input. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_BRIDGE_ANALYSIS — Bridge Analysis

A versioned decomposition of change between two states into defined drivers, such as revenue, margin, earnings, cash flow, value creation, or actual-versus-plan variance.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| bridge_analysis_id | string | required | Stable bridge identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| bridge_type | enum | required | Bridge type. | stored on current object |
| start_basis | structured object | required | Starting state. | stored on current object |
| end_basis | structured object | required | Ending state. | stored on current object |
| components | structured object | required | Attributed drivers. | stored on current object |
| status | enum | required | Bridge status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_VALUE_CREATION_PLAN — Value Creation Plan

A versioned plan linking value drivers to assumptions, initiatives, owners, milestones, metrics, costs, timing, and expected economic impact.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| value_creation_plan_id | string | required | Stable plan identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| initiative_set | structured object | required | Value-creation initiatives. | stored on current object |
| assumption_ids | reference array | required | Supporting assumptions. | stored on current object |
| metric_definition_ids | reference array | optional | Tracking metrics. | stored on current object |
| owner_role_assignment_ids | reference array | optional | Initiative owners. | stored on current object |
| milestones | structured object | optional | Planned milestones. | stored on current object |
| expected_value_impact | structured object | optional | Expected impact by driver. | stored on current object |
| status | enum | required | Plan status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_CAPITAL_STRUCTURE — Capital Structure

An as-of snapshot of securities, debt, cash, ownership, seniority, dilution, and fully diluted economics.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| capital_structure_id | string | required | Stable snapshot identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| as_of_date | date | required | Effective date. | stored on current object |
| security_ids | reference array | required | Securities in the structure. | stored on current object |
| cash | money | optional | Cash balance. | stored on current object |
| net_debt | money | optional | Net debt. | stored on current object |
| ownership_table | structured object | optional | Ownership by holder and basis. | stored on current object |
| fully_diluted_basis | structured object | optional | Fully diluted assumptions. | stored on current object |
| status | enum | required | Snapshot status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SECURITY — Security

A legal and economic instrument defining cash-flow rights, priority, conversion, participation, governance, transfer, and downside protection.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| security_id | string | required | Stable instrument identifier. | immutable |
| issuer_company_or_vehicle_id | reference | required | Issuer. | stored on current object |
| security_type | enum | required | Instrument type. | stored on current object |
| currency | string | required | Denomination currency. | stored on current object |
| seniority_rank | integer | optional | Priority rank. | stored on current object |
| economic_terms | structured object | required | Coupon, dividend, conversion, participation, redemption, and return terms. | stored on current object |
| governance_right_ids | reference array | optional | Associated governance rights. | stored on current object |
| status | enum | required | Security status. | stored on current object |
| current_terms_version | integer | required | Current terms version. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SOURCES_USES — Sources and Uses

A versioned funding schedule balancing financing sources against purchase price, fees, refinancing, cash to balance sheet, and other uses.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| sources_uses_id | string | required | Stable schedule identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| as_of_date | date | required | Effective date. | stored on current object |
| source_lines | structured object | required | Funding sources. | stored on current object |
| use_lines | structured object | required | Transaction uses. | stored on current object |
| total_sources | money | required | Total sources. | stored on current object |
| total_uses | money | required | Total uses. | stored on current object |
| balance_difference | money | required | Difference between sources and uses. | stored on current object |
| status | enum | required | Schedule status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_MATERIALITY_ASSESSMENT — Materiality Assessment

An executable evaluation of whether a fact, variance, risk, question, finding, term, or event should inform, warn, block, trigger, reopen, or permit continuation.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| materiality_assessment_id | string | required | Stable assessment identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| subject_type | enum | required | Type of assessed object. | stored on current object |
| subject_id | reference | required | Assessed object. | stored on current object |
| rule_source | enum | required | Rule source. | stored on current object |
| threshold_or_condition | structured object | required | Executable threshold or condition. | stored on current object |
| result | enum | required | Workflow consequence. | stored on current object |
| rationale | text | required | Reason for result. | stored on current object |
| override_exception_record_id | reference | optional | Approved override. | stored on current object |
| status | enum | required | Assessment status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_GATE — Gate

A deal-specific control point determining whether a workflow transition may occur based on conditions, approvals, materiality results, and exceptions.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| gate_id | string | required | Stable gate identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| transition_id | string | required | Controlled state transition. | stored on current object |
| required_condition_set | structured object | required | Executable conditions. | stored on current object |
| authority_rule_id | reference | optional | Applicable authority rule. | stored on current object |
| blocking_object_refs | reference array | optional | Current blockers. | stored on current object |
| approval_record_ids | reference array | optional | Approvals. | stored on current object |
| exception_record_ids | reference array | optional | Approved exceptions. | stored on current object |
| status | enum | required | Gate status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| authority_action_id | reference | optional | Authority action needed to satisfy or waive the gate. | stored on current object |
| required_governance_record_types | structured object | required | Required approval, acceptance, exception, or condition records. | stored on current object |
| permission_evaluation_ids | reference array | required | Permission evaluations for the requested transition. | stored on current object |
| condition_record_ids | reference array | optional | Conditions attached to the gate. | stored on current object |

### ENT_DECISION_RECORD — Decision Record

An immutable decision snapshot recording the question decided, recommendation, alternatives, supporting and opposing evidence, assumptions, risks, conditions, and authority outcome.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| decision_record_id | string | required | Stable decision identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| decision_type | enum | required | Decision type. | stored on current object |
| decision_date | datetime | required | Decision time. | stored on current object |
| recommendation | enum | optional | Submitted recommendation. | stored on current object |
| decision | enum | required | Authority outcome. | stored on current object |
| supporting_object_refs | reference array | required | Evidence, models, valuations, and findings supporting the decision. | stored on current object |
| opposing_object_refs | reference array | optional | Contrary evidence and risks. | stored on current object |
| condition_set | structured object | optional | Conditions of approval or action. | stored on current object |
| approval_record_ids | reference array | required | Authority records. | stored on current object |
| status | enum | required | Decision status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| approved_model_case_ids | reference array | optional | Model cases approved as decision basis. | immutable |
| approved_valuation_case_ids | reference array | optional | Valuation cases approved as decision basis. | immutable |
| approved_assumption_version_ids | reference array | optional | Assumption versions used. | immutable |
| approved_risk_ids | reference array | optional | Risks considered. | immutable |
| decision_basis_snapshot | structured object | required | Immutable decision basis. | immutable |
| supersedes_decision_record_id | reference | optional | Prior decision superseded. | immutable |
| commitment_status | enum | optional | Whether an approval has become a binding commitment. | immutable |
| committed_at | datetime | optional | Commitment timestamp. | immutable |

### ENT_RISK_ACCEPTANCE_RECORD — Risk Acceptance Record

An immutable authority-backed acceptance of a defined residual risk or unresolved question for a stated scope, duration, and consequence.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| risk_acceptance_record_id | string | required | Stable record identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| risk_id | reference | optional | Accepted risk. | stored on current object |
| question_id | reference | optional | Accepted unresolved question. | stored on current object |
| scope | text | required | Acceptance scope. | stored on current object |
| rationale | text | required | Acceptance rationale. | stored on current object |
| accepted_by_approval_record_id | reference | required | Authority record. | stored on current object |
| review_or_expiry_date | date | optional | Review or expiry. | stored on current object |
| status | enum | required | Acceptance status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |
| authority_rule_version | string | required | Effective authority rule. | immutable |
| decision_basis_snapshot | structured object | required | Evidence and reasoning basis. | immutable |
| condition_record_ids | reference array | optional | Conditions of acceptance. | immutable |
| residual_risk_statement | text | required | Risk remaining after acceptance. | immutable |
| expires_at | datetime | optional | Acceptance lapse. | immutable |
| supersedes_risk_acceptance_record_id | reference | optional | Prior acceptance superseded. | immutable |

### ENT_EXCEPTION_RECORD — Exception Record

An immutable, time-bounded authorization to deviate from a workflow rule, dependency, gate, policy, or required artifact, with stated scope and consequence.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| exception_record_id | string | required | Stable exception identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| exception_type | enum | required | Exception type. | stored on current object |
| subject_ref | reference | required | Rule or object excepted. | stored on current object |
| reason | text | required | Exception reason. | stored on current object |
| effect | enum | required | Exception effect. | stored on current object |
| approval_record_id | reference | required | Approving authority. | stored on current object |
| expires_at | datetime | optional | Expiry. | stored on current object |
| status | enum | required | Exception status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_EXECUTION_DOCUMENT_SET — Execution Document Set

A versioned set of transaction, financing, vehicle, governance, and closing documents required to sign and close a deal or follow-on action.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| execution_document_set_id | string | required | Stable set identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| document_artifact_ids | reference array | required | Documents in the set. | stored on current object |
| legal_agreement_ids | reference array | optional | Agreements represented. | stored on current object |
| required_document_types | structured object | required | Required document types and applicability. | stored on current object |
| conditions_tracker | structured object | optional | Conditions precedent. | stored on current object |
| economic_consistency_status | enum | required | Consistency with approved economics. | stored on current object |
| status | enum | required | Set status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_LEGAL_AGREEMENT — Legal Agreement

A legally operative agreement with parties, effective dates, rights, obligations, conditions, remedies, amendments, and termination status.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| legal_agreement_id | string | required | Stable agreement identifier. | immutable |
| deal_id | reference | optional | Deal scope. | stored on current object |
| agreement_type | enum | required | Agreement type. | stored on current object |
| party_organization_ids | reference array | required | Agreement parties. | stored on current object |
| effective_date | date | optional | Effective date. | stored on current object |
| rights_and_obligations | structured object | required | Structured rights and obligations. | stored on current object |
| governing_law | string | optional | Governing law. | stored on current object |
| status | enum | required | Agreement status. | stored on current object |
| current_executed_version_id | reference | optional | Executed document version. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_COVENANT — Covenant

A contractual financial, operating, reporting, or negative obligation with a test rule, frequency, cure mechanics, and compliance status.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| covenant_id | string | required | Stable covenant identifier. | immutable |
| legal_agreement_id | reference | required | Governing agreement. | stored on current object |
| covenant_type | enum | required | Covenant type. | stored on current object |
| test_expression | text | required | Executable test expression. | stored on current object |
| test_frequency | duration | optional | Testing frequency. | stored on current object |
| threshold_rule | structured object | required | Threshold and basis. | stored on current object |
| cure_terms | structured object | optional | Cure rights and timing. | stored on current object |
| status | enum | required | Compliance status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_GOVERNANCE_RIGHT — Governance Right

A contractual right to information, observation, board participation, consent, veto, transfer, liquidity, or protective action.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| governance_right_id | string | required | Stable right identifier. | immutable |
| legal_agreement_id | reference | required | Source agreement. | stored on current object |
| holder_organization_or_vehicle_id | reference | required | Right holder. | stored on current object |
| right_type | enum | required | Right type. | stored on current object |
| scope | text | required | Right scope. | stored on current object |
| exercise_conditions | structured object | optional | Exercise conditions. | stored on current object |
| status | enum | required | Right status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_CLOSING_RECORD — Closing Record

An immutable record that conditions were satisfied or waived, funds moved, documents became effective, and securities or interests were issued or transferred.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| closing_record_id | string | required | Stable closing identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| scheduled_date | date | optional | Scheduled date. | stored on current object |
| effective_datetime | datetime | optional | Actual effective time. | stored on current object |
| execution_document_set_id | reference | required | Signed document set. | stored on current object |
| conditions_status | structured object | required | Conditions satisfied or waived. | stored on current object |
| funds_flow | structured object | optional | Confirmed funds flow. | stored on current object |
| issued_security_ids | reference array | optional | Securities issued or transferred. | stored on current object |
| created_exposure_ids | reference array | optional | Exposures created. | stored on current object |
| status | enum | required | Closing status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_CAPITAL_EVENT — Capital Event

An immutable event changing committed, funded, distributed, redeemed, impaired, or written-off value for an investment exposure.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| capital_event_id | string | required | Stable event identifier. | immutable |
| investment_exposure_id | reference | required | Affected exposure. | stored on current object |
| event_type | enum | required | Event type. | stored on current object |
| event_date | date | required | Effective date. | stored on current object |
| amount | money | required | Event amount. | stored on current object |
| currency | string | required | Currency. | stored on current object |
| status | enum | required | Event status. | stored on current object |
| related_decision_record_id | reference | optional | Authority decision if required. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_MONITORING_RECORD — Monitoring Record

A period-specific snapshot of performance, valuation, capital structure, risks, governance events, and variance against the approved underwriting baseline.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| monitoring_record_id | string | required | Stable monitoring identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| period_end | date | required | Reporting period end. | stored on current object |
| metric_observation_ids | reference array | required | Performance and valuation observations. | stored on current object |
| baseline_model_case_id | reference | optional | Underwriting baseline. | stored on current object |
| variance_summary | structured object | optional | Actual-versus-baseline variance. | stored on current object |
| risk_ids | reference array | optional | Current risks. | stored on current object |
| governance_event_refs | reference array | optional | Material governance events. | stored on current object |
| action_flags | structured object | optional | Required actions or triggers. | stored on current object |
| status | enum | required | Record status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_REUNDERWRITING_TRIGGER — Re-underwriting Trigger

A validated event or condition requiring the investment case, security economics, risk, hold period, or outcome options to be reassessed.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| reunderwriting_trigger_id | string | required | Stable trigger identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| trigger_type | enum | required | Trigger type. | stored on current object |
| detected_at | datetime | required | Detection time. | stored on current object |
| severity | enum | required | Severity. | stored on current object |
| source_object_refs | reference array | required | Supporting objects. | stored on current object |
| status | enum | required | Trigger status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_REUNDERWRITING_RECORD — Re-underwriting Record

An immutable analysis snapshot comparing current evidence and revised cases against the original decision basis and evaluating hold, follow-on, rescue, restructure, sell, impair, or no-action alternatives.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| reunderwriting_record_id | string | required | Stable record identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| trigger_ids | reference array | required | Initiating triggers. | stored on current object |
| original_model_case_id | reference | required | Original underwriting baseline. | stored on current object |
| current_metric_observation_ids | reference array | required | Current actuals and marks. | stored on current object |
| revised_model_case_ids | reference array | optional | Revised scenarios. | stored on current object |
| option_analysis | structured object | required | Hold, follow-on, rescue, restructure, sell, impairment, and no-action alternatives. | stored on current object |
| old_money_new_money_analysis | structured object | optional | Separate analysis for existing and incremental exposure. | stored on current object |
| recommendation | enum | required | Recommended action. | stored on current object |
| decision_record_id | reference | optional | Resulting decision. | stored on current object |
| status | enum | required | Record status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_OUTCOME_RECORD — Outcome Record

An immutable record of a realized, partial, continuing, restructured, impaired, written-off, or terminated investment outcome and its economic and decision basis.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| outcome_record_id | string | required | Stable outcome identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| investment_exposure_ids | reference array | optional | Affected exposures. | stored on current object |
| outcome_type | enum | required | Outcome type. | stored on current object |
| effective_date | date | required | Outcome date. | stored on current object |
| economic_result | structured object | optional | Proceeds, value, returns, loss, or residual exposure. | stored on current object |
| decision_record_id | reference | optional | Authorizing decision. | stored on current object |
| residual_exposure_status | enum | optional | Residual status. | stored on current object |
| status | enum | required | Outcome status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SYNERGY_PLAN — Synergy Plan

A versioned plan specifying revenue or cost synergies, timing, ownership, implementation cost, dependencies, and realization evidence.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| synergy_plan_id | string | required | Stable plan identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| synergy_items | structured object | required | Synergy initiatives and values. | stored on current object |
| timing_profile | structured object | required | Timing of realization. | stored on current object |
| implementation_cost | money | optional | Implementation cost. | stored on current object |
| owner_role_assignment_ids | reference array | optional | Owners. | stored on current object |
| status | enum | required | Plan status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_INTEGRATION_PLAN — Integration Plan

A versioned plan for combining operations, systems, people, customers, governance, and reporting after a platform or add-on transaction.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| integration_plan_id | string | required | Stable plan identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| scope | structured object | required | Functions and entities included. | stored on current object |
| milestones | structured object | required | Milestones, owners, dates, and status. | stored on current object |
| dependency_map | structured object | optional | Operational dependencies. | stored on current object |
| risk_ids | reference array | optional | Integration risks. | stored on current object |
| status | enum | required | Plan status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_ADD_ON_PIPELINE — Add-on Pipeline

A versioned portfolio of prospective acquisition targets with stage, strategic fit, indicative economics, probability, timing, and dependency on financing or integration capacity.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| add_on_pipeline_id | string | required | Stable pipeline identifier. | immutable |
| deal_id | reference | required | Platform deal scope. | stored on current object |
| target_entries | structured object | required | Prospective targets and stages. | stored on current object |
| integration_capacity_assessment | structured object | optional | Capacity constraints. | stored on current object |
| financing_dependency | structured object | optional | Funding requirements. | stored on current object |
| status | enum | required | Pipeline status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_PLATFORM_ADD_ON_LINK — Platform–Add-on Link

A persistent relationship identifying a platform company, an add-on company, acquisition deal, integration status, and intended value-creation logic.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| platform_add_on_link_id | string | required | Stable link identifier. | immutable |
| platform_company_id | reference | required | Platform company. | stored on current object |
| add_on_company_id | reference | required | Add-on company. | stored on current object |
| acquisition_deal_id | reference | required | Acquisition deal. | stored on current object |
| effective_date | date | optional | Acquisition date. | stored on current object |
| integration_plan_id | reference | optional | Integration plan. | stored on current object |
| status | enum | required | Link status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SEPARATION_PERIMETER — Separation Perimeter

A versioned definition of assets, liabilities, employees, contracts, systems, data, permits, and shared services included or excluded from a carve-out.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| separation_perimeter_id | string | required | Stable perimeter identifier. | immutable |
| deal_id | reference | required | Carve-out deal scope. | stored on current object |
| included_items | structured object | required | Included items. | stored on current object |
| excluded_items | structured object | required | Excluded items. | stored on current object |
| shared_services | structured object | optional | Shared services and dependencies. | stored on current object |
| open_perimeter_items | structured object | optional | Unresolved items. | stored on current object |
| status | enum | required | Perimeter status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_TRANSITION_SERVICE_AGREEMENT — Transition Service Agreement

A legal agreement under which a seller or affiliate provides defined services to a separated business for a limited term, fee, service level, and exit plan.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| transition_service_agreement_id | string | required | Stable agreement identifier. | immutable |
| legal_agreement_id | reference | required | Underlying legal agreement. | stored on current object |
| separation_perimeter_id | reference | required | Related perimeter. | stored on current object |
| service_schedule | structured object | required | Services, providers, recipients, fees, and service levels. | stored on current object |
| term | duration | required | Agreement term. | stored on current object |
| exit_milestones | structured object | required | Service-exit milestones. | stored on current object |
| status | enum | required | Agreement status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_STANDALONE_COST_BASELINE — Standalone Cost Baseline

A versioned estimate of recurring costs required for a separated business to operate independently, including stranded, replacement, and transition costs.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| standalone_cost_baseline_id | string | required | Stable baseline identifier. | immutable |
| deal_id | reference | required | Carve-out scope. | stored on current object |
| cost_categories | structured object | required | Recurring and one-time costs. | stored on current object |
| assumption_ids | reference array | required | Cost assumptions. | stored on current object |
| as_of_date | date | required | Baseline date. | stored on current object |
| status | enum | required | Baseline status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_FOUNDER_ROLLOVER — Founder Rollover

A transaction arrangement under which a founder or existing owner reinvests value into a continuing security, with amount, percentage, terms, vesting, lock-up, and governance consequences.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| founder_rollover_id | string | required | Stable rollover identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| founder_actor_or_organization_id | reference | required | Rolling holder. | stored on current object |
| security_id | reference | required | Rollover security. | stored on current object |
| rollover_amount | money | optional | Rollover value. | stored on current object |
| rollover_percentage | percentage | optional | Percentage rolled. | stored on current object |
| vesting_and_lockup_terms | structured object | optional | Continuing restrictions. | stored on current object |
| status | enum | required | Rollover status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_AUCTION_PROCESS — Auction Process

A structured sale process with rounds, deadlines, bidder access, process rules, indications, bids, exclusivity, and outcome.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| auction_process_id | string | required | Stable process identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| seller_organization_id | reference | required | Seller or process principal. | stored on current object |
| process_type | enum | required | Process type. | stored on current object |
| rounds_and_deadlines | structured object | required | Process stages and deadlines. | stored on current object |
| bidder_access_rules | structured object | optional | Access rules. | stored on current object |
| status | enum | required | Process status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_VENDOR_DILIGENCE_PACKAGE — Vendor Diligence Package

A seller-commissioned package of financial, commercial, legal, tax, operational, or other diligence supplied to prospective buyers.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| vendor_diligence_package_id | string | required | Stable package identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| source_material_set_id | reference | required | Containing material set. | stored on current object |
| adviser_organization_id | reference | optional | Preparing adviser. | stored on current object |
| scope | structured object | required | Scope and limitations. | stored on current object |
| status | enum | required | Package status. | stored on current object |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_PUBLIC_MARKET_TRANSACTION — Public Market Transaction

A take-private, tender, merger, special-purpose acquisition, public issuance, or similar transaction requiring public-market pricing, disclosure, approval, financing, and completion mechanics.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| public_market_transaction_id | string | required | Stable transaction identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| transaction_type | enum | required | Public-market transaction type. | stored on current object |
| unaffected_price | money | optional | Reference price before announcement. | stored on current object |
| offer_price | money | optional | Offer or transaction price. | stored on current object |
| premium | percentage | optional | Premium to reference price. | stored on current object |
| required_approvals | structured object | optional | Shareholder, regulatory, or exchange approvals. | stored on current object |
| status | enum | required | Transaction status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SHAREHOLDER_APPROVAL — Shareholder Approval

An immutable approval event recording the vote, consent threshold, result, and conditions required from shareholders or equivalent holders.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| shareholder_approval_id | string | required | Stable approval identifier. | immutable |
| public_market_transaction_id | reference | optional | Related public-market transaction. | stored on current object |
| company_id | reference | required | Company whose holders act. | stored on current object |
| approval_type | enum | required | Approval type. | stored on current object |
| threshold | percentage | optional | Required threshold. | stored on current object |
| vote_or_consent_date | date | optional | Decision date. | stored on current object |
| result | enum | required | Approval result. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_SPONSOR_TRACK_RECORD — Sponsor Track Record

A versioned record of an investment organization’s relevant historical investments, outcomes, attribution, team continuity, and strategy-specific performance.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| sponsor_track_record_id | string | required | Stable record identifier. | immutable |
| organization_id | reference | required | Organization assessed. | stored on current object |
| strategy_scope | structured object | required | Relevant strategy and period. | stored on current object |
| investment_entries | structured object | optional | Historical investments and outcomes. | stored on current object |
| performance_metrics | structured object | optional | Gross and net metrics on stated basis. | stored on current object |
| team_continuity | structured object | optional | Team continuity and attribution. | stored on current object |
| verification_status | enum | required | Verification status. | stored on current object |
| status | enum | required | Record status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_KEY_PERSON_DEPENDENCY — Key-Person Dependency

A structured dependency on a specific person or small group whose absence, capacity, incentives, or succession could materially affect execution, governance, or value.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| key_person_dependency_id | string | required | Stable dependency identifier. | immutable |
| deal_id | reference | required | Deal scope. | stored on current object |
| actor_or_role_id | reference | required | Dependent person or role. | stored on current object |
| dependency_type | enum | required | Dependency type. | stored on current object |
| impact_description | text | required | Impact if dependency fails. | stored on current object |
| mitigation_plan | text | optional | Succession or mitigation. | stored on current object |
| status | enum | required | Dependency status. | stored on current object |
| source_document_version_ids | reference array | optional | Document versions providing direct support. | append-only references |
| evidence_item_ids | reference array | optional | Evidence items supporting the object. | append-only references |
| created_at | datetime | required | Creation timestamp. | immutable |
| created_by_actor_id | reference | required | Actor that created the object. | immutable |
| updated_at | datetime | optional | Timestamp of the latest permitted mutation. | updated on permitted mutation |

### ENT_WORKFLOW_EVENT — Workflow Event

An append-only record of a state, transition, workstream, or governance event.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| workflow_event_id | string | required | Stable event identifier. | immutable |
| deal_id | reference | required | Subject deal. | stored on current object |
| event_type | enum | required | Event type. | stored on current object |
| subject_entity_id | reference | required | Object affected. | stored on current object |
| occurred_at | datetime | required | Event timestamp. | immutable |
| actor_role_assignment_id | reference | required | Attributed actor role. | stored on current object |
| idempotency_key | string | required | Unique execution key. | immutable |
| payload | structured object | optional | Typed event payload. | immutable |

### ENT_STALENESS_RECORD — Staleness Record

An append-only record that marks a downstream analytical object stale because an upstream basis changed.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| staleness_record_id | string | required | Stable identifier. | immutable |
| source_object_id | reference | required | Changed upstream object. | stored on current object |
| source_version_id | reference | required | Upstream version that triggered staleness. | stored on current object |
| target_object_id | reference | required | Affected downstream object. | stored on current object |
| reason | text | required | Reason the object is stale. | stored on current object |
| status | enum | required | Staleness status. | stored on current object |
| created_at | datetime | required | Timestamp. | immutable |
| resolved_by_object_id | reference | optional | Successor or recomputed object. | stored on current object |

### ENT_CONDITION_RECORD — Condition Record

A durable condition attached to an approval, gate, signing, closing, funding, or outcome action.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| condition_record_id | string | required | Stable identifier. | immutable |
| subject_entity_id | reference | required | Object or action subject to the condition. | stored on current object |
| condition_type | enum | required | Condition category. | stored on current object |
| description | text | required | Testable condition. | stored on current object |
| status | enum | required | Condition status. | stored on current object |
| due_at | datetime | optional | Deadline. | stored on current object |
| satisfaction_evidence_ids | reference array | optional | Evidence supporting satisfaction. | stored on current object |
| waiver_approval_record_id | reference | optional | Authority record supporting waiver. | stored on current object |
| created_at | datetime | required | Timestamp. | immutable |

### ENT_PERMISSION_EVALUATION_RECORD — Permission Evaluation Record

An immutable evaluation of an actor-role assignment against a permission policy for a requested action.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| permission_evaluation_id | string | required | Stable identifier. | immutable |
| policy_id | reference | required | Policy evaluated. | stored on current object |
| policy_version | string | required | Policy version. | immutable |
| role_assignment_id | reference | required | Contextual subject role. | stored on current object |
| object_entity_id | reference | required | Protected object. | stored on current object |
| action | enum | required | Requested permission action. | stored on current object |
| result | enum | required | Evaluation result. | stored on current object |
| conditions | structured object | optional | Conditions applied. | stored on current object |
| evaluated_at | datetime | required | Timestamp. | immutable |
| workflow_event_id | reference | required | Audit event. | stored on current object |

### ENT_EVIDENCE_SUFFICIENCY_ASSESSMENT — Evidence Sufficiency Assessment

A phase-specific assessment of whether available evidence is relevant, reliable, complete, current, and sufficiently corroborated for a stated conclusion.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| sufficiency_assessment_id | string | required | Stable identifier. | immutable |
| question_id | reference | required | Question assessed. | stored on current object |
| phase | enum | required | Lifecycle phase. | stored on current object |
| evidence_item_ids | reference array | required | Evidence evaluated. | stored on current object |
| relevance_result | enum | required | Relevance result. | stored on current object |
| reliability_result | enum | required | Reliability result. | stored on current object |
| completeness_result | enum | required | Completeness result. | stored on current object |
| recency_result | enum | required | Recency result. | stored on current object |
| corroboration_result | enum | required | Corroboration result. | stored on current object |
| conclusion | enum | required | Sufficiency conclusion. | stored on current object |
| residual_uncertainty | text | optional | Remaining uncertainty. | stored on current object |
| assessed_by_role_assignment_id | reference | required | Assessor. | stored on current object |
| created_at | datetime | required | Timestamp. | immutable |

### ENT_REASONING_RECORD — Reasoning Record

A versioned analytical transformation that connects propositions, evidence, operators, alternatives, findings, confidence, uncertainty, and downstream effects.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| reasoning_record_id | string | required | Stable identifier. | immutable |
| workstream_run_id | reference | required | Workstream execution. | stored on current object |
| starting_proposition | text | required | Proposition evaluated. | stored on current object |
| evidence_item_ids | reference array | required | Evidence consumed. | stored on current object |
| reasoning_operator_ids | reference array | required | Operations applied. | stored on current object |
| alternative_explanations | structured object | optional | Alternatives considered. | stored on current object |
| finding_ids | reference array | required | Findings produced. | stored on current object |
| assumption_ids | reference array | optional | Assumptions created or modified. | stored on current object |
| model_case_ids | reference array | optional | Model outputs produced. | stored on current object |
| valuation_case_ids | reference array | optional | Valuation outputs produced. | stored on current object |
| confidence | enum | required | Confidence level. | stored on current object |
| residual_uncertainty | text | optional | Unresolved uncertainty. | stored on current object |
| version | integer | required | Version number. | stored on current object |
| supersedes_reasoning_record_id | reference | optional | Prior reasoning version. | stored on current object |
| created_at | datetime | required | Timestamp. | immutable |

### ENT_ROLE_DEFINITION — Role Definition

A configurable definition of a contextual role, its permission capabilities, authority classes, delegation constraints, and segregation requirements.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| role_definition_id | string | required | Stable identifier. | immutable |
| role_name | string | required | Role label. | stored on current object |
| scope | structured object | required | Permitted contexts. | stored on current object |
| permission_capabilities | structured object | required | Default permission capabilities. | stored on current object |
| authority_types | structured object | optional | Possible authority actions. | stored on current object |
| delegation_rule | structured object | required | Delegation constraints. | stored on current object |
| conflict_constraints | structured object | required | Conflict rules. | stored on current object |
| sod_constraints | structured object | required | Segregation rules. | stored on current object |
| status | enum | required | Definition status. | stored on current object |
| version | integer | required | Version number. | stored on current object |

### ENT_DELEGATION_RECORD — Delegation Record

An immutable, scoped and time-bound transfer of permitted authority from one contextual role assignment to another.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| delegation_record_id | string | required | Stable identifier. | immutable |
| delegator_role_assignment_id | reference | required | Delegating role assignment. | stored on current object |
| delegate_role_assignment_id | reference | required | Receiving role assignment. | stored on current object |
| authority_action_ids | reference array | required | Delegated actions. | stored on current object |
| scope | structured object | required | Object and process scope. | stored on current object |
| effective_at | datetime | required | Start timestamp. | stored on current object |
| expires_at | datetime | required | Expiry timestamp. | stored on current object |
| status | enum | required | Delegation status. | stored on current object |
| non_delegable_exclusions | structured object | optional | Excluded actions. | stored on current object |
| approval_record_id | reference | required | Approval authorizing delegation. | stored on current object |
| workflow_event_id | reference | required | Audit event. | stored on current object |

### ENT_RECUSAL_RECORD — Recusal Record

An immutable record that removes a conflicted role assignment from a decision, approval, review, or quorum.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| recusal_record_id | string | required | Stable identifier. | immutable |
| role_assignment_id | reference | required | Recused assignment. | stored on current object |
| subject_entity_id | reference | required | Affected object or decision. | stored on current object |
| reason | text | required | Conflict basis. | stored on current object |
| scope | structured object | required | Actions and time scope. | stored on current object |
| effective_at | datetime | required | Start timestamp. | stored on current object |
| expires_at | datetime | optional | End timestamp. | stored on current object |
| workflow_event_id | reference | required | Audit event. | stored on current object |

### ENT_DISSENT_RECORD — Dissent Record

An immutable record of a reasoned disagreement attached to a collective decision or approval.

| Field | Type | Required | Definition | Version behavior |
| --- | --- | --- | --- | --- |
| dissent_record_id | string | required | Stable identifier. | immutable |
| decision_record_id | reference | required | Decision challenged. | stored on current object |
| role_assignment_id | reference | required | Dissenting assignment. | stored on current object |
| statement | text | required | Reasoned dissent. | stored on current object |
| evidence_item_ids | reference array | optional | Supporting evidence. | stored on current object |
| recorded_at | datetime | required | Timestamp. | immutable |

## Relationship catalog

| Relationship ID | Relationship | Source | Target | Cardinality | Required | Definition |
| --- | --- | --- | --- | --- | --- | --- |
| REL_001 | Deal targets Company | ENT_DEAL | ENT_COMPANY | 1:1..* | required | A deal concerns one or more operating companies, assets, or legally defined perimeters. |
| REL_002 | Deal has Organization role | ENT_DEAL | ENT_ORGANIZATION | 1:1..* | required | An organization participates in a deal in a defined role such as sponsor, seller, buyer, lender, adviser, or administrator. |
| REL_003 | Deal uses Fund or Vehicle | ENT_DEAL | ENT_FUND_VEHICLE | 1:1..* | required for investment | A deal is allocated to one or more legal or accounting vehicles. |
| REL_004 | Deal has Investment Exposure | ENT_DEAL | ENT_INVESTMENT_EXPOSURE | 1:0..* | optional | A deal may create one or more vehicle-security exposures. |
| REL_005 | Exposure held by Vehicle | ENT_INVESTMENT_EXPOSURE | ENT_FUND_VEHICLE | 0..*:1 | required | An investment exposure is held or committed by exactly one vehicle. |
| REL_006 | Exposure references Security | ENT_INVESTMENT_EXPOSURE | ENT_SECURITY | 0..*:1 | required | An investment exposure obtains its economics and rights from one security or instrument. |
| REL_007 | Exposure has Position Record | ENT_INVESTMENT_EXPOSURE | ENT_POSITION_RECORD | 1:0..* | optional | An exposure has zero or more as-of position snapshots. |
| REL_008 | Deal has Workstream Run | ENT_DEAL | ENT_WORKSTREAM_RUN | 1:0..* | optional | A deal instantiates workstreams as required by state, archetype, risk, and materiality. |
| REL_009 | Workstream Run instantiates Definition | ENT_WORKSTREAM_RUN | ENT_WORKSTREAM_DEFINITION | 0..*:1 | required | A run implements one version of a reusable workstream definition. |
| REL_010 | Actor has Role Assignment | ENT_ACTOR | ENT_ROLE_ASSIGNMENT | 1:0..* | optional | An actor may hold multiple scoped roles over time. |
| REL_011 | Organization has Role Assignment | ENT_ORGANIZATION | ENT_ROLE_ASSIGNMENT | 1:0..* | optional | An organization may hold multiple deal or entity roles over time. |
| REL_012 | Role Assignment scoped to Deal | ENT_ROLE_ASSIGNMENT | ENT_DEAL | 0..*:0..1 | optional | A role assignment may be scoped to one deal. |
| REL_013 | Access Grant controls Source Material Set | ENT_ACCESS_GRANT | ENT_SOURCE_MATERIAL_SET | 1:0..* | optional | An access grant authorizes use of one or more material sets within its scope. |
| REL_014 | Permission Policy governs Document Artifact | ENT_PERMISSION_POLICY | ENT_DOCUMENT_ARTIFACT | 0..*:0..* | optional | A permission policy may govern actions on document artifacts based on role, classification, and context. |
| REL_015 | Authority Rule governs Gate | ENT_AUTHORITY_RULE | ENT_GATE | 1:0..* | optional | An authority rule specifies the approval or override requirements for a gate. |
| REL_016 | Approval Record satisfies Authority Rule | ENT_APPROVAL_RECORD | ENT_AUTHORITY_RULE | 0..*:1 | required | An approval record evidences an authority decision under one rule version. |
| REL_017 | Approval Record authorizes Decision | ENT_APPROVAL_RECORD | ENT_DECISION_RECORD | 1..*:1 | required for effective decision | One or more approval records authorize or reject a decision. |
| REL_018 | Source Material Set belongs to Deal | ENT_SOURCE_MATERIAL_SET | ENT_DEAL | 0..*:1 | required | A material set is scoped to one deal. |
| REL_019 | Source Material Set contains Document | ENT_SOURCE_MATERIAL_SET | ENT_DOCUMENT_ARTIFACT | 1:0..* | optional | A material set contains zero or more logical documents. |
| REL_020 | Document has Version | ENT_DOCUMENT_ARTIFACT | ENT_DOCUMENT_VERSION | 1:1..* | required | A logical document has one or more immutable content versions. |
| REL_021 | Evidence captured from Document Version | ENT_EVIDENCE_ITEM | ENT_DOCUMENT_VERSION | 0..*:0..1 | optional | An evidence item may be captured from a precise document version and locator. |
| REL_022 | Evidence belongs to Deal | ENT_EVIDENCE_ITEM | ENT_DEAL | 0..*:1 | required | An evidence item is evaluated within one deal context. |
| REL_023 | Deal has Question Register | ENT_DEAL | ENT_QUESTION_REGISTER | 1:0..* | optional | A deal may have multiple versioned question-register snapshots. |
| REL_024 | Question Register contains Question | ENT_QUESTION_REGISTER | ENT_QUESTION | 1:0..* | optional | A register version contains zero or more questions. |
| REL_025 | Question tests Assumption | ENT_QUESTION | ENT_ASSUMPTION | 0..*:0..* | optional | A question may test one or more assumptions, and an assumption may be tested by multiple questions. |
| REL_026 | Evidence supports Assumption | ENT_EVIDENCE_ITEM | ENT_ASSUMPTION | 0..*:0..* | optional | Evidence may increase support for an assumption. |
| REL_027 | Evidence falsifies Assumption | ENT_EVIDENCE_ITEM | ENT_ASSUMPTION | 0..*:0..* | optional | Evidence may challenge or break an assumption. |
| REL_028 | Risk challenges Thesis | ENT_RISK | ENT_INVESTMENT_THESIS | 0..*:0..* | optional | A risk may threaten one or more value-creation claims in a thesis. |
| REL_029 | Assumption belongs to Thesis | ENT_ASSUMPTION | ENT_INVESTMENT_THESIS | 0..*:1..* | required for active thesis | A thesis is supported by one or more explicit assumptions. |
| REL_030 | Metric Observation instantiates Metric Definition | ENT_METRIC_OBSERVATION | ENT_METRIC_DEFINITION | 0..*:1 | required | Each observation uses exactly one metric-definition version. |
| REL_031 | Metric Observation measures Company | ENT_METRIC_OBSERVATION | ENT_COMPANY | 0..*:0..1 | optional | An observation may measure a company. |
| REL_032 | Workstream Run produces Finding | ENT_WORKSTREAM_RUN | ENT_DILIGENCE_FINDING | 1:0..* | optional | A workstream run may produce zero or more diligence findings. |
| REL_033 | Finding supported by Evidence | ENT_DILIGENCE_FINDING | ENT_EVIDENCE_ITEM | 0..*:1..* | required for validated finding | A validated finding is supported by one or more evidence items. |
| REL_034 | Finding resolves Question | ENT_DILIGENCE_FINDING | ENT_QUESTION | 0..*:0..* | optional | A finding may answer, reframe, or leave unresolved a question. |
| REL_035 | Finding updates Assumption | ENT_DILIGENCE_FINDING | ENT_ASSUMPTION | 0..*:0..* | optional | A finding may support, challenge, break, or supersede an assumption. |
| REL_036 | Analytical Model contains Model Case | ENT_ANALYTICAL_MODEL | ENT_MODEL_CASE | 1:1..* | required | A model contains one or more versioned scenario cases. |
| REL_037 | Model Case uses Assumption | ENT_MODEL_CASE | ENT_ASSUMPTION | 1:1..* | required | A model case uses one or more explicit assumption versions. |
| REL_038 | Model Case uses Metric Observation | ENT_MODEL_CASE | ENT_METRIC_OBSERVATION | 1:0..* | optional | A model case consumes measured or forecast observations as inputs or calibration points. |
| REL_039 | Model Case feeds Valuation Case | ENT_MODEL_CASE | ENT_VALUATION_CASE | 0..*:1..* | required | A valuation case uses one or more model cases. |
| REL_040 | Valuation Input feeds Valuation Case | ENT_VALUATION_INPUT | ENT_VALUATION_CASE | 0..*:1..* | required | A valuation case consumes one or more typed valuation inputs. |
| REL_041 | Valuation Case supports Decision | ENT_VALUATION_CASE | ENT_DECISION_RECORD | 0..*:0..* | optional | A decision may rely on one or more valuation cases. |
| REL_042 | Adjustment Item modifies Valuation Input | ENT_ADJUSTMENT_ITEM | ENT_VALUATION_INPUT | 0..*:0..1 | optional | An accepted adjustment changes a metric or valuation input basis. |
| REL_043 | Bridge Analysis decomposes Valuation or Metric Change | ENT_BRIDGE_ANALYSIS | ENT_VALUATION_CASE | 0..*:0..* | optional | A bridge may explain the change between valuation or return states. |
| REL_044 | Value Creation Plan contains Assumption | ENT_VALUE_CREATION_PLAN | ENT_ASSUMPTION | 1:1..* | required | A value-creation plan depends on explicit assumptions. |
| REL_045 | Value Creation Plan defines Metric Target | ENT_VALUE_CREATION_PLAN | ENT_METRIC_DEFINITION | 1:0..* | optional | A plan identifies metrics used to measure initiative execution. |
| REL_046 | Materiality Assessment applies to Deal | ENT_MATERIALITY_ASSESSMENT | ENT_DEAL | 0..*:1 | required | Every materiality assessment is evaluated in a deal context. |
| REL_047 | Materiality Assessment drives Gate | ENT_MATERIALITY_ASSESSMENT | ENT_GATE | 0..*:0..* | optional | A materiality result may satisfy, warn, block, trigger, or reopen a gate. |
| REL_048 | Gate authorizes Transition | ENT_GATE | ENT_DEAL | 0..*:1 | required for gated transition | A satisfied or validly waived gate authorizes a specified state transition for a deal. |
| REL_049 | Decision consumes Question Register | ENT_DECISION_RECORD | ENT_QUESTION_REGISTER | 0..*:0..1 | optional | A decision references the question-register snapshot used at the decision time. |
| REL_050 | Decision consumes Risk Acceptance | ENT_DECISION_RECORD | ENT_RISK_ACCEPTANCE_RECORD | 0..*:0..* | optional | A decision may rely on explicit acceptance of residual risks or unresolved questions. |
| REL_051 | Risk Acceptance resolves Risk | ENT_RISK_ACCEPTANCE_RECORD | ENT_RISK | 0..*:0..1 | optional | A risk-acceptance record may accept one residual risk. |
| REL_052 | Exception Record waives Gate | ENT_EXCEPTION_RECORD | ENT_GATE | 0..*:0..1 | optional | An exception may waive or defer a specific gate requirement. |
| REL_053 | Execution Set contains Legal Agreement | ENT_EXECUTION_DOCUMENT_SET | ENT_LEGAL_AGREEMENT | 1:0..* | optional | An execution set contains zero or more legal agreements required for the transaction. |
| REL_054 | Legal Agreement defines Security | ENT_LEGAL_AGREEMENT | ENT_SECURITY | 0..*:0..* | optional | A legal agreement may create, issue, amend, or govern one or more securities. |
| REL_055 | Legal Agreement contains Covenant | ENT_LEGAL_AGREEMENT | ENT_COVENANT | 1:0..* | optional | A legal agreement may contain zero or more covenants. |
| REL_056 | Legal Agreement grants Governance Right | ENT_LEGAL_AGREEMENT | ENT_GOVERNANCE_RIGHT | 1:0..* | optional | A legal agreement may grant governance and information rights. |
| REL_057 | Closing Record confirms Execution Set | ENT_CLOSING_RECORD | ENT_EXECUTION_DOCUMENT_SET | 0..*:1 | required for closed status | A closing record confirms one signed execution-document set. |
| REL_058 | Closing Record creates Exposure | ENT_CLOSING_RECORD | ENT_INVESTMENT_EXPOSURE | 1:1..* | required for investment closing | A closing may create one or more live investment exposures. |
| REL_059 | Capital Event affects Exposure | ENT_CAPITAL_EVENT | ENT_INVESTMENT_EXPOSURE | 0..*:1 | required | A capital event changes the economic state of one exposure. |
| REL_060 | Monitoring Record contains Observation | ENT_MONITORING_RECORD | ENT_METRIC_OBSERVATION | 1:1..* | required | A monitoring record contains one or more period observations. |
| REL_061 | Monitoring Record compares Model Case | ENT_MONITORING_RECORD | ENT_MODEL_CASE | 0..*:0..1 | optional | A monitoring record may compare actuals against an approved model-case baseline. |
| REL_062 | Monitoring Record detects Trigger | ENT_MONITORING_RECORD | ENT_REUNDERWRITING_TRIGGER | 1:0..* | optional | A monitoring record may create zero or more re-underwriting triggers. |
| REL_063 | Trigger creates Re-underwriting Record | ENT_REUNDERWRITING_TRIGGER | ENT_REUNDERWRITING_RECORD | 1..*:1 | required for trigger-driven review | One or more validated triggers initiate a re-underwriting cycle. |
| REL_064 | Re-underwriting compares Original Model Case | ENT_REUNDERWRITING_RECORD | ENT_MODEL_CASE | 0..*:1 | required | A re-underwriting record compares current evidence with the original or prior approved model case. |
| REL_065 | Re-underwriting updates Assumption | ENT_REUNDERWRITING_RECORD | ENT_ASSUMPTION | 0..*:0..* | optional | A re-underwriting record may confirm, break, or supersede assumptions. |
| REL_066 | Re-underwriting produces Decision | ENT_REUNDERWRITING_RECORD | ENT_DECISION_RECORD | 0..*:0..1 | optional | A re-underwriting record may produce a hold, follow-on, rescue, restructure, sell, impairment, or no-action decision. |
| REL_067 | Decision creates Outcome | ENT_DECISION_RECORD | ENT_OUTCOME_RECORD | 0..*:0..* | optional | A decision may authorize or record an outcome. |
| REL_068 | Capital Event updates Outcome | ENT_CAPITAL_EVENT | ENT_OUTCOME_RECORD | 0..*:0..* | optional | Capital events provide economic realization, impairment, or write-off evidence for outcomes. |
| REL_069 | Outcome updates Deal | ENT_OUTCOME_RECORD | ENT_DEAL | 0..*:1 | optional | An outcome may close, partially close, restructure, or keep a deal open. |
| REL_070 | Value Creation Plan has Synergy Plan | ENT_VALUE_CREATION_PLAN | ENT_SYNERGY_PLAN | 1:0..* | optional | A value-creation plan may include a separately governed synergy plan. |
| REL_071 | Synergy Plan realized by Integration Plan | ENT_SYNERGY_PLAN | ENT_INTEGRATION_PLAN | 0..*:0..1 | optional | An integration plan executes and tracks the operational steps required to realize synergies. |
| REL_072 | Value Creation Plan has Add-on Pipeline | ENT_VALUE_CREATION_PLAN | ENT_ADD_ON_PIPELINE | 1:0..1 | optional | A buy-and-build plan may include an add-on pipeline. |
| REL_073 | Platform Link has Platform Company | ENT_PLATFORM_ADD_ON_LINK | ENT_COMPANY | 0..*:1 | required | A platform-add-on link identifies exactly one platform company. |
| REL_074 | Platform Link has Add-on Company | ENT_PLATFORM_ADD_ON_LINK | ENT_COMPANY | 0..*:1 | required | A platform-add-on link identifies exactly one add-on company. |
| REL_075 | Separation Perimeter defines Company | ENT_SEPARATION_PERIMETER | ENT_COMPANY | 0..*:1 | required for carve-out | A separation perimeter defines the operating scope of a carve-out company. |
| REL_076 | Transition Service Agreement supports Perimeter | ENT_TRANSITION_SERVICE_AGREEMENT | ENT_SEPARATION_PERIMETER | 0..*:1 | optional | A transition-service agreement supports operating dependencies arising from a separation perimeter. |
| REL_077 | Standalone Cost Baseline feeds Model Case | ENT_STANDALONE_COST_BASELINE | ENT_MODEL_CASE | 0..*:1..* | required when standalone costs are material | A standalone-cost baseline supplies cost assumptions to carve-out model cases. |
| REL_078 | Founder Rollover references Security | ENT_FOUNDER_ROLLOVER | ENT_SECURITY | 0..*:1 | required | A founder rollover is implemented through one continuing security. |
| REL_079 | Auction Process generates Source Set | ENT_AUCTION_PROCESS | ENT_SOURCE_MATERIAL_SET | 1:0..* | optional | An auction process may issue process materials and data-room sets. |
| REL_080 | Vendor Package supplies Source Set | ENT_VENDOR_DILIGENCE_PACKAGE | ENT_SOURCE_MATERIAL_SET | 0..*:1 | required | A vendor-diligence package is distributed within one source-material set. |
| REL_081 | Public Transaction has Shareholder Approval | ENT_PUBLIC_MARKET_TRANSACTION | ENT_SHAREHOLDER_APPROVAL | 1:0..* | optional | A public-market transaction may require one or more holder approvals. |
| REL_082 | Sponsor Track Record informs Risk | ENT_SPONSOR_TRACK_RECORD | ENT_RISK | 0..*:0..* | optional | A sponsor track record may create or mitigate sponsor-execution risk. |
| REL_083 | Key-Person Dependency is Risk | ENT_KEY_PERSON_DEPENDENCY | ENT_RISK | 0..*:1 | required | A key-person dependency is represented as or linked to a risk object for decision and monitoring purposes. |
| REL_084 | Document belongs to Deal | ENT_DOCUMENT_ARTIFACT | ENT_DEAL | 0..*:0..1 | optional | A deal-scoped document is associated with exactly one deal unless explicitly classified as reusable reference material. |
| REL_085 | Document produced by Organization | ENT_DOCUMENT_ARTIFACT | ENT_ORGANIZATION | 0..*:0..1 | optional | A document may identify the organization responsible for producing or issuing it. |
| REL_086 | Document represents Investment Thesis | ENT_DOCUMENT_ARTIFACT | ENT_INVESTMENT_THESIS | 0..*:0..* | optional | A document may present one or more thesis versions without becoming the thesis object itself. |
| REL_087 | Screening Assessment produces Decision | ENT_SCREENING_ASSESSMENT | ENT_DECISION_RECORD | 1:1 | required for finalized screening | A finalized screening assessment produces a proceed, decline, defer, or exception-proceed decision record. |
| REL_088 | Model Case produces Metric Observation | ENT_MODEL_CASE | ENT_METRIC_OBSERVATION | 1:1..* | required | A model case produces forecast, target, stress, or re-underwritten metric observations. |
| REL_089 | Permission Policy governs Deal | ENT_PERMISSION_POLICY | ENT_DEAL | 0..*:0..* | optional | A permission policy may govern actions on deal records and their inherited object scope. |
| REL_090 | Workstream Run produces Valuation Input | ENT_WORKSTREAM_RUN | ENT_VALUATION_INPUT | 1:0..* | optional | A workstream run may produce a decision-relevant input for valuation or return analysis. |
| REL_091 | Workstream Run configures Security | ENT_WORKSTREAM_RUN | ENT_SECURITY | 0..*:0..* | optional | Financing, structuring, tax, or legal work may propose or revise security terms before execution. |
| REL_092 | Bridge Analysis decomposes Thesis | ENT_BRIDGE_ANALYSIS | ENT_INVESTMENT_THESIS | 0..*:0..* | optional | A bridge analysis may decompose thesis value drivers, operating change, or entry-to-exit value into quantified components. |
| REL_093 | Synergy Plan feeds Model Case | ENT_SYNERGY_PLAN | ENT_MODEL_CASE | 0..*:0..* | optional | A synergy plan may provide timing, cost, and value assumptions to one or more model cases. |
| REL_094 | Add-on Pipeline supports Thesis | ENT_ADD_ON_PIPELINE | ENT_INVESTMENT_THESIS | 0..*:0..1 | optional | An add-on pipeline may support a buy-and-build thesis, subject to probability and execution constraints. |
| REL_095 | Exception Record modifies Gate | ENT_EXCEPTION_RECORD | ENT_GATE | 0..*:0..1 | optional | An effective exception may waive, defer, or alter one specifically identified gate condition. |
| REL_096 | Deal records Workflow Event | ENT_DEAL | ENT_WORKFLOW_EVENT | 1:0..* | required | A deal owns an append-only sequence of workflow events. |
| REL_097 | Staleness Record affects analytical object | ENT_STALENESS_RECORD | ENT_DOCUMENT_ARTIFACT | 1:1 | required | A staleness record identifies a downstream representation or analytical object that must be recomputed or reviewed. |
| REL_098 | Approval attaches Condition | ENT_APPROVAL_RECORD | ENT_CONDITION_RECORD | 1:0..* | optional | An approval may impose one or more explicit, testable conditions. |
| REL_099 | Gate requires Condition | ENT_GATE | ENT_CONDITION_RECORD | 1:0..* | optional | A gate may require conditions to be satisfied or explicitly waived. |
| REL_100 | Condition is supported by Evidence | ENT_CONDITION_RECORD | ENT_EVIDENCE_ITEM | 1:0..* | optional | Evidence supports satisfaction, failure, or waiver evaluation of a condition. |
| REL_101 | Permission Policy produces Evaluation | ENT_PERMISSION_POLICY | ENT_PERMISSION_EVALUATION_RECORD | 1:0..* | required | A permission policy is evaluated for a role assignment, object, and requested action. |
| REL_102 | Permission Evaluation evaluates Role Assignment | ENT_PERMISSION_EVALUATION_RECORD | ENT_ROLE_ASSIGNMENT | 1:1 | required | A permission evaluation applies to one contextual role assignment. |
| REL_103 | Role Assignment instantiates Role Definition | ENT_ROLE_ASSIGNMENT | ENT_ROLE_DEFINITION | 0..*:1 | required | A contextual role assignment instantiates an effective role definition. |
| REL_104 | Delegation transfers scoped authority | ENT_DELEGATION_RECORD | ENT_ROLE_ASSIGNMENT | 1:1 | required | A delegation record transfers listed actions within a bounded scope and period to a receiving assignment. |
| REL_105 | Recusal removes Role Assignment | ENT_RECUSAL_RECORD | ENT_ROLE_ASSIGNMENT | 1:1 | required | A recusal excludes a contextual role assignment from specified governance actions. |
| REL_106 | Dissent attaches to Decision | ENT_DISSENT_RECORD | ENT_DECISION_RECORD | 0..*:1 | optional | A dissent record preserves a reasoned disagreement with a collective decision. |
| REL_107 | Question has Evidence Sufficiency Assessment | ENT_QUESTION | ENT_EVIDENCE_SUFFICIENCY_ASSESSMENT | 1:0..* | optional | A question may have phase-specific sufficiency assessments over its evidence set. |
| REL_108 | Reasoning Record consumes Evidence | ENT_REASONING_RECORD | ENT_EVIDENCE_ITEM | 1:1..* | required | A reasoning record identifies the evidence used in an analytical transformation. |
| REL_109 | Reasoning Record produces Finding | ENT_REASONING_RECORD | ENT_DILIGENCE_FINDING | 1:1..* | required | A reasoning record produces one or more findings. |
| REL_110 | Reasoning Record modifies Assumption | ENT_REASONING_RECORD | ENT_ASSUMPTION | 1:0..* | optional | A reasoning record may create, support, challenge, reject, or supersede an assumption. |
| REL_111 | Reasoning Record produces Model Case | ENT_REASONING_RECORD | ENT_MODEL_CASE | 1:0..* | optional | A model reasoning record may produce a versioned model case. |
| REL_112 | Reasoning Record produces Valuation Case | ENT_REASONING_RECORD | ENT_VALUATION_CASE | 1:0..* | optional | A valuation reasoning record may produce a versioned valuation case. |
| REL_113 | Covenant is tested by Metric Observation | ENT_COVENANT | ENT_METRIC_OBSERVATION | 1:0..* | optional | A covenant is evaluated against one or more metric observations. |
| REL_114 | Monitoring Record tests Covenant | ENT_MONITORING_RECORD | ENT_COVENANT | 1:0..* | optional | A monitoring record may evaluate covenant compliance and headroom. |
| REL_115 | Covenant breach creates Trigger | ENT_COVENANT | ENT_REUNDERWRITING_TRIGGER | 1:0..* | optional | A covenant breach or headroom deterioration may create a re-underwriting trigger. |
| REL_116 | Founder Rollover grants Governance Right | ENT_FOUNDER_ROLLOVER | ENT_GOVERNANCE_RIGHT | 1:0..* | optional | A founder rollover may carry explicit governance rights and retained influence. |
| REL_117 | Key-Person Dependency concerns Role Assignment | ENT_KEY_PERSON_DEPENDENCY | ENT_ROLE_ASSIGNMENT | 1:1..* | required | A key-person dependency concerns one or more contextual management or sponsor role assignments. |
| REL_118 | Decision approves Model Case | ENT_DECISION_RECORD | ENT_MODEL_CASE | 1:0..* | optional | A decision identifies the exact model-case version used as its approved basis. |
| REL_119 | Decision approves Valuation Case | ENT_DECISION_RECORD | ENT_VALUATION_CASE | 1:0..* | optional | A decision identifies the exact valuation-case version used as its approved basis. |
| REL_120 | Decision approves Assumption Version | ENT_DECISION_RECORD | ENT_ASSUMPTION | 1:0..* | optional | A decision identifies the assumption versions relied upon. |
| REL_121 | Monitoring compares against Decision | ENT_MONITORING_RECORD | ENT_DECISION_RECORD | 0..*:1 | required | Monitoring compares actual evidence against an immutable approved decision baseline. |
| REL_122 | Re-underwriting supersedes Decision | ENT_REUNDERWRITING_RECORD | ENT_DECISION_RECORD | 1:0..* | optional | A re-underwriting record may support a successor decision without overwriting the prior decision. |
| REL_123 | Analytical object creates Staleness Record | ENT_ASSUMPTION | ENT_STALENESS_RECORD | 1:0..* | optional | A changed assumption creates staleness records for affected downstream objects. |
| REL_124 | Approval includes Permission Evaluation | ENT_APPROVAL_RECORD | ENT_PERMISSION_EVALUATION_RECORD | 1:1..* | required | An authority action includes permission evaluations proving the actor may perform the action. |
| REL_125 | Approval records Recusal | ENT_APPROVAL_RECORD | ENT_RECUSAL_RECORD | 1:0..* | optional | An approval records recusals that affected participation or quorum. |
| REL_126 | Approval records Dissent | ENT_APPROVAL_RECORD | ENT_DISSENT_RECORD | 1:0..* | optional | An approval may record dissent from collective participants. |
| REL_127 | Approval authorizes Delegation | ENT_APPROVAL_RECORD | ENT_DELEGATION_RECORD | 1:0..* | optional | An approval authorizes a scoped delegation where delegation is permitted. |

## Transactional invariants

- A successful transition updates the current-state projection and appends its event atomically.
- An authority action is effective only when permission, role eligibility, authority rule, quorum, conflict, evidence, materiality, condition, and expiry checks succeed.
- A stale analytical object cannot satisfy a final-output gate unless an explicit approved exception permits provisional use.
- Historical approval, decision, evidence, assumption, model, valuation, and term versions remain addressable after supersession.
- Capital commitment and funding release are separate actions and records.
- Skipped states and overridden blockers create explicit exception or waiver records.
- Object deletion cannot remove a referenced historical basis; archival preserves identity and lineage.
