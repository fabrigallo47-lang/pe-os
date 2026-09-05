"""Deterministic scenario projection from admitted ledger evidence.

Rules copy a specifically identified claim's value into a specifically identified
model input. They do not infer an economic shock from an event's prose.
"""
from .simulation import SimulationError, admitted, digest, number
from .ledger_store import ADMISSION_MODES


def event_scenarios(model, graph, events):
    rules = model.mapping.get('simulation_event_rules') or []
    rule_ids = [r.get('rule_id') for r in rules]
    if any(not isinstance(i, str) or not i for i in rule_ids) or len(set(rule_ids)) != len(rule_ids):
        raise SimulationError('Event rules need unique identities.')
    event_ids = [e.get('event_id') for e in events]
    if len(set(event_ids)) != len(event_ids):
        raise SimulationError('The event ledger contains duplicate identities.')
    claims = {c.get('claim_id'): c for c in graph.get('claims', []) if admitted(c)}
    results, limits = [], []
    for event in events:
        if event.get('case_id', model.case_id) != model.case_id or event.get('admission_mode') not in ADMISSION_MODES or not admitted(event):
            continue
        eid = event.get('event_id')
        if not eid or not event.get('known_at') or not event.get('source_ids'):
            continue
        matched, overrides, applied, reasons = False, {}, [], []
        for rule in rules:
            if rule.get('institutional_state') not in ('CURRENT', 'APPROVED') or rule.get('event_type') != event.get('event'):
                continue
            mutations = [m for m in event.get('mutations', []) if m.get('object_id') == rule.get('claim_id') and m.get('object_type') == 'CLAIM']
            if not mutations:
                continue
            matched = True
            key, claim_id = rule.get('input_id'), rule.get('claim_id')
            claim, node = claims.get(claim_id), model.nodes.get(key)
            if len(mutations) != 1 or not claim or not node:
                reasons.append('A unique admitted claim and model input are required.')
                continue
            mutation = mutations[0]
            # The value must be carried explicitly by this evidence event.
            raw = mutation.get('to') if mutation.get('field', 'value') == 'value' and 'to' in mutation else mutation.get('value') if mutation.get('operation') == 'ADD' else None
            value = number(raw)
            if mutation.get('operation') not in ('ADD', 'UPDATE') or mutation.get('field', 'value') != 'value' or value is None or any(item.get('bound') not in (None, 'EQ', 'EXACT', 'POINT') for item in (claim, mutation)):
                reasons.append('The mapped event has no point value that can be applied.')
                continue
            if claim.get('source_id') not in event['source_ids']:
                reasons.append('The admitted claim does not resolve to this event’s sources.')
                continue
            if any(not mutation.get(dim) or mutation.get(dim) != node.get(dim) for dim in ('unit', 'period', 'perimeter', 'basis', 'currency', 'scenario')):
                reasons.append('The event value and model input have different or missing dimensions.')
                continue
            if key in overrides and overrides[key] != value:
                reasons.append('The event gives conflicting values for the same model input.')
                continue
            overrides[key] = value
            applied.append(dict(ruleId=rule['rule_id'], claimId=claim_id, inputId=key, value=str(value), sourceId=claim['source_id']))
        if not matched:
            continue
        provenance = dict(eventId=eid, eventHash=digest(event), label=event.get('label') or event.get('event') or eid,
            knownAt=event['known_at'], effectiveAt=event.get('effective_date'), recordedAt=event.get('recorded_at'),
            sourceIds=event['source_ids'], changes=applied, basis='CURRENT_CASE')
        if not reasons:
            key = sorted(overrides)[0]
            request = dict(mode='event', optionId=key, originObjectId=key, value=str(overrides[key]),
                assumption=provenance['label'], caseVersion=model.case_version, scopeVersion=model.version,
                scenarioId=digest(dict(event=event, rules=rules, scope=model.version)))
            try:
                result = model.run_overrides(overrides, request)
                result['event'] = provenance
                result['id'] = request['scenarioId']
                results.append(result)
            except SimulationError as exc:
                reasons.append(str(exc))
        if reasons:
            limits.append(dict(eventId=eid, label=provenance['label'], reason=' '.join(sorted(set(reasons)))))
    return results, limits
