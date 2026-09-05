"""Read-only numeric counterfactuals over the admitted case's execution mapping.

Uses the transition runtime's Decimal formula evaluator. It never settles a
Candidate, grades a human view, or derives a financial formula from prose.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext

from .panta_transition_engine import _execute_formula

SCHEMA = 'simulation/1.0'
EXECUTABLE = {'ARITHMETIC', 'SAFE_DECIMAL_EXPRESSION'}
ADMITTED = {'CURRENT', 'APPROVED'}


class SimulationError(ValueError):
    pass


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    text = str(value).strip()
    if len(text) > 256 or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', text):
        return None
    try:
        result = Decimal(text)
        return result if result.is_finite() and abs(result) <= Decimal('1e30') and (result == 0 or result.adjusted() >= -100) else None
    except (InvalidOperation, ValueError):
        return None


def admitted(item):
    # Membership in the server's Current is authoritative for legacy objects
    # without an explicit state. An explicit candidate can never override it.
    state = item.get('institutional_state', item.get('institutionalState'))
    return state is None or str(state).upper() in ADMITTED


def _index(items, field):
    result = {}
    for item in items:
        identity = item.get(field)
        if not isinstance(identity, str) or not identity or identity in result:
            raise SimulationError('The model contains missing or duplicate identities.')
        result[identity] = copy.deepcopy(item)
    return result


def _formula_error(formula, nodes):
    if not admitted(formula):
        return 'This calculation has not been admitted to the case.'
    if formula.get('evaluation_type') not in EXECUTABLE:
        return 'This calculation needs a runtime that is not available in this simulation.'
    inputs = formula.get('input_ids', [])
    bindings = formula.get('operand_bindings') or formula.get('variable_binding') or {}
    if not isinstance(inputs, list) or not isinstance(bindings, dict):
        return 'The calculation does not declare its inputs unambiguously.'
    if any(not isinstance(i, str) or i not in nodes for i in inputs):
        return 'A calculation input is absent from the admitted case.'
    if any(not isinstance(i, str) for i in bindings.values()) or set(bindings.values()) != set(inputs):
        return 'The calculation does not bind every declared input explicitly.'
    expression = formula.get('expression_or_function_ref')
    if not isinstance(expression, str) or len(expression) > 4096:
        return 'The calculation has no supported expression.'
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError):
        return 'The calculation expression could not be read.'
    parts = list(ast.walk(tree))
    if len(parts) > 256 or any(isinstance(p, ast.Pow) for p in parts):
        return 'This calculation exceeds the bounded arithmetic supported here.'
    allowed_calls = {'min', 'max', 'abs', 'sum', 'if', 'IF', 'MIN', 'MAX', 'ABS', 'SUM'}
    calls = {p.func.id for p in parts if isinstance(p, ast.Call) and isinstance(p.func, ast.Name)}
    if not calls <= allowed_calls or any(isinstance(p, (ast.Attribute, ast.Subscript, ast.Lambda)) for p in parts):
        return 'The calculation uses unsupported operations.'
    names = {p.id for p in parts if isinstance(p, ast.Name)} - calls
    parameters = formula.get('fixture_parameters') or {}
    if not isinstance(parameters, dict) or any(number(v) is None for v in parameters.values()):
        return 'A declared calculation parameter is not a finite number.'
    if set(parameters) & set(bindings) or names != set(bindings) | set(parameters):
        return 'The calculation has missing or conflicting operand identities.'
    formula['operand_bindings'] = bindings
    return None


class SimulationModel:
    def __init__(self, case_id, case_version, graph, mapping):
        self.case_id = case_id
        self.case_version = case_version
        self.mapping = copy.deepcopy(mapping)
        self.version = digest({'schema': SCHEMA, 'case': case_id, 'version': case_version, 'graph': graph, 'mapping': mapping})
        raw = _index(graph.get('model_nodes', []), 'model_node_id')
        mapped = _index(mapping.get('model_nodes', []), 'model_node_id')
        self.nodes = {key: {**mapped.get(key, {}), **node} for key, node in raw.items()
                      if admitted(node) and admitted(mapped.get(key, {}))}
        self.errors = {}
        self.notes = []
        # Current values are never taken from an old mapping's initial_value.
        for key, node in self.nodes.items():
            if key not in mapped:
                self.errors[key] = 'This current model item has no execution mapping.'
            if any(not node.get(field) or str(node[field]).upper().startswith(('UNSPECIFIED', 'UNKNOWN')) for field in ('unit', 'period', 'perimeter')):
                self.errors[key] = 'Specify unit, period and scope before calculating this item.'
            node['value'] = raw[key].get('value')
        self.formulas = _index(mapping.get('formulas', []), 'formula_id')
        self.by_output = {}
        self.dependencies = {key: set() for key in self.nodes}
        self.relations = []
        for fid, formula in sorted(self.formulas.items()):
            output = formula.get('output_id')
            if output not in self.nodes:
                continue
            if output in self.by_output:
                raise SimulationError('More than one calculation owns the same model output.')
            self.by_output[output] = formula
            error = _formula_error(formula, self.nodes)
            if error:
                self.errors[output] = error
            # A rejected/candidate formula cannot even be a traversal path.
            if not admitted(formula):
                continue
            for source in formula.get('input_ids', []):
                if isinstance(source, str) and source in self.nodes:
                    self.dependencies[output].add(source)
                    self.relations.append(dict(id=f'{fid}:{source}:{output}', caseId=case_id,
                        sourceObjectId=source, sourceObjectType='ModelNode', targetObjectId=output,
                        targetObjectType='ModelNode', type='DRIVES', institutionalState='CURRENT',
                        contractVersion=SCHEMA, rationale=formula.get('description') or 'Declared model calculation.'))
        for key, node in self.nodes.items():
            if node.get('freshness_status', 'CURRENT') not in ('CURRENT', 'current'):
                self.errors[key] = 'The current value needs review before it can be simulated.'
            if number(node.get('value')) is None:
                self.errors[key] = 'The current case has no finite numeric value for this item.'
            if key not in self.by_output and node.get('computational_form') not in ('INPUT', 'DIRECT_INPUT'):
                self.errors[key] = 'No executable calculation is mapped for this model item.'
            if node.get('coverage_limits'):
                self.errors[key] = 'The admitted model declares unresolved calculation coverage for this item.'
        for limit in [*graph.get('coverage_limits', []), *mapping.get('coverage_limits', [])]:
            if not isinstance(limit, dict):
                continue
            targets = set(limit.get('scope_ids') or [])
            target = limit.get('model_node_id') or limit.get('output_id') or limit.get('node_id')
            if target:
                targets.add(target)
            reason = str(limit.get('effect') or limit.get('reason') or limit.get('message') or 'The model declares an unresolved coverage limit.')
            for target in targets & self.nodes.keys():
                self.errors[target] = reason
            if not targets & self.nodes.keys():
                self.notes.append(reason)
        self.baseline, baseline_errors = self.evaluate({})
        self.errors.update(baseline_errors)
        # Reproducing Current is a precondition, not an implicit baseline repair.
        for key, value in self.baseline.items():
            recorded = number(self.nodes[key].get('value'))
            if recorded is not None and abs(value - recorded) > max(Decimal('1e-9'), abs(recorded) * Decimal('1e-9')):
                self.errors[key] = 'Recalculation does not reproduce the recorded current value. Review the model first.'
        self.baseline, baseline_errors = self.evaluate({})
        self.errors.update(baseline_errors)

    def evaluate(self, overrides):
        values = {}
        errors = dict(self.errors)
        pending = set(self.nodes)
        for key in list(pending):
            if key not in self.by_output:
                value = number(overrides.get(key, self.nodes[key].get('value')))
                if key not in errors and value is not None:
                    values[key] = value
                pending.remove(key)
        while pending:
            progressed = False
            for key in sorted(pending):
                if key in errors:
                    pending.remove(key); progressed = True; continue
                deps = self.dependencies[key]
                if deps & pending:
                    continue
                if any(d not in values for d in deps):
                    errors[key] = 'A required input could not be calculated.'
                else:
                    registry = {k: {'object': {'value': str(values[k])}} for k in deps}
                    try:
                        with localcontext() as context:
                            context.prec = 28
                            raw, error = _execute_formula(self.by_output[key], registry)
                        value = number(raw)
                    except (ArithmeticError, ValueError, TypeError, RecursionError):
                        error, value = 'FORMULA_EVALUATION_FAILED', None
                    if error or value is None:
                        errors[key] = 'The calculation could not produce a finite number for these inputs.'
                    else:
                        values[key] = value
                pending.remove(key); progressed = True
            if not progressed:
                for key in pending:
                    errors[key] = 'A circular or unresolved dependency needs a declared solver.'
                break
        return values, errors

    def closure(self, origin):
        reached = {origin}
        while True:
            next_ids = {key for key, deps in self.dependencies.items() if deps & reached}
            if next_ids <= reached:
                return reached
            reached |= next_ids

    def scope(self):
        options = []
        for key, node in sorted(self.nodes.items()):
            if key in self.by_output or node.get('computational_form') not in ('INPUT', 'DIRECT_INPUT'):
                continue
            reason = self.errors.get(key)
            if not reason and any(not node.get(field) for field in ('unit', 'period', 'perimeter')):
                reason = 'Specify unit, period and scope before testing this input.'
            downstream = self.closure(key) - {key}
            covered = sorted(i for i in downstream if i not in self.errors)
            if not reason and not covered:
                reason = 'No downstream calculation is executable from this input.'
            options.append(dict(id=key, originObjectId=key, label=node.get('label') or node.get('name') or key,
                assumption='Change this input within the declared model.', enabled=not reason, disabledReason=reason,
                input=dict(value=str(self.baseline[key]) if key in self.baseline else None,
                           unit=node.get('unit'), period=node.get('period'), scope=node.get('perimeter')),
                scope=dict(coveredObjectIds=covered, limitedObjectIds=sorted(downstream - set(covered)))))
        limits = [dict(objectId=key, label=self.nodes[key].get('label') or key, reason=reason) for key, reason in sorted(self.errors.items())]
        return dict(schemaVersion=SCHEMA, version=self.version, caseId=self.case_id, caseVersion=self.case_version,
            modelNodeCount=len(self.nodes), computableCount=len(self.baseline), limits=limits, options=options,
            notes=sorted(set(self.notes)))

    def run(self, request):
        if request.get('scopeVersion') != self.version or request.get('caseVersion') != self.case_version:
            raise SimulationError('The case or model changed. Refresh before running the simulation.')
        option = next((o for o in self.scope()['options'] if o['id'] == request.get('optionId')), None)
        if not option or request.get('originObjectId') != option['originObjectId']:
            raise SimulationError('Choose an input from this case’s declared simulation scope.')
        if not option['enabled']:
            raise SimulationError(option['disabledReason'])
        value = number(request.get('value'))
        if value is None:
            raise SimulationError('Enter a finite numeric input within the supported range.')
        key = option['originObjectId']
        canonical_request = dict(optionId=option['id'], originObjectId=key,
            assumption=f"{option['label']}: {option['input']['value']} → {value} {option['input']['unit']}",
            value=str(value), caseVersion=self.case_version, scopeVersion=self.version)
        return self.run_overrides({key: value}, canonical_request)

    def run_overrides(self, overrides, canonical_request):
        """Server-only atomic scenario; the HTTP caller cannot supply this mapping."""
        enabled = {o['id'] for o in self.scope()['options'] if o['enabled']}
        if not overrides or set(overrides) - enabled or any(number(v) is None for v in overrides.values()):
            raise SimulationError('Every scenario change must address an available numeric input.')
        values, errors = self.evaluate(overrides)
        reached = set().union(*(self.closure(key) for key in overrides))
        effects, limits = [], []
        ordered = sorted(overrides)
        remaining = reached - set(overrides)
        while remaining:
            ready = sorted(i for i in remaining if not (self.dependencies[i] & remaining))
            if not ready:
                ready = sorted(remaining)  # Cycles are disclosed limits, never calculations.
            ordered.extend(ready)
            remaining -= set(ready)
        for identity in ordered:
            node = self.nodes[identity]
            if identity in errors or identity not in self.baseline or identity not in values:
                limits.append(dict(objectId=identity, label=node.get('label') or identity,
                                   reason=errors.get(identity, 'No comparable baseline value is available.')))
                continue
            before, after = self.baseline[identity], values[identity]
            delta = after - before
            unit = node.get('unit') or ''
            effects.append(dict(objectId=identity, objectLabel=node.get('label') or identity,
                state='HOLDS' if delta == 0 else 'CHANGES', before=f'{before:.8g} {unit}'.strip(), after=f'{after:.8g} {unit}'.strip(),
                explanation='Hypothetical input supplied for this test.' if identity in overrides else None,
                reasonRelationIds=[r['id'] for r in self.relations if r['targetObjectId'] == identity],
                magnitude=dict(before=str(before), after=str(after), delta=str(delta), unit=unit,
                               percent=None if before == 0 else str(delta / abs(before) * 100))))
        changed = sum(e['state'] != 'HOLDS' for e in effects)
        return dict(id=digest(canonical_request), schemaVersion=SCHEMA, caseId=self.case_id,
            caseVersion=self.case_version, scopeVersion=self.version, request=canonical_request,
            effects=effects, limits=limits, coverage=dict(examinedCount=len(reached), changedCount=changed,
                heldCount=len(effects)-changed, unmappedCount=len(limits)), liveCaseUnchanged=True)
