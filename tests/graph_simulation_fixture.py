"""Synthetic graph used by engine, HTTP, transport and browser acceptance tests."""
import copy
import json
from pathlib import Path
from simulation_fixture import advanced_fixture, CASE_ID
from backend.dynamics.runtime.panta_transition_engine import build_runtime_state


def graph_fixture(case_id=CASE_ID):
    (case, graph, mapping), events = advanced_fixture(case_id)
    graph.update(schema_version='1.1.0', canonical_as_of='2026-09-05', case_positions=[], support_routes=[],
                 claim_position_edges=[], position_dependencies=[], position_model_bindings=[], artifacts=[])
    graph.setdefault('claims', [])
    for identity, statement, usable in [
        ('CUSTOMER-CALL', 'Customer interviews indicate renewal intent', True),
        ('RENEWAL-RECORD', 'Renewal records independently support retention', True),
        ('CUSTOMER-LOSS', 'A customer may terminate its contract', False),
        ('ISOLATED-CLAIM', 'An unrelated operational observation', True),
    ]:
        graph['claims'].append(dict(claim_id=identity, statement=statement, usable=usable, institutional_state='CURRENT',
            period='FY2027', perimeter='Group', freshness_status='CURRENT', source_id='SYNTHETIC-EVIDENCE'))
    for identity, statement in [('RETENTION', 'The revenue base is durable'), ('DEBT-SERVICE', 'The case can support its financing')]:
        graph['case_positions'].append(dict(position_id=identity, statement=statement, criticality='critical',
            decision_status='ACCEPTED', freshness_status='CURRENT', institutional_state='CURRENT', period='FY2027', perimeter='Group'))
    graph['support_routes'] = [
        dict(route_id='INTERVIEW-PATH', label='Customer interview evidence', target_position_id='RETENTION',
             logic='AND_WITH_COUNTEREVIDENCE', member_claim_ids=['CUSTOMER-CALL'], counter_claim_ids=['CUSTOMER-LOSS']),
        dict(route_id='RECORD-PATH', label='Independent renewal records', target_position_id='RETENTION',
             logic='AND', member_claim_ids=['RENEWAL-RECORD']),
        dict(route_id='FINANCING-PATH', label='Durability and operating earnings', target_position_id='DEBT-SERVICE',
             logic='AND', member_position_ids=['RETENTION'], member_model_node_ids=['PROFIT']),
    ]
    graph['position_dependencies'] = [dict(edge_id='DURABILITY-FINANCING', from_position_id='RETENTION', to_position_id='DEBT-SERVICE', relation_type='CONDITIONS')]
    graph['decision_snapshot'] = dict(decision_id='DECISION-1', decision_status='APPROVED', actor_id='SYNTHETIC-HUMAN')
    graph['stated_positions'][0].update(actor_id='SYNTHETIC-HUMAN', institutional_state='CURRENT')
    mapping.update(mapping_version='SIMULATION-ACCEPTANCE-1', directed_model_edges=[], position_model_directions=[],
        rule_switches=[], inverse_solver_configs=[], model_controls=[], cyclic_component_solver_configs=[], coverage_limits=[])
    # Formula definitions and links are precisely those already admitted to this fixture.
    for formula in mapping['formulas']:
        if formula['formula_id'] == 'F-IRR':
            formula['expression_or_function_ref'] = 'UNAVAILABLE_RETURN_SOLVER(profit)'
        for source in formula['input_ids']:
            mapping['directed_model_edges'].append(dict(edge_id=f"{formula['formula_id']}:{source}", from_id=source, to_id=formula['output_id'], relation_type='DRIVES'))
    for event in events:
        event['trigger_claim_ids'] = []
    root = Path(__file__).resolve().parents[1] / 'backend' / 'dynamics' / 'benchmark'
    inputs = dict(current_graph=copy.deepcopy(graph), prior_state=build_runtime_state(graph), execution_mapping=copy.deepcopy(mapping),
        materiality_policy=json.loads((root / 'keystone_materiality_policy_v0.json').read_text()),
        authority_policy=json.loads((root / 'keystone_authority_matrix_v0.json').read_text()))
    events.append(dict(event_id='EVENT-CUSTOMER-WITHDRAWAL', case_id=case_id, event='SOURCE_CORRECTION', label='Customer interview evidence withdrawn',
        admission_mode='HUMAN_CONFIRMED', effective_date='2026-09-05', known_at='2026-09-05T10:00:00Z', recorded_at='2026-09-05T10:01:00Z',
        source_ids=['SYNTHETIC-EVIDENCE'], trigger_claim_ids=[], mutations=[dict(operation='RETRACT', object_type='CLAIM', object_id='CUSTOMER-CALL')]))
    return (case, graph, mapping), events, inputs
