"""Bounded inverse questions and explicitly comparable model sensitivities.

No sampled curve is treated as proof of continuity or uniqueness. Interval
arithmetic certifies a strictly monotone, continuous path before bisection.
"""
import ast
from decimal import Decimal, localcontext, ROUND_FLOOR, ROUND_CEILING

from .simulation import SimulationError, digest, number


def interval_op(a, b, operation):
    bounds = []
    for rounding in (ROUND_FLOOR, ROUND_CEILING):
        with localcontext() as context:
            context.prec = 50
            context.rounding = rounding
            bounds.extend(operation(x, y) for x in a for y in b)
    return min(bounds), max(bounds)


def add(a, b):
    return interval_op(a, b, lambda x, y: x + y)


def neg(a):
    return a[1].copy_negate(), a[0].copy_negate()


def mul(a, b):
    return interval_op(a, b, lambda x, y: x * y)


def div(a, b):
    if b[0] <= 0 <= b[1]:
        raise SimulationError('The search interval crosses a possible division by zero. Narrow the bounds.')
    return interval_op(a, b, lambda x, y: x / y)


ZERO = (Decimal(0), Decimal(0))
ONE = (Decimal(1), Decimal(1))


def certify(model, input_id, output_id, lower, upper):
    cache, visiting = {}, set()

    def item(identity):
        if identity in cache:
            return cache[identity]
        if identity in visiting or identity in model.errors:
            raise SimulationError('A calculation on this path is unavailable.')
        if identity == input_id:
            return (lower, upper), ONE
        if identity not in model.by_output:
            v = model.baseline[identity]
            return (v, v), ZERO
        visiting.add(identity)
        formula = model.by_output[identity]
        env = {name: item(ref) for name, ref in formula['operand_bindings'].items()}
        env.update({name: ((number(v), number(v)), ZERO) for name, v in (formula.get('fixture_parameters') or {}).items()})
        result = expression(ast.parse(formula['expression_or_function_ref'], mode='eval').body, env)
        visiting.remove(identity)
        cache[identity] = result
        return result

    def expression(node, env):
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, ast.Constant) and number(node.value) is not None:
            v = number(node.value)
            return (v, v), ZERO
        if isinstance(node, ast.UnaryOp):
            v, d = expression(node.operand, env)
            if isinstance(node.op, ast.USub):
                return neg(v), neg(d)
            if isinstance(node.op, ast.UAdd):
                return v, d
        if isinstance(node, ast.BinOp):
            a, da = expression(node.left, env)
            b, db = expression(node.right, env)
            if isinstance(node.op, ast.Add):
                return add(a, b), add(da, db)
            if isinstance(node.op, ast.Sub):
                return add(a, neg(b)), add(da, neg(db))
            if isinstance(node.op, ast.Mult):
                return mul(a, b), add(mul(da, b), mul(a, db))
            if isinstance(node.op, ast.Div):
                return div(a, b), div(add(mul(da, b), neg(mul(a, db))), mul(b, b))
        # Piecewise expressions remain valid for forward tests, but this V1
        # solver does not claim a unique inverse through a branch or plateau.
        raise SimulationError('This path cannot be certified as continuous and strictly monotone. Use a forward test or a simpler output.')

    _, derivative = item(output_id)
    if derivative[0] > 0:
        return 'INCREASING'
    if derivative[1] < 0:
        return 'DECREASING'
    raise SimulationError('The model does not establish a unique threshold over these bounds. Narrow the interval or choose another output.')


def inverse(model, request):
    # Reuse all scope, authorization-independent input and freshness checks.
    base = model.run({**request, 'value': next((o['input']['value'] for o in model.scope()['options'] if o['id'] == request.get('optionId')), None)})
    query = request.get('inverse')
    if not isinstance(query, dict) or set(query) != {'outputId', 'target', 'lower', 'upper'}:
        raise SimulationError('Supply an output, target and two search bounds.')
    key, output = request['optionId'], query['outputId']
    if not isinstance(output, str) or output == key or output not in model.closure(key) or output not in model.baseline:
        raise SimulationError('Choose an available downstream output from this input.')
    lower, upper, target = (number(query[k]) for k in ('lower', 'upper', 'target'))
    if lower is None or upper is None or target is None or lower >= upper:
        raise SimulationError('Enter finite bounds with the lower bound below the upper bound.')
    canonical = {**base['request'], 'mode': 'inverse', 'inverse': {k: str(v) for k, v in query.items()}}
    base.update(request=canonical, effects=[], limits=[], coverage=dict(examinedCount=0, changedCount=0, heldCount=0, unmappedCount=0))
    outcome = dict(outputId=output, target=str(target), lower=str(lower), upper=str(upper), status='UNSUPPORTED', iterations=0)
    base['inverse'] = outcome
    try:
        direction = certify(model, key, output, lower, upper)
    except (SimulationError, ArithmeticError, KeyError, RecursionError) as exc:
        outcome['reason'] = str(exc) if isinstance(exc, SimulationError) else 'This interval cannot be calculated reliably.'
        base['id'] = digest(base)
        return base

    def evaluate(value):
        values, errors = model.evaluate({key: value})
        if output in errors or output not in values:
            raise SimulationError('The output cannot be calculated inside this interval.')
        return values[output]

    try:
        lo_value, hi_value = evaluate(lower), evaluate(upper)
        outcome.update(direction=direction, outputAtLower=str(lo_value), outputAtUpper=str(hi_value))
        if not min(lo_value, hi_value) <= target <= max(lo_value, hi_value):
            outcome.update(status='UNREACHABLE', reason='The target is outside the output range for these bounds.')
        else:
            tolerance = max(Decimal('1e-9'), abs(target) * Decimal('1e-9'))
            lo, hi = lower, upper
            solved = None
            # Endpoint roots count, but an interval with a discontinuity never does.
            for candidate in (lo, hi):
                if abs(evaluate(candidate) - target) <= tolerance:
                    solved = candidate
                    break
            for iteration in range(160):
                if solved is not None:
                    break
                candidate = (lo + hi) / 2
                actual = evaluate(candidate)
                outcome['iterations'] = iteration + 1
                if abs(actual - target) <= tolerance:
                    solved = candidate
                    break
                if (actual < target) == (direction == 'INCREASING'):
                    lo = candidate
                else:
                    hi = candidate
            if solved is None:
                outcome.update(status='NON_CONVERGENT', reason='No value met the output tolerance within 160 iterations.')
            else:
                result = model.run({**request, 'value': str(solved)})
                actual = evaluate(solved)
                outcome.update(status='FOUND', inputValue=str(solved), actual=str(actual), residual=str(actual-target), tolerance=str(tolerance))
                result.update(request={**result['request'], 'mode': 'inverse', 'inverse': canonical['inverse']}, inverse=outcome)
                base = result
    except SimulationError as exc:
        outcome.update(status='UNSUPPORTED', reason=str(exc))
    base['id'] = digest(base)
    return base


DIMENSIONS = ('comparison_key', 'unit', 'currency', 'period', 'perimeter', 'basis', 'scenario')


def comparison_identity(node):
    # Explicit shared definition identity, never matching labels or local IDs.
    values = tuple(node.get(k) for k in DIMENSIONS)
    return values if all(isinstance(v, str) and v.strip() and not v.upper().startswith(('UNKNOWN', 'UNSPECIFIED')) for v in values) else None


def compare(left, right, request, peer_name):
    if left.case_id == right.case_id:
        raise SimulationError('Choose a different case for comparison.')
    if request.get('peerCaseVersion') != right.case_version or request.get('peerScopeVersion') != right.version:
        raise SimulationError('The comparison case changed. Refresh both cases before comparing.')
    rate = number(request.get('percent'))
    if rate is None or abs(rate) > 10000:
        raise SimulationError('Enter a percentage change between -10000 and 10000.')
    key = request.get('optionId')
    if key not in left.nodes:
        raise SimulationError('Choose a declared input.')
    identity = comparison_identity(left.nodes[key])
    matches = [k for k, n in right.nodes.items() if identity is not None and comparison_identity(n) == identity]
    if len(matches) != 1 or sum(comparison_identity(n) == identity for n in left.nodes.values()) != 1:
        raise SimulationError('The cases do not declare one unambiguous input with the same definition, unit, currency, period, scope, basis and scenario.')
    peer_key = matches[0]
    if key not in left.baseline or peer_key not in right.baseline or left.baseline[key] == 0 or right.baseline[peer_key] == 0:
        raise SimulationError('A percentage shock needs an available nonzero baseline in both cases.')
    factor = 1 + rate / 100
    result = left.run({**request, 'value': str(left.baseline[key] * factor)})
    peer = right.run(dict(optionId=peer_key, originObjectId=peer_key, value=str(right.baseline[peer_key] * factor), caseVersion=right.case_version, scopeVersion=right.version))
    left_effects = {e['objectId']: e for e in result['effects']}
    right_effects = {e['objectId']: e for e in peer['effects']}
    rows, exclusions, used = [], [], set()
    for local_id in sorted(left.closure(key)):
        local_identity = comparison_identity(left.nodes[local_id])
        found = [k for k in right.closure(peer_key) if local_identity is not None and comparison_identity(right.nodes[k]) == local_identity]
        if len(found) != 1 or sum(comparison_identity(n) == local_identity for n in left.nodes.values()) != 1:
            exclusions.append(dict(caseId=left.case_id, objectId=local_id, label=left.nodes[local_id].get('label') or local_id, reason='No unique counterpart with the same declared definition and dimensions.'))
            continue
        peer_id = found[0]
        used.add(peer_id)
        if local_id not in left_effects or peer_id not in right_effects:
            exclusions.append(dict(caseId=left.case_id, objectId=local_id, label=left.nodes[local_id].get('label') or local_id, reason='This calculation is unavailable in one or both cases.'))
            continue
        rows.append(dict(label=left_effects[local_id]['objectLabel'], objectId=local_id, peerObjectId=peer_id,
            identity=dict(zip(DIMENSIONS, local_identity)), current=left_effects[local_id]['magnitude'], peer=right_effects[peer_id]['magnitude']))
    for peer_id in sorted(right.closure(peer_key) - used):
        exclusions.append(dict(caseId=right.case_id, objectId=peer_id, label=right.nodes[peer_id].get('label') or peer_id, reason='No comparable current-case calculation.'))
    result['request'] = {**result['request'], 'mode': 'compare', 'percent': str(rate), 'peerCaseId': right.case_id,
                         'peerCaseVersion': right.case_version, 'peerScopeVersion': right.version}
    result['comparison'] = dict(peerCaseId=right.case_id, peerName=peer_name, peerCaseVersion=right.case_version,
        peerScopeVersion=right.version, percent=str(rate), rows=rows, exclusions=exclusions, peerResult=peer)
    result['id'] = digest(result)
    return result
