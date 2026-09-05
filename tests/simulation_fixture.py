"""Fictional model data for the isolated simulation acceptance workspace."""
import copy

CASE_ID = 'SIMULATION-TEST'
ACTOR = {'actorId': 'SIM-REVIEWER', 'entitlements': ['READ_CASE']}


def fixture():
    def node(identity, label, value, form='DIRECT_INPUT', unit='EUR m'):
        return dict(model_node_id=identity, label=label, value=value, initial_value=value,
                    computational_form=form, unit=unit, period='FY2027', perimeter='Group',
                    institutional_state='CURRENT', freshness_status='CURRENT')
    nodes = [node('REVENUE', 'Revenue assumption', 100), node('COST', 'Operating costs', 60),
             node('DEBT', 'Net debt', 80), node('PROFIT', 'Operating earnings', 40, 'DIRECT_FORMULA'),
             node('LEVERAGE', 'Net debt / operating earnings', 2, 'DIRECT_FORMULA', 'x'),
             node('CAP', 'Capped distribution', 30, 'DIRECT_FORMULA'),
             node('IRR', 'Return with an unconfigured solver', 0.2, 'DIRECT_FORMULA', 'ratio')]
    def formula(identity, output, expression, **operands):
        return dict(formula_id=identity, output_id=output, input_ids=list(operands.values()),
                    operand_bindings=operands, expression_or_function_ref=expression,
                    evaluation_type='SAFE_DECIMAL_EXPRESSION', institutional_state='CURRENT',
                    description=expression)
    formulas = [formula('F-LEVERAGE', 'LEVERAGE', 'debt / profit', debt='DEBT', profit='PROFIT'),
                formula('F-PROFIT', 'PROFIT', 'revenue - cost', revenue='REVENUE', cost='COST'),
                formula('F-CAP', 'CAP', 'MIN(profit, 30)', profit='PROFIT'),
                {**formula('F-IRR', 'IRR', 'profit', profit='PROFIT'), 'evaluation_type': 'UNCONFIGURED_SOLVER'}]
    for n in nodes:
        f = next((f for f in formulas if f['output_id'] == n['model_node_id']), None)
        if f:
            n['formula_id'] = f['formula_id']
    graph = {'model_nodes': copy.deepcopy(nodes), 'stated_positions': [{'stated_position_id': 'HUMAN-1', 'statement': 'A fictional analyst view that must remain unchanged.'}],
             'decisions': [{'decision_id': 'DECISION-1', 'status': 'RECORDED'}]}
    mapping = {'model_nodes': copy.deepcopy(nodes), 'formulas': formulas}
    case = {key: [] for key in ('actors workstreams questions caseReadings claims sources sourceVersions metricDefinitions metricObservations quantities assumptions risks modelNodes unknowns humanPositions workItems artifacts artifactBlocks artifactDiffs events outcomes findings pendingReviews simulationOptions decisionPaths decisions conditions relations').split()}
    case.update(caseRef={'id': CASE_ID, 'name': 'Simulation acceptance · fictional model'}, caseVersion='SIM-CASE-1', asOf='2026-09-05',
                actors=[{'id': ACTOR['actorId'], 'type': 'PERSON', 'displayName': 'Test reviewer'}])
    case['workstreams'] = [dict(id='MODEL-WS', name='Operating model', currentCaseReadingId='MODEL-READING',
        questionIds=['MODEL-Q'], activeWorkItemIds=[], openUnknownIds=[])]
    case['questions'] = [dict(id='MODEL-Q', name='How sensitive are earnings and leverage to revenue?',
        workstreamId='MODEL-WS', currentCaseReadingId='MODEL-READING', questionStatus='OPEN',
        claimIds=[], workItemIds=[], openUnknownIds=[], chronologyEventIds=[])]
    case['caseReadings'] = [dict(id='MODEL-READING', questionId='MODEL-Q', text='The declared model links revenue to earnings and leverage.',
        institutionalState='CURRENT', epistemicStatus='UNEXAMINED', freshnessStatus='CURRENT', decisionLinkStatus='NO_DECISION',
        supportObjectIds=['REVENUE', 'PROFIT', 'LEVERAGE'], independentSupportObjectIds=[], unknownIds=[], relatedObjectIds=[])]
    return case, graph, mapping

PEER_ID = 'SIMULATION-PEER'


def advanced_fixture(case_id=CASE_ID):
    case, graph, mapping = fixture()
    case['caseRef'] = dict(id=case_id, name='Example A · fictional model' if case_id == CASE_ID else 'Example B · fictional model')
    case['caseVersion'] = case_id + '-V1'
    graph['case_id'] = mapping['case_id'] = case_id
    peer_values = dict(REVENUE=120, COST=90, DEBT=60, PROFIT=30, LEVERAGE=2, CAP=30, IRR=0.2)
    for collection in (graph['model_nodes'], mapping['model_nodes']):
        for n in collection:
            n.update(comparison_key='example-definition:' + n['model_node_id'], basis='REPORTED', currency='EUR', scenario='BASE')
            if case_id == PEER_ID:
                n['value'] = n['initial_value'] = peer_values[n['model_node_id']]
    events = []
    if case_id == CASE_ID:
        mutations = []
        for key, value in [('REVENUE', 90), ('COST', 65)]:
            claim = dict(claim_id='CLAIM-' + key, value=value, source_id='SOURCE-UPDATE', institutional_state='CURRENT',
                unit='EUR m', period='FY2027', perimeter='Group', basis='REPORTED', currency='EUR', scenario='BASE')
            graph.setdefault('claims', []).append(claim)
            case['claims'].append(dict(id=claim['claim_id'], label=f'Latest operating update: {key.lower()} {value} EUR m.',
                normalizedStatement=f'The admitted update reports {value} EUR m for {key.lower()}.', institutionalState='CURRENT'))
            mutations.append(dict(operation='ADD', object_type='CLAIM', object_id=claim['claim_id'], **claim))
            mapping.setdefault('simulation_event_rules', []).append(dict(rule_id='RULE-' + key, event_type='CLAIM_ADMISSION',
                claim_id=claim['claim_id'], input_id=key, institutional_state='CURRENT'))
        events.append(dict(event_id='EVENT-OPERATING-UPDATE', case_id=case_id, event='CLAIM_ADMISSION',
            label='Operating update: revenue down, costs up', admission_mode='HUMAN_CONFIRMED',
            known_at='2026-09-05T09:00:00Z', effective_date='2026-09-04', recorded_at='2026-09-05T09:01:00Z',
            source_ids=['SOURCE-UPDATE'], mutations=mutations))
    return (case, graph, mapping), events
