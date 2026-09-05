"""Authenticated simulation workspace over server-owned Current and mapping."""
import copy

from fastapi import APIRouter, HTTPException, Request

from backend.dynamics.runtime.simulation import SimulationError, SimulationModel, admitted
from backend.dynamics.runtime.simulation_queries import inverse, compare
from backend.dynamics.runtime.simulation_events import event_scenarios
from backend.dynamics.runtime.graph_simulation import GraphSimulation
from backend.dynamics.runtime.ledger_store import ADMISSION_MODES
from app.statement_tracking import statement_context
from app.simulation_proposals import propose, capabilities, configured_proposal_model


def simulation_projection(case, model):
    snapshot = copy.deepcopy(case)
    scope = model.scope()
    snapshot['simulationScope'] = scope
    snapshot['simulationOptions'] = scope['options']
    snapshot['modelNodes'] = [dict(id=key, modelId=model.version, label=node.get('label') or key,
        currentValue=node.get('value'), unit=node.get('unit'), nodeRole=node.get('computational_form'),
        valueOrFormulaRef=node.get('formula_id'), freshnessStatus=node.get('freshness_status') or 'CURRENT',
        executionStatus='UNAVAILABLE' if key in model.errors else 'READY') for key, node in model.nodes.items()]
    snapshot['relations'] = list({r['id']: r for r in [*snapshot.get('relations', []), *model.relations]}.values())
    return snapshot


def simulation_router(load_case, authenticate, load_events=lambda _: [], scenario_store=None, load_transition_inputs=None, proposal_model=None):
    router = APIRouter(prefix='/api/v20/cases/{case_id}/simulations')

    def authorize(case_id, actor_id, token):
        if not isinstance(actor_id, str) or not isinstance(token, str):
            raise HTTPException(403, 'A valid case session is required.')
        actor = authenticate(case_id, actor_id, token)
        if 'READ_CASE' not in actor.get('entitlements', []):
            raise HTTPException(403, 'Case access is required.')
        return actor

    def context(case_id, request):
        actor = authorize(case_id, request.headers.get('x-panta-actor', ''), request.headers.get('x-panta-session'))
        case, graph, mapping = load_case(case_id)
        if case['caseRef']['id'] != case_id or graph.get('case_id', case_id) != case_id or mapping.get('case_id', case_id) != case_id:
            raise HTTPException(409, 'The supplied model belongs to a different case.')
        try:
            model = SimulationModel(case_id, case['caseVersion'], graph, mapping)
        except (SimulationError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return case, graph, model, actor

    def scenarios(case_id, graph, model):
        try:
            events = load_events(case_id)
            results, limits = event_scenarios(model, graph, events)
            if scenario_store:
                store = scenario_store(case_id)
                for result in results:
                    store.record(model, graph, result, next(e for e in events if e['event_id'] == result['event']['eventId']))
            return results, limits
        except (SimulationError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    def graph_context(case_id, case, graph, mapping):
        if load_transition_inputs is None:
            raise SimulationError('The case has no transition state and policies available for graph simulation.')
        inputs = load_transition_inputs(case_id)
        simulation = GraphSimulation(case_id, case['caseVersion'], inputs)
        if simulation.graph != graph or simulation.mapping != mapping:
            raise SimulationError('The displayed graph and transition state differ. Refresh the current case.')
        return simulation

    def graph_events(case_id, simulation):
        results, limits, seen = [], [], set()
        for event in load_events(case_id):
            if event.get('case_id', case_id) != case_id or event.get('admission_mode') not in ADMISSION_MODES or not admitted(event):
                continue
            if event.get('event_id') in seen:
                raise SimulationError('The event ledger contains duplicate identities.')
            seen.add(event.get('event_id'))
            try:
                if not event.get('source_ids') or not event.get('known_at'):
                    raise SimulationError('The event has no recorded evidence basis.')
                result = simulation.run(dict(caseVersion=simulation.case_version, graphVersion=simulation.version), event)
                if scenario_store:
                    scenario_store(case_id).record_graph(simulation, result, event)
                results.append(result)
            except ValueError as exc:
                limits.append(dict(eventId=event.get('event_id'), label=event.get('label') or event.get('event'), reason=str(exc)))
        return results, limits

    @router.get('')
    def read(case_id: str, request: Request):
        case, graph, model, actor = context(case_id, request)
        snapshot = simulation_projection(case, model)
        try:
            graph_simulation = graph_context(case_id, case, graph, model.mapping)
            snapshot['graphSimulationScope'] = graph_simulation.scope()
            snapshot['simulationTextInput'] = capabilities(graph_simulation, proposal_model)
            snapshot['graphSimulationScenarios'], snapshot['graphSimulationEventLimits'] = graph_events(case_id, graph_simulation)
        except ValueError as exc:
            snapshot['graphSimulationUnavailable'] = str(exc)
        snapshot['simulationScenarios'], snapshot['simulationEventLimits'] = scenarios(case_id, graph, model)
        # Every evidence reference in an event scenario remains inspectable even
        # when the older semantic projection has not rendered that raw claim yet.
        referenced = {c['claimId'] for s in snapshot['simulationScenarios'] for c in s['event']['changes']}
        projected = {c['id'] for c in snapshot.get('claims', [])}
        for claim in graph.get('claims', []):
            identity = claim.get('claim_id')
            if identity in referenced - projected and admitted(claim):
                snapshot['claims'].append(dict(id=identity, type='Source statement',
                    label=claim.get('statement') or claim.get('label') or identity,
                    normalizedStatement=claim.get('statement') or claim.get('label'), institutionalState='CURRENT'))
                projected.add(identity)
            if identity in referenced and admitted(claim):
                item = next(c for c in snapshot['claims'] if c['id'] == identity)
                item.setdefault('tracking', statement_context({**claim, 'scope': claim.get('scope') or claim.get('perimeter')}))
        return dict(snapshot=snapshot, actor=actor)

    @router.post('/propose')
    def propose_changes(case_id: str, request: Request, payload: dict):
        case, graph, model, _ = context(case_id, request)
        if set(payload) != {'text', 'caseVersion', 'graphVersion'}:
            raise HTTPException(422, 'Supply only the description and the displayed case and graph versions.')
        try:
            simulation = graph_context(case_id, case, graph, model.mapping)
            return propose(simulation, payload, proposal_model)
        except (SimulationError, ValueError) as exc:
            raise HTTPException(409 if 'Refresh' in str(exc) else 422, str(exc)) from exc

    @router.get('/archive/{scenario_id}')
    def archive(case_id: str, scenario_id: str, request: Request):
        authorize(case_id, request.headers.get('x-panta-actor', ''), request.headers.get('x-panta-session'))
        if not scenario_store:
            raise HTTPException(404, 'No scenario archive is configured.')
        try:
            saved = scenario_store(case_id).read(case_id, scenario_id)
        except SimulationError as exc:
            raise HTTPException(409, str(exc)) from exc
        if saved is None:
            raise HTTPException(404, 'Scenario not found.')
        return saved

    @router.post('')
    def run(case_id: str, request: Request, payload: dict):
        case, graph, model, _ = context(case_id, request)
        if payload.get('mode') in ('graph', 'graph_event'):
            allowed_graph = {'mode', 'caseVersion', 'graphVersion', 'optionId', 'originObjectId', 'assumption'} | ({'mutations'} if payload['mode'] == 'graph' else {'eventId', 'eventHash'})
            if set(payload) - allowed_graph:
                raise HTTPException(422, 'Supply only the selected changes or the admitted event reference.')
            try:
                simulation = graph_context(case_id, case, graph, model.mapping)
                if payload.get('graphVersion') != simulation.version or payload.get('caseVersion') != simulation.case_version:
                    raise SimulationError('The case, graph or policies changed. Refresh before simulating.')
                if payload['mode'] == 'graph_event':
                    results, _ = graph_events(case_id, simulation)
                    result = next((r for r in results if r['request']['eventId'] == payload.get('eventId') and r['request']['eventHash'] == payload.get('eventHash')), None)
                    if result is None:
                        raise SimulationError('This admitted event changed or is unavailable. Refresh the case.')
                    return result
                result = simulation.run(payload)
                if scenario_store:
                    scenario_store(case_id).record_graph(simulation, result, result['graph']['event'])
                return result
            except ValueError as exc:
                raise HTTPException(409 if 'Refresh' in str(exc) else 422, str(exc)) from exc
        common = {'mode', 'optionId', 'originObjectId', 'assumption', 'scopeVersion', 'caseVersion'}
        mode = payload.get('mode', 'manual')
        allowed = {'manual': {'value'}, 'event': {'scenarioId'}, 'inverse': {'inverse'},
                   'compare': {'percent', 'peerCaseId', 'peerCaseVersion', 'peerScopeVersion', 'peerActorId', 'peerSessionId'}}
        if not isinstance(mode, str) or mode not in allowed or set(payload) - common - allowed[mode]:
            raise HTTPException(422, 'Supply only the fields required by the selected simulation mode.')
        if any(not isinstance(payload.get(k), str) for k in ('optionId', 'originObjectId')):
            raise HTTPException(422, 'Choose a declared model input.')
        if payload.get('scopeVersion') != model.version or payload.get('caseVersion') != model.case_version:
            raise HTTPException(409, 'The case or model changed. Refresh before running the simulation.')
        try:
            if mode == 'inverse':
                return inverse(model, payload)
            if mode == 'event':
                results, _ = scenarios(case_id, graph, model)
                selected = next((r for r in results if r['id'] == payload.get('scenarioId')), None)
                if not selected or any(payload.get(k) != selected['request'][k] for k in ('optionId', 'originObjectId')):
                    raise SimulationError('The event scenario is unavailable. Refresh the current case.')
                return selected
            if mode == 'compare':
                peer_id = payload.get('peerCaseId')
                if not isinstance(peer_id, str) or not peer_id or peer_id == case_id:
                    raise SimulationError('Choose a different case for comparison.')
                authorize(peer_id, payload.get('peerActorId', ''), payload.get('peerSessionId'))
                peer_case, peer_graph, peer_mapping = load_case(peer_id)
                if peer_case['caseRef']['id'] != peer_id or peer_graph.get('case_id', peer_id) != peer_id or peer_mapping.get('case_id', peer_id) != peer_id:
                    raise SimulationError('The comparison model belongs to a different case.')
                peer = SimulationModel(peer_id, peer_case['caseVersion'], peer_graph, peer_mapping)
                return compare(model, peer, payload, peer_case['caseRef']['name'])
            return model.run(payload)
        except SimulationError as exc:
            status = 409 if 'Refresh' in str(exc) else 422
            raise HTTPException(status, str(exc)) from exc

    return router


def production_simulation_router():
    import os
    import app.v20_router as runtime
    from app.output_case import project_output_case
    from app.simulation_store import ScenarioStore
    from backend.dynamics.runtime import ledger_store
    from backend.dynamics.service import load_bundle_inputs, DynamicsBundleError

    def load(case_id):
        if not (runtime._case_vault_dir(case_id) / 'deal.md').exists():
            raise HTTPException(404, 'Case not found.')
        projection = runtime._build_projection(case_id)
        graph = projection['deal'].get('current_graph') or {}
        mapping = runtime._load_json_safe(runtime._pipeline_out_for_case(case_id) / 'execution_mapping.json')
        return project_output_case(projection), graph, mapping

    def authenticate(case_id, actor_id, token):
        runtime._authenticated_principal(case_id, actor_id, query_session_id=None, header_session_id=token)
        return dict(actorId=actor_id, entitlements=['READ_CASE'])

    def store(case_id):
        configured = os.environ.get('PANTA_SIMULATION_DB')
        if os.environ.get('VERCEL') == '1' and not configured:
            raise HTTPException(503, 'A durable scenario archive is required in this deployment.')
        return ScenarioStore(configured or runtime.VAULT / 'simulation-scenarios.sqlite3')

    def transition_inputs(case_id):
        try:
            return load_bundle_inputs(runtime._pipeline_out_for_case(case_id))
        except (DynamicsBundleError, OSError, ValueError) as exc:
            raise SimulationError('The current transition state and policies are unavailable for this case.') from exc

    return simulation_router(load, authenticate, ledger_store.read_ledger, store, transition_inputs, configured_proposal_model())
