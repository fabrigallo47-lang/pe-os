# PANTA Semantic Handoff v0.2

## Read first

1. `00_RELEASE_NOTES.md`
2. `01_universal_investment_kernel_v0_2.yaml`
3. `02_buyout_archetype_pack_v0_2.yaml`
4. `03_provisional_fund_lens_schema_v0_1.md`
5. `04_semantic_extraction_contract_v0_2.md`
6. `06_relation_update_contract_v0_2.yaml`
7. `07_archetype_lens_boundary_audit_v0_2.yaml`
8. `09_blind_benchmark_spec_v0_1.yaml`

## Core implementation flow

```text
Archetype Pack + provisional or validated Fund Lens + Deal Frame
→ route source extraction
→ emit semantic proposal
→ validate identity, binding and relation
→ automatic admission under policy or exceptional review
→ append canonical event
→ filter runtime-ready assertions
→ Dynamic
```

## Files

### Architecture and domain
- `01_universal_investment_kernel_v0_2.yaml`
- `02_buyout_archetype_pack_v0_2.yaml`
- `03_provisional_fund_lens_schema_v0_1.schema.json`
- `03_provisional_fund_lens_schema_v0_1.md`

### Compiler to Dynamic boundary
- `04_semantic_extraction_contract_v0_2.schema.json`
- `04_semantic_extraction_contract_v0_2.md`
- `05_canonical_case_event_v0_2.schema.json`
- `06_relation_update_contract_v0_2.yaml`

### Governance and testing
- `07_archetype_lens_boundary_audit_v0_2.yaml`
- `08_ui_projection_map_v0_2.json`
- `09_blind_benchmark_spec_v0_1.yaml`
- `10_legacy_to_v0_2_mapping.yaml`
- `examples/`
- `validate_package.py`

## Immediate engineering work

### Compiler
- Use the Buyout Pack only to route and contextualize extraction.
- Emit v0.2 proposal objects.
- Record Claims even when binding remains unresolved.
- Keep similarity as trace metadata.
- Store `CHALLENGES` as semantic-only with `PENDING_ADAPTER`.
- Create canonical events only after validation/admission.

### Dynamic
- Accept only assertions listed in `dynamic_assertion_refs`.
- Confirm relation-specific `CONDITIONS` behavior.
- Resolve the versioned adapter for semantic `CHALLENGES`.
- Preserve changed, unchanged-with-reason, blocked and Human Stop outcomes.

### Product and domain review
- Review the nine Buyout workstreams and question families.
- Approve or revise the provisional Fund Lens shape.
- Create independent blind gold annotations before setting empirical thresholds.

## Boundary

This package defines the semantic layer immediately upstream of the frozen Dynamic. Existing machine contracts remain authoritative until an explicit versioned migration is accepted.
