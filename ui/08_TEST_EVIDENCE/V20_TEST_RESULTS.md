# PANTA V20 Test Results

- **Status:** PASS
- **Passed:** 49 / 49
- **Failed:** 0

Tests the bundled V20 frontend, three synthetic fixture packs, typed schemas, pure compiler and transition adapters, and the stateful Mock Connected reference API. It does not certify production authentication/RBAC, a production Case Store, a live autonomous research service, external human contact, external effects, or Anto's separate production runtime.

## Results

### PASS - Release identity is V20 / 20.0.0

Category: `RELEASE`  
Duration: `0.08 ms`

```json
{
  "release": "V20",
  "semantic_version": "20.0.0"
}
```

### PASS - Three structurally distinct synthetic cases are packaged

Category: `GENERALIZATION`  
Duration: `0.09 ms`

```json
{
  "cases": [
    "PROJECT-KEYSTONE",
    "PROJECT-ORION",
    "PROJECT-TETHYS"
  ]
}
```

### PASS - Connected/core code is fixture-free

Category: `CORE_PURITY`  
Duration: `2.34 ms`

```json
{
  "scanned_files": 11,
  "case_specific_matches": 0
}
```

### PASS - Tethys fixture is resynthesized and confidential-safe

Category: `FIXTURE_SAFETY`  
Duration: `27.63 ms`

```json
{
  "real_identifiers": 0,
  "synthetic": true
}
```

### PASS - Venture statement overlap is below 20%

Category: `GENERALIZATION`  
Duration: `3.84 ms`

```json
{
  "normalized_exact_overlap": {
    "Keystone": 0.0,
    "Orion": 0.0
  },
  "tethys_claims": 30
}
```

### PASS - Early-stage venture case contains no LBO grammar

Category: `GENERALIZATION`  
Duration: `45.08 ms`

```json
{
  "banned_lbo_terms": 0
}
```

### PASS - Venture grammar uses a hierarchical archetype

Category: `VENTURE_GRAMMAR`  
Duration: `0.02 ms`

```json
{
  "kernel": "PANTA_LIVE_INVESTMENT_CASE",
  "archetype": "VENTURE",
  "stage_overlay": "PRE_REVENUE_SEED",
  "sector_overlay": "DEEP_TECH_MARITIME_SECURITY",
  "fund_lens": "TY-LENS-VENTURE-CORE",
  "deal_instance": "PROJECT-TETHYS"
}
```

### PASS - Interactions carry speaker-level provenance and governance

Category: `INTERACTIONS`  
Duration: `0.03 ms`

```json
{
  "participants": 8,
  "interactions": 6
}
```

### PASS - Every utterance resolves to a speaker and interaction

Category: `INTERACTIONS`  
Duration: `0.03 ms`

```json
{
  "utterances": 7,
  "references_valid": true
}
```

### PASS - Observed speech act does not make its content observed truth

Category: `EPISTEMIC`  
Duration: `0.02 ms`

```json
{
  "content_claims_asserted": 6,
  "speech_act_observations": 6
}
```

### PASS - V20 venture objects are bitemporal

Category: `TEMPORAL`  
Duration: `0.21 ms`

```json
{
  "objects_checked": 62,
  "collections": [
    "claims",
    "interactions",
    "utterances",
    "agent_missions",
    "spine_change_proposals",
    "condition_edges",
    "validation_envelopes",
    "derivation_specs",
    "lenses"
  ]
}
```

### PASS - Discrepancies are generated from declarative rules

Category: `COMPILER`  
Duration: `0.01 ms`

```json
{
  "rules": 3,
  "preauthored_candidates": 0,
  "types": [
    "CONDITIONAL_INVALIDATION",
    "EXACT_CONTRADICTION",
    "NUMERIC_INCOMPATIBILITY"
  ]
}
```

### PASS - Deterministic derivations expose inputs, formula and assumptions

Category: `DERIVATIONS`  
Duration: `0.01 ms`

```json
{
  "specs": 4,
  "methods": [
    "CIRCLE_AREA",
    "IMPLIED_RADIUS_FROM_AREA_AND_NODE_COUNT",
    "RUNWAY_MONTHS",
    "POST_MONEY_OWNERSHIP"
  ]
}
```

### PASS - AI explanations are separate from deterministic derivations

Category: `EPISTEMIC`  
Duration: `0.0 ms`

```json
{
  "templates": 5,
  "base_hypotheses": 0
}
```

### PASS - Agent missions declare authority, data-egress and stop conditions

Category: `MISSIONS`  
Duration: `0.03 ms`

```json
{
  "missions": 5,
  "human_or_physical": 2
}
```

### PASS - Venture financing, dilution and ownership arithmetic reconcile

Category: `VENTURE_FINANCE`  
Duration: `0.01 ms`

```json
{
  "post_money_eur_m": 22.5,
  "new_investor_ownership_pct": 20.0,
  "cap_tables_sum_to": 100
}
```

### PASS - Condition edges and technical validation envelopes are first-class

Category: `TECHNICAL_VALIDATION`  
Duration: `0.0 ms`

```json
{
  "condition_edges": 2,
  "validation_envelopes": 3
}
```

### PASS - Fund Lens changes emphasis through projection policy, not facts

Category: `LENS`  
Duration: `0.38 ms`

```json
{
  "lenses": 4,
  "behaviors": [
    "question order",
    "ranking weights",
    "required questions",
    "controls"
  ]
}
```

### PASS - All public schemas contain typed properties

Category: `SCHEMAS`  
Duration: `1.7 ms`

```json
{
  "schema_count": 23,
  "untyped_property_gaps": 0
}
```

### PASS - Browser and Python runtime syntax is valid

Category: `SYNTAX`  
Duration: `3693.46 ms`

```json
{
  "javascript_files": 10,
  "python_files": 4,
  "errors": 0
}
```

### PASS - Compiler bundle maps through a pure typed adapter

Category: `ADAPTERS`  
Duration: `26.82 ms`

```json
{
  "deterministic": true,
  "pure": true,
  "schema_errors": 0,
  "projection_id": "PROJ-COMPILER-faf03ad0ac63fb49"
}
```

### PASS - Frozen engine output maps through a pure 19-field adapter

Category: `ADAPTERS`  
Duration: `3.08 ms`

```json
{
  "deterministic": true,
  "pure": true,
  "schema_errors": 0,
  "integration_fields": 19
}
```

### PASS - No detected firm act carries the attested class

Category: `EPISTEMIC`  
Duration: `0.37 ms`

```json
{
  "firm_acts_misclassified_attested": 0
}
```

### PASS - Canonical approved EV ceiling terminology is preserved

Category: `LANGUAGE`  
Duration: `44.94 ms`

```json
{
  "retired_phrase_hits": 0
}
```

### PASS - Connected mode refuses fixture-backed data

Category: `MODE_HONESTY`  
Duration: `2.73 ms`

```json
{
  "status": 503,
  "error_code": "CONNECTED_BACKEND_NOT_CONFIGURED"
}
```

### PASS - All three live projections and contexts validate

Category: `SCHEMAS`  
Duration: `203.45 ms`

```json
{
  "PROJECT-KEYSTONE": {
    "projection_errors": 0,
    "context_errors": 0
  },
  "PROJECT-ORION": {
    "projection_errors": 0,
    "context_errors": 0
  },
  "PROJECT-TETHYS": {
    "projection_errors": 0,
    "context_errors": 0
  }
}
```

### PASS - Compiler layer generates reviewable V20 proposals

Category: `COMPILER`  
Duration: `28.86 ms`

```json
{
  "discrepancies": 3,
  "derivations": 4,
  "hypotheses": 5,
  "spine_changes": 1
}
```

### PASS - Selecting a past date renders only then-known information

Category: `TEMPORAL`  
Duration: `28.17 ms`

```json
{
  "as_of_date": "2026-06-05",
  "interactions": 1,
  "claims": 7,
  "active_lens": "TY-LENS-VENTURE-CORE"
}
```

### PASS - Causal Replay is event-derived, bitemporal and read-only

Category: `TEMPORAL`  
Duration: `87.41 ms`

```json
{
  "event_id": "TY-REG-011",
  "registry_before": 11,
  "registry_after": 11,
  "stable_hash": "sha256:d4e362a68e78ef415010d50b7079919fe46628ceeaf2d3543f6e9589082cf647"
}
```

### PASS - Lens changes ranking and visibility without changing facts

Category: `LENS`  
Duration: `73.03 ms`

```json
{
  "core_first": [
    "TYQ-PROBLEM",
    "TYQ-PERFORMANCE",
    "TYQ-DEPLOYMENT"
  ],
  "deep_tech_first": [
    "TYQ-PERFORMANCE",
    "TYQ-DEPLOYMENT",
    "TYQ-DIFFERENTIATION"
  ],
  "facts_hash_stable": true
}
```

### PASS - Candidate discrepancy requires professional review

Category: `COMPILER`  
Duration: `47.74 ms`

```json
{
  "discrepancy_id": "TY-DISC-RADIUS",
  "automatic_truth_change": false,
  "review_status": "ADMITTED"
}
```

### PASS - Deterministic arithmetic produces inspectable expected values

Category: `DERIVATIONS`  
Duration: `33.03 ms`

```json
{
  "TY-DER-NOMINAL-AREA": 201.06,
  "TY-DER-IMPLIED-RADIUS": 97.72,
  "TY-DER-RUNWAY": 16.0,
  "TY-DER-OWNERSHIP": 20.0
}
```

### PASS - AI hypothesis cannot propagate before admission

Category: `EPISTEMIC`  
Duration: `58.46 ms`

```json
{
  "hypothesis_id": "TY-DISC-RADIUS-H1",
  "before": false,
  "after": true
}
```

### PASS - Question-spine changes are governed and replayable

Category: `SPINE_GOVERNANCE`  
Duration: `88.19 ms`

```json
{
  "associate_status": 403,
  "partner_status": 200,
  "question_count": 10
}
```

### PASS - Preparing a mission causes no research or external effect

Category: `MISSIONS`  
Duration: `48.49 ms`

```json
{
  "status": "PREPARED",
  "source_count_unchanged": true
}
```

### PASS - Policy-safe synthetic mission creates a reviewable source

Category: `MISSIONS`  
Duration: `41.57 ms`

```json
{
  "mission_id": "TY-MISSION-PROCUREMENT",
  "new_source": "SRC-MISSION-ED9A0B83FD09",
  "review_required": true,
  "external_effects": false
}
```

### PASS - Human-contact and physical missions cannot auto-run

Category: `MISSIONS`  
Duration: `30.47 ms`

```json
{
  "mission_id": "TY-MISSION-SEA-TRIAL",
  "status": 409,
  "error_code": "MISSION_AUTHORITY_REQUIRED"
}
```

### PASS - Transcript ingestion creates native interactions and asserted content claims

Category: `INTERACTIONS`  
Duration: `111.34 ms`

```json
{
  "job_id": "JOB-52E8351B9662",
  "interaction_id": "INT-EAB410571E19",
  "utterances": 2,
  "claims": 2,
  "content_class": "asserted"
}
```

### PASS - Human Stop settlement is refused without scoped authority

Category: `AUTHORITY`  
Duration: `56.54 ms`

```json
{
  "human_stop_id": "TY-HS-SEED-TECH-GATE",
  "settlement_status_without_authority": 409
}
```

### PASS - Authority rejects a mismatched Candidate

Category: `AUTHORITY`  
Duration: `52.15 ms`

```json
{
  "status": 409,
  "error_code": "CANDIDATE_CONTEXT_MISMATCH"
}
```

### PASS - Preparation rejects changes outside the transition output

Category: `SETTLEMENT`  
Duration: `44.21 ms`

```json
{
  "status": 409,
  "error_code": "UNKNOWN_CHANGE_ID"
}
```

### PASS - Authority, course-specific execution and settlement complete coherently

Category: `GOVERNED_FLOW`  
Duration: `149.5 ms`

```json
{
  "authority_schema_errors": 0,
  "package_status": "ACCEPTED",
  "settlement_schema_errors": 0,
  "current_state_id": "STATE-F50DC056F9FE"
}
```

### PASS - Blocked scope remains explicit and requires bounded partial settlement

Category: `SETTLEMENT`  
Duration: `83.97 ms`

```json
{
  "without_partial": 409,
  "with_partial": 200,
  "blocked_component_id": "TY-COMP-MAINTENANCE-ECONOMICS"
}
```

### PASS - Idempotency key rejects a conflicting payload

Category: `IDEMPOTENCY`  
Duration: `43.1 ms`

```json
{
  "first_status": 200,
  "conflict_status": 409,
  "error_code": "IDEMPOTENCY_CONFLICT"
}
```

### PASS - Incompatible authority courses cannot coexist

Category: `AUTHORITY`  
Duration: `68.76 ms`

```json
{
  "first_course": "TY-COURSE-A",
  "second_course": "TY-COURSE-B",
  "second_status": 409,
  "error_code": "HUMAN_STOP_NOT_OPEN"
}
```

### PASS - Authority records cannot be reused across runs

Category: `AUTHORITY`  
Duration: `73.49 ms`

```json
{
  "source_run": "RUN-58E93F449368",
  "target_run": "RUN-E4991CE889C4",
  "reuse_status": 409
}
```

### PASS - Failed delivery never reports optimistic success

Category: `EXECUTION`  
Duration: `72.79 ms`

```json
{
  "send_status": 503,
  "error_code": "DELIVERY_FAILED",
  "pre_ack_status": "READY"
}
```

### PASS - Defer has no executable package

Category: `EXECUTION`  
Duration: `0.01 ms`

```json
{
  "course_id": "TY-COURSE-C",
  "effect_type": "DEFER",
  "execution_package": null
}
```

### PASS - V20 venture objects and governed flows render in the browser

Category: `BROWSER_E2E`  
Duration: `15161.4 ms`

```json
{
  "screenshots": [
    "08_TEST_EVIDENCE/browser/v20_01_deal_command.png",
    "08_TEST_EVIDENCE/browser/v20_02_interactions.png",
    "08_TEST_EVIDENCE/browser/v20_03_utterance_aperture.png",
    "08_TEST_EVIDENCE/browser/v20_04_compiler_review.png",
    "08_TEST_EVIDENCE/browser/v20_05_validation_conditions.png",
    "08_TEST_EVIDENCE/browser/v20_06_unknowns_missions.png",
    "08_TEST_EVIDENCE/browser/v20_07_venture_financing.png",
    "08_TEST_EVIDENCE/browser/v20_08_replay.png",
    "08_TEST_EVIDENCE/browser/v20_09_human_stop.png",
    "08_TEST_EVIDENCE/browser/v20_10_blocked_component.png",
    "08_TEST_EVIDENCE/browser/v20_11_mobile_read_review.png"
  ],
  "lens_facts_stable": true,
  "lens_order_changed": true,
  "console_errors": []
}
```

