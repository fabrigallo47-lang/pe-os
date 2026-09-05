"""Read-only graph counterfactuals executed by the real transition engine.

This module validates UI requests and projects runtime outputs. It owns no
support logic, financial formulas, materiality rules or settlement behavior.
"""
import copy
import json
from .simulation import SimulationError, digest, admitted
from .panta_transition_engine import (
    ENGINE_VERSION, apply_state_transition, build_runtime_state, compute_affected_set,
    normalize_event_batch, _object_registry, HUMAN_ONLY_FIELDS,
)

SCHEMA = 'graph-simulation/1.0'
KINDS = {'CLAIM': 'Evidence', 'POSITION': 'Case conclusion', 'MODEL_NODE': 'Model item',
         'SUPPORT_ROUTE': 'Evidence path', 'ARTIFACT': 'Work product', 'STATED_POSITION': 'Attributed human view'}
# Projection controls over existing runtime fields. Identity, provenance and
# authority fields cannot be rewritten through the hypothetical editor.
FIELDS = {
    'CLAIM': ('usable', 'value', 'statement', 'freshness_status', 'period', 'perimeter', 'unit', 'definition_id'),
    'POSITION': ('usable', 'statement', 'freshness_status', 'criticality'),
    'MODEL_NODE': ('value', 'usable', 'freshness_status', 'period', 'perimeter', 'unit', 'definition_id'),
    'SUPPORT_ROUTE': ('member_claim_ids', 'counter_claim_ids', 'member_position_ids', 'member_model_node_ids', 'logic'),
    'ARTIFACT': ('statement', 'text', 'freshness_status'),
}
FIELD_LABELS = {'usable': 'Usable as support', 'value': 'Value or assumption', 'statement': 'Statement',
    'text': 'Content', 'freshness_status': 'Freshness', 'criticality': 'Importance',
    'member_claim_ids': 'Supporting evidence', 'counter_claim_ids': 'Contrary evidence',
    'member_position_ids': 'Supporting conclusions', 'member_model_node_ids': 'Supporting model items',
    'logic': 'How this evidence is combined', 'period': 'Reporting period', 'perimeter': 'Scope', 'unit': 'Unit', 'definition_id': 'Definition reference'}
REFERENCE_KINDS = {'member_claim_ids': 'CLAIM', 'counter_claim_ids': 'CLAIM',
                   'member_position_ids': 'POSITION', 'member_model_node_ids': 'MODEL_NODE'}
RELATION_LABELS = {'SUPPORT_ROUTE_MEMBER': 'supports this evidence path', 'SUPPORT_ROUTE_COUNTEREVIDENCE': 'challenges this evidence path',
    'ROUTE_FOR_POSITION': 'supports this conclusion', 'SUPPORTS': 'supports', 'CONTRADICTS': 'contradicts',
    'CHALLENGES': 'challenges', 'DRIVES': 'affects', 'CONDITIONS': 'is a condition for', 'BEARS_ON': 'matters to', 'DERIVES_FROM': 'is a calculation input for'}
REASON_LABELS = {
    'MATERIALITY_POLICY_COVERAGE_UNPROVEN': 'The case has no complete rule for assessing the significance of this change. A reviewer must assess it before it could be adopted.',
    'APPROVED_FROZEN': 'The approved investment record stays fixed. A hypothetical cannot amend it.',
    'DECISION_REQUIRES_HUMAN': 'This change reaches an investment decision that requires an authorized human review.',
    'CONFLICTING_SUPPORT_EVIDENCE': 'Supporting and contrary evidence conflict. This path cannot establish a settled conclusion.',
    'STALE_UPSTREAM_BASIS': 'An input is no longer current, so this consequence cannot be established.',
    'PRIOR_VALUE_MISMATCH': 'The starting value differs from the value this change expected.',
    'CIRCULAR_SUPPORT': 'This evidence path depends on its own conclusion and cannot establish independent support.',
}


def label(entry):
    item = entry['object']
    return str(item.get('label') or item.get('name') or item.get('statement') or item.get(entry['id_field']))


def truth_states(output):
    return {**{r['route_id']: r['state'] for r in output['route_results']},
            **{r['position_id']: r['state'] for r in output['support_combination_results']}}


class GraphSimulation:
    def __init__(self, case_id, case_version, inputs):
        self.case_id, self.case_version = case_id, case_version
        if not isinstance(inputs, dict) or any(not isinstance(inputs.get(k), dict) for k in ('prior_state', 'execution_mapping', 'materiality_policy', 'authority_policy')):
            raise SimulationError('The current transition state, execution rules and policies are required.')
        self.inputs = copy.deepcopy(inputs)
        prior = self.inputs['prior_state']
        self.state = prior if 'current_graph' in prior else build_runtime_state(prior)
        self.graph = self.state['current_graph']
        if self.state['case_id'] != case_id or self.graph['case_id'] != case_id:
            raise SimulationError('The transition state belongs to another case.')
        self.mapping = self.inputs['execution_mapping']
        self.registry = _object_registry(copy.deepcopy(self.graph))
        self.version = digest(dict(schema=SCHEMA, engine=ENGINE_VERSION, case=case_id, caseVersion=case_version, inputs=self.inputs))
        self.as_of = str(self.graph.get('canonical_as_of') or '')[:10]
        if not self.as_of:
            raise SimulationError('The Current graph has no recorded effective date for this hypothetical.')
        self.catalog = self._catalog()

    def _catalog(self):
        objects = []
        for identity, entry in sorted(self.registry.items()):
            item, kind = entry['object'], entry['object_type']
            fields = []
            editable = admitted(item) and kind in FIELDS
            for field in FIELDS.get(kind, ()) if editable else ():
                # Optional usability/freshness fields are supported by the runtime;
                # absence is disclosed rather than silently stored as a baseline.
                if field not in item and field not in ('usable', 'freshness_status') and field not in REFERENCE_KINDS:
                    continue
                value = item.get(field)
                control = 'references' if field in REFERENCE_KINDS else 'boolean' if field == 'usable' else 'text'
                choices = None
                if field == 'freshness_status':
                    control, choices = 'choice', ['CURRENT', 'STALE', 'UNKNOWN']
                if field == 'logic':
                    control, choices = 'choice', ['AND', 'INDEPENDENT', 'AND_WITH_COUNTEREVIDENCE']
                    if value == 'FORMULA':
                        continue  # Formula routes keep their mapped execution rule.
                if field == 'criticality':
                    control, choices = 'choice', ['critical', 'important', 'contextual']
                fields.append(dict(id=field, label=FIELD_LABELS[field], value=value, control=control,
                    choices=choices, referenceKind=REFERENCE_KINDS.get(field)))
            objects.append(dict(id=identity, label=label(entry), kind=kind, kindLabel=KINDS[kind], fields=fields,
                canRetract=editable and kind != 'ARTIFACT',
                limitation=None if editable else 'Attributed human views and non-current objects cannot be rewritten by a hypothetical.',
                current=copy.deepcopy(item), currentFlags=copy.deepcopy(self.state.get('runtime_flags', {}).get(identity, {}))))
        return objects

    def scope(self):
        reach = compute_affected_set(self.graph, [], self.mapping)
        return dict(schemaVersion=SCHEMA, version=self.version, engineVersion=ENGINE_VERSION,
            caseId=self.case_id, caseVersion=self.case_version, asOf=self.as_of, objects=self.catalog,
            notes=['Qualitative and quantitative changes use the same transition engine as the live case.',
                   'Human views and recorded decisions retain their original attribution and authority.',
                   'Only executable relationships propagate; missing logic remains an explicit limitation.'],
            coverageLimits=reach['coverage_limits'])

    def _manual_mutations(self, mutations):
        if not isinstance(mutations, list) or not 1 <= len(mutations) <= 50:
            raise SimulationError('Supply between one and fifty changes.')
        if len(json.dumps(mutations, allow_nan=False)) > 100000:
            raise SimulationError('The hypothetical changes exceed the supported request size.')
        catalog = {o['id']: o for o in self.catalog}
        new_ids = {m.get('object_id') for m in mutations if isinstance(m, dict) and m.get('operation') == 'ADD' and isinstance(m.get('object_id'), str)}
        if len(new_ids) != sum(isinstance(m, dict) and m.get('operation') == 'ADD' for m in mutations):
            raise SimulationError('New evidence identities must be unique.')
        clean = []
        for mutation in mutations:
            if not isinstance(mutation, dict):
                raise SimulationError('Every change must be a structured mutation.')
            m = copy.deepcopy(mutation)
            if set(m) - {'operation', 'object_type', 'object_id', 'field', 'from', 'to', 'statement', 'relation_type', 'target_position_id', 'value'}:
                raise SimulationError('The hypothetical cannot supply identities, sources, policy overrides or authority metadata.')
            key, kind, operation = m.get('object_id'), m.get('object_type'), m.get('operation')
            if not all(isinstance(v, str) and v for v in (key, kind, operation)):
                raise SimulationError('Every change needs its object and operation.')
            if operation == 'ADD':
                if kind != 'CLAIM' or key in self.registry or not key.startswith('HYPOTHETICAL:') or len(key) > 160:
                    raise SimulationError('New hypothetical evidence needs a unique temporary identity.')
                target = self.registry.get(m.get('target_position_id')) if isinstance(m.get('target_position_id'), str) else None
                if not target or target['object_type'] != 'POSITION' or not admitted(target['object']) or m.get('relation_type') not in ('SUPPORTS', 'CONTRADICTS'):
                    raise SimulationError('Connect the hypothetical evidence to a current conclusion as supporting or contrary evidence.')
                if not isinstance(m.get('statement'), str) or not m['statement'].strip() or len(m['statement']) > 4000:
                    raise SimulationError('Describe the hypothetical evidence.')
                if set(m) & {'field', 'from', 'to'}:
                    raise SimulationError('New evidence supplies a statement, not a field override.')
                # Context is inherited from the selected target, not guessed from prose.
                for field in ('period', 'perimeter', 'unit', 'definition_id'):
                    if target['object'].get(field) is not None:
                        m[field] = target['object'][field]
                clean.append(m)
                continue
            obj = catalog.get(key)
            if not obj or obj['kind'] != kind or kind == 'STATED_POSITION':
                raise SimulationError('Choose a current object that supports this change.')
            if set(m) & {'statement', 'relation_type', 'target_position_id', 'value'}:
                raise SimulationError('Update the selected object through its declared field.')
            if operation == 'RETRACT':
                if not obj['canRetract'] or set(m) - {'operation', 'object_type', 'object_id'}:
                    raise SimulationError('This object cannot be withdrawn by this hypothetical.')
            elif operation in ('CORRECT', 'OBSERVE', 'SUPERSEDE'):
                field = next((f for f in obj['fields'] if f['id'] == m.get('field')), None)
                if not field or m.get('field') in HUMAN_ONLY_FIELDS or 'to' not in m:
                    raise SimulationError('Choose a declared mutable field. Historical and human-decision fields are protected.')
                value = m['to']
                if field['control'] == 'boolean' and not isinstance(value, bool):
                    raise SimulationError('Choose whether this item is usable as support.')
                if field['control'] == 'choice' and value not in field['choices']:
                    raise SimulationError('Choose one of the supported field values.')
                if field['control'] == 'references':
                    if not isinstance(value, list) or any(not isinstance(v, str) for v in value) or len(value) != len(set(value)):
                        raise SimulationError('Evidence connections must be unique object references.')
                    if any((v not in self.registry or self.registry[v]['object_type'] != field['referenceKind'] or not admitted(self.registry[v]['object'])) and not (v in new_ids and field['referenceKind'] == 'CLAIM') for v in value):
                        raise SimulationError('Connect only current objects or evidence added in this hypothetical.')
                if field['control'] == 'text' and (isinstance(value, (list, dict, bool)) or value is not None and not isinstance(value, (str, int, float))):
                    raise SimulationError('Supply a text or numeric value.')
                if isinstance(value, str) and len(value) > 4000:
                    raise SimulationError('The hypothetical value is too long.')
                # A caller may pin an explicit from value; runtime mismatch stops
                # remain visible. Otherwise pin exactly the Current value displayed.
                m.setdefault('from', self.registry[key]['object'].get(m['field']))
            else:
                raise SimulationError('This operation is not supported by the transition contract.')
            clean.append(m)
        return clean

    def manual_event(self, mutations):
        clean = self._manual_mutations(mutations)
        return dict(event_id='SIMULATION:' + digest(dict(scope=self.version, mutations=clean))[7:], event='HYPOTHETICAL_CASE_CHANGE',
            effective_date=self.as_of, known_at=self.as_of + 'T00:00:00Z', source_ids=['HYPOTHETICAL-USER-INPUT'], trigger_claim_ids=[], mutations=clean)

    def transition(self, events):
        return apply_state_transition(copy.deepcopy(self.state), copy.deepcopy(events), copy.deepcopy(self.mapping),
            copy.deepcopy(self.inputs['materiality_policy']), copy.deepcopy(self.inputs['authority_policy']))

    def run(self, request, event=None):
        if request.get('graphVersion') != self.version or request.get('caseVersion') != self.case_version:
            raise SimulationError('The case, graph or policies changed. Refresh before simulating.')
        description = request.get('assumption') if event is None else None
        if description is not None and (not isinstance(description, str) or len(description) > 6000):
            raise SimulationError('The scenario description exceeds the supported size.')
        envelope = copy.deepcopy(event) if event is not None else self.manual_event(request.get('mutations'))
        if envelope.get('case_id', self.case_id) != self.case_id:
            raise SimulationError('This event belongs to a different case.')
        normalize_event_batch([envelope])
        result = self.transition([envelope])
        baseline_event = dict(event_id='SIMULATION-BASELINE:' + self.version, event='Evaluate current graph',
            effective_date=self.as_of, known_at=self.as_of + 'T00:00:00Z', source_ids=[], trigger_claim_ids=list(self.registry), mutations=[])
        baseline = self.transition([baseline_event])
        report = self._report(result, baseline)
        wording_ids = sorted({m['object_id'] for m in envelope.get('mutations', []) if m.get('field') in ('statement', 'text')})
        if wording_ids:
            report['issues'].append(dict(category='Coverage limitation', objectIds=wording_ids,
                reason='The wording is changed as supplied. Its meaning is not converted into new evidence connections or assumptions; specify those changes explicitly.',
                raw=dict(reason_code='NO_IMPLICIT_SEMANTIC_REINTERPRETATION', scope_ids=wording_ids)))
        route_claims = {identity for route in result['candidate_state']['current_graph'].get('support_routes', []) for field in ('member_claim_ids', 'counter_claim_ids') for identity in route.get(field, [])}
        unbound = sorted({m['object_id'] for m in envelope.get('mutations', []) if m.get('operation') == 'ADD' and m.get('object_type') == 'CLAIM' and m['object_id'] not in route_claims})
        if unbound:
            report['issues'].append(dict(category='Coverage limitation', objectIds=unbound,
                reason='This evidence reaches the linked conclusion, but no declared evidence path uses it to calculate support. Add the appropriate connection to an evidence path to test that consequence.',
                raw=dict(reason_code='NO_DECLARED_SUPPORT_ROUTE_MEMBERSHIP', scope_ids=unbound)))
        canonical = dict(mode='graph_event' if event is not None else 'graph', optionId='graph', originObjectId='graph',
            assumption=description or envelope.get('label') or envelope['event'], caseVersion=self.case_version, graphVersion=self.version)
        if event is not None:
            canonical.update(eventId=envelope['event_id'], eventHash=digest(envelope))
        else:
            canonical['mutations'] = copy.deepcopy(request['mutations'])
        response = dict(id=digest(dict(scope=self.version, event=envelope, description=canonical['assumption'])), schemaVersion='simulation/1.0', caseId=self.case_id,
            caseVersion=self.case_version, request=canonical, liveCaseUnchanged=True, effects=[], limits=[],
            coverage=dict(examinedCount=0, changedCount=0, heldCount=0, unmappedCount=0), graph=report)
        report.update(schemaVersion=SCHEMA, version=self.version, engineVersion=ENGINE_VERSION,
            event=envelope, engineResult=result, baselineSupport=truth_states(baseline['transition_output']),
            currentGraph=copy.deepcopy(self.graph), currentFlags=copy.deepcopy(self.state.get('runtime_flags', {})))
        return response

    def _report(self, result, baseline):
        output = result['transition_output']
        candidate = result['candidate_state']
        after_registry = _object_registry(copy.deepcopy(candidate['current_graph']))
        before_truth, after_truth = truth_states(baseline['transition_output']), truth_states(output)
        issues = []
        for category, field in [('Review required', 'human_stops'), ('Propagation blocked', 'blocked_components'), ('Coverage limitation', 'coverage_limits')]:
            for raw in output[field]:
                ids = raw.get('scope_ids') or raw.get('member_ids') or [raw.get('object_or_component_id') or raw.get('object_id') or raw.get('component_id')]
                issues.append(dict(category=category, objectIds=[i for i in ids if i],
                    reason=REASON_LABELS.get(raw.get('reason_code')) or raw.get('reason') or raw.get('effect') or raw.get('details') or str(raw.get('reason_code', 'Runtime limitation')).replace('_', ' ').capitalize(), raw=raw))
        pending = {r['object_id'] for r in output['unchanged_objects'] if r['reason_code'] == 'REACHED_PENDING_EVALUATION'}
        pending.update(identity for component in output['ordered_transitions'] if component['result'] != 'SETTLED' for identity in component['member_ids'])
        affected = {i['object_id']: i for i in output['affected_set']}
        # Direct no-ops and semantic rejections may sit outside the affected set.
        for raw in output['unchanged_objects']:
            if raw['object_id'] in self.registry:
                affected.setdefault(raw['object_id'], dict(object_id=raw['object_id'], object_type=raw['object_type'], seed=False, reached_via=[]))
        rows = []
        for key, item in sorted(affected.items(), key=lambda pair: (not pair[1]['seed'], pair[0])):
            before = copy.deepcopy(self.registry.get(key, {}).get('object'))
            after = copy.deepcopy(after_registry.get(key, {}).get('object'))
            prior_flags = self.state.get('runtime_flags', {}).get(key, {})
            next_flags = candidate.get('runtime_flags', {}).get(key, {})
            changes = [dict(field=f, before=(before or {}).get(f), after=(after or {}).get(f)) for f in sorted(set(before or {}) | set(after or {})) if (before or {}).get(f) != (after or {}).get(f)]
            if prior_flags != next_flags:
                changes.append(dict(field='runtime_state', before=copy.deepcopy(prior_flags), after=copy.deepcopy(next_flags)))
            if key in after_truth and before_truth.get(key) != after_truth[key]:
                changes.append(dict(field='support_result', before=before_truth.get(key), after=after_truth[key]))
            reasons = [r['reason'] for r in output['unchanged_objects'] if r['object_id'] == key]
            unresolved = key in pending or after_truth.get(key) == 'UNKNOWN'
            rows.append(dict(id=key, label=label(after_registry.get(key) or self.registry[key]), kind=item['object_type'],
                kindLabel=KINDS.get(item['object_type'], 'Case item'), status='CHANGED' if changes else 'UNAVAILABLE' if unresolved else 'HELD', unresolved=unresolved,
                before=before, after=after, changes=changes, beforeSupport=before_truth.get(key), afterSupport=after_truth.get(key),
                isOrigin=item['seed'], reachedVia=item['reached_via'], reasons=reasons))
        reached = set(affected)
        witness_routes = {r['route_id'] for r in output['route_results'] if r['target_position_id'] in reached}
        edges = []
        for version, graph in [('CURRENT', self.graph), ('HYPOTHETICAL', candidate['current_graph'])]:
            adjacency = compute_affected_set(graph, [], self.mapping)['adjacency']
            for source, links in adjacency.items():
                for target, relation, eid in links:
                    if target in reached | witness_routes:
                        edges.append(dict(id=eid, source=source, target=target, relation=relation,
                            label=RELATION_LABELS.get(relation, 'affects through a declared relationship'), version=version))
        all_labels = {k: label(v) for k, v in {**self.registry, **after_registry}.items()}
        return dict(rows=rows, edges=edges, labels=all_labels, issues=issues,
            counts=dict(examined=len(rows), changed=sum(r['status'] == 'CHANGED' for r in rows), held=sum(r['status'] == 'HELD' for r in rows), unavailable=sum(r['unresolved'] for r in rows)),
            materiality=output['materiality_assessment'], governance=output['governance'])
