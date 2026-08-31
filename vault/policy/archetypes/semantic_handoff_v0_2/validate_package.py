from pathlib import Path
import json
import sys
import os
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent


def load_json(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def load_yaml(relative):
    return yaml.safe_load((ROOT / relative).read_text(encoding='utf-8'))


errors = []
format_checker = FormatChecker()

kernel = load_yaml('01_universal_investment_kernel_v0_2.yaml')
buyout = load_yaml('02_buyout_archetype_pack_v0_2.yaml')
fund_lens_schema = load_json('03_provisional_fund_lens_schema_v0_1.schema.json')
extraction_schema = load_json('04_semantic_extraction_contract_v0_2.schema.json')
event_schema = load_json('05_canonical_case_event_v0_2.schema.json')
relations = load_yaml('06_relation_update_contract_v0_2.yaml')
audit = load_yaml('07_archetype_lens_boundary_audit_v0_2.yaml')
benchmark = load_yaml('09_blind_benchmark_spec_v0_1.yaml')

for name, schema in [
    ('Fund Lens schema', fund_lens_schema),
    ('Extraction schema', extraction_schema),
    ('Canonical event schema', event_schema),
]:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        errors.append(f'{name}: invalid JSON Schema: {exc}')

validation_sets = [
    ('examples/provisional_fund_lens_empty.example.json', fund_lens_schema),
    ('examples/qualitative_call_extraction.json', extraction_schema),
    ('examples/quantitative_qoe_extraction.json', extraction_schema),
    ('examples/canonical_qualitative_event.json', event_schema),
    ('examples/canonical_quantitative_event.json', event_schema),
    ('examples/canonical_human_decision_event.json', event_schema),
]

for relative, schema in validation_sets:
    data = load_json(relative)
    validator = Draft202012Validator(schema, format_checker=format_checker)
    for error in validator.iter_errors(data):
        location = '/'.join(str(part) for part in error.absolute_path)
        errors.append(f'{relative}:{location}: {error.message}')

expected_hierarchy = [
    'Universal Investment Kernel',
    'Strategy Archetype Pack with transaction flags',
    'Provisional Fund Lens',
    'Deal Frame',
    'Live Case State and Execution Mapping',
]
if kernel['architecture']['hierarchy'] != expected_hierarchy:
    errors.append('Kernel hierarchy does not match the five-layer v0.2 hierarchy.')

if 'StatedPosition' not in kernel['object_types']:
    errors.append('Kernel is missing StatedPosition.')
if 'CaseReading' not in kernel['object_types']:
    errors.append('Kernel is missing CaseReading.')
if not kernel['object_types']['Decision']['human_boundary'].startswith('HUMAN_ONLY'):
    errors.append('Decision is not marked HUMAN_ONLY.')

expected_runtime = {'SUPPORTS', 'CONTRADICTS', 'DERIVES_FROM', 'DRIVES', 'CONDITIONS'}
actual_runtime = set(kernel['relation_families']['runtime_relations'])
if actual_runtime != expected_runtime:
    errors.append(f'Unexpected frozen runtime relation set: {sorted(actual_runtime)}')
if 'CHALLENGES' not in kernel['relation_families']['semantic_binding_non_traversal']:
    errors.append('CHALLENGES is not registered as semantic-only.')
if set(relations['relation_classes']['FROZEN_RUNTIME']) != expected_runtime:
    errors.append('Relation contract does not match the kernel frozen runtime set.')
if relations['relations']['CHALLENGES']['dynamic_effect'] != 'NONE_UNTIL_VERSIONED_ADAPTER':
    errors.append('CHALLENGES is not isolated from the Dynamic.')

if buyout['metadata']['status'] != 'PROVISIONAL_DOMAIN_ARCHETYPE':
    errors.append('Buyout Pack is not explicitly provisional.')
if buyout['metadata']['universality_status'] != 'NOT_YET_CROSS_FIRM_VALIDATED':
    errors.append('Buyout Pack universality status is missing.')
if len(buyout['workstreams']) != 9:
    errors.append(f"Expected 9 Buyout workstreams after layer separation, found {len(buyout['workstreams'])}.")
for workstream_id, workstream in buyout['workstreams'].items():
    for required in ['governing_question', 'question_families', 'universality_class', 'lens_contamination_risk', 'lens_controls']:
        if required not in workstream:
            errors.append(f'{workstream_id}: missing {required}')

if fund_lens_schema['properties']['schema_status'].get('const') != 'PROVISIONAL_SHAPE_ONLY':
    errors.append('Fund Lens schema is not marked provisional shape only.')
if audit['metadata']['status'] != 'PASS_WITH_PROVISIONAL_ARCHETYPE_STATUS':
    errors.append('Archetype/Lens audit status is unexpected.')
if benchmark['metadata']['status'] != 'PROTOCOL_READY_GOLD_NOT_INCLUDED':
    errors.append('Blind benchmark status is unexpected.')

# Canonical-event runtime filtering checks.
for relative in [
    'examples/canonical_qualitative_event.json',
    'examples/canonical_quantitative_event.json',
    'examples/canonical_human_decision_event.json',
]:
    event = load_json(relative)
    relation_by_id = {rel['relation_id']: rel for rel in event['relation_assertions']}
    for relation_id in event['semantic_only_relation_ids']:
        relation = relation_by_id.get(relation_id)
        if relation is None:
            errors.append(f'{relative}: semantic-only relation {relation_id} does not exist.')
        elif relation['runtime_traversal']:
            errors.append(f'{relative}: semantic-only relation {relation_id} has runtime traversal enabled.')
    for assertion_ref in event['dynamic_assertion_refs']:
        if assertion_ref in relation_by_id:
            relation = relation_by_id[assertion_ref]
            if relation['relation_class'] != 'RUNTIME' or relation['runtime_mapping_status'] != 'READY':
                errors.append(f'{relative}: {assertion_ref} is not a READY runtime relation.')
    for relation in event['relation_assertions']:
        if relation['relation_type'] == 'CHALLENGES':
            if relation['runtime_mapping_status'] != 'PENDING_ADAPTER' or relation['runtime_traversal']:
                errors.append(f'{relative}: CHALLENGES relation is not safely isolated.')
            if relation['relation_id'] in event['dynamic_assertion_refs']:
                errors.append(f'{relative}: CHALLENGES appears in Dynamic input.')

# Concept IDs must be unique.
concept_ids = [item['id'] for item in buyout['canonical_concepts']]
if len(concept_ids) != len(set(concept_ids)):
    errors.append('Duplicate canonical concept IDs.')

if errors:
    print('FAIL')
    for error in errors:
        print('-', error)
    sys.stdout.flush()
    os._exit(1)

print('PASS')
print('- three JSON Schemas are valid')
print('- six examples validate')
print('- five-layer hierarchy is exact')
print('- StatedPosition / CaseReading vocabulary is present')
print('- CHALLENGES is semantic-only and excluded from Dynamic input')
print('- provisional Fund Lens shape validates')
print('- Buyout Archetype / Fund Lens boundary checks pass')
print(f"- {len(kernel['object_types'])} kernel object types")
print(f"- {len(buyout['workstreams'])} Buyout workstreams")
print(f"- {len(buyout['canonical_concepts'])} canonical concept seeds")

sys.stdout.flush()
os._exit(0)
