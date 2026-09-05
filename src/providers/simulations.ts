import type { PantaBackendAdapter } from './PantaBackendAdapter';
import type { ActorContext, PantaCaseSnapshot, SimulationRequest, SimulationResult, SimulationProposalRequest, SimulationProposal } from '../types/domain';
import { withSourceDocuments } from './sourceDocuments';

export interface SimulationCredentials { actorId: string; sessionId: string }

/** Dedicated authenticated workspace; the host supplies its case-bootstrap credentials. */
export function createSimulationsAdapter(caseId: string, credentials: () => Promise<SimulationCredentials>, options: { fetchImpl?: typeof fetch; peerCredentials?: (id: string) => Promise<SimulationCredentials>; peerSnapshot?: (id: string) => PantaCaseSnapshot | undefined } = {}): PantaBackendAdapter {
  const fetchImpl = options.fetchImpl ?? fetch;
  const path = '/api/v20/cases/' + encodeURIComponent(caseId) + '/simulations';
  let current: PantaCaseSnapshot | undefined;
  let actor: ActorContext | undefined;
  let initial: Promise<void> | undefined;

  async function request(body?: (SimulationRequest & { peerActorId?: string; peerSessionId?: string }) | SimulationProposalRequest, suffix = '') {
    const session = await credentials();
    const response = await fetchImpl(path + suffix, { method: body ? 'POST' : 'GET', credentials: 'same-origin',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Panta-Actor': session.actorId, 'X-Panta-Session': session.sessionId },
      ...(body ? { body: JSON.stringify(body) } : {}) });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The simulation request could not be completed.');
    return result;
  }
  async function load() {
    const result = await request();
    const scope = result.snapshot?.simulationScope;
    if (result.snapshot?.caseRef?.id !== caseId || scope?.schemaVersion !== 'simulation/1.0' || scope.caseId !== caseId || scope.caseVersion !== result.snapshot.caseVersion || !Array.isArray(scope.limits) || !Array.isArray(result.snapshot.simulationOptions)) throw new Error('The simulation scope does not match the case.');
    const graph = result.snapshot.graphSimulationScope;
    if (graph && (graph.schemaVersion !== 'graph-simulation/1.0' || graph.caseId !== caseId || graph.caseVersion !== result.snapshot.caseVersion || !graph.version || !Array.isArray(graph.objects) || new Set(graph.objects.map((o: { id: string }) => o.id)).size !== graph.objects.length)) throw new Error('The graph simulation scope does not match the case.');
    current = result.snapshot; actor = result.actor;
  }
  async function ready() { if (!initial) initial = load().catch(error => { initial = undefined; throw error; }); await initial; }

  return withSourceDocuments({
    async proposeSimulation(id, body) {
      if (id !== caseId || !current?.graphSimulationScope || body.caseVersion !== current.caseVersion || body.graphVersion !== current.graphSimulationScope.version) throw new Error('The case changed. Refresh before interpreting the scenario.');
      const result: SimulationProposal = await request(body, '/propose');
      if (result.schemaVersion !== 'simulation-proposal/1.0' || result.caseId !== caseId || result.caseVersion !== current.caseVersion || result.caseVersion !== body.caseVersion || result.graphVersion !== current.graphSimulationScope.version || result.graphVersion !== body.graphVersion || result.text !== body.text || !['GUIDED', 'ASSISTED'].includes(result.interpreter) || !['READY', 'NEEDS_CLARIFICATION'].includes(result.status) || !Array.isArray(result.items) || !Array.isArray(result.questions) || !Array.isArray(result.limits)) throw new Error('The interpretation does not match this description and case version.');
      const known = new Set(current.graphSimulationScope.objects.map(o => o.id));
      if (new Set(result.items.map(i => i.id)).size !== result.items.length || result.items.some(i => !known.has(i.objectId) || !i.sourceText?.trim() || !body.text.includes(i.sourceText) || !Array.isArray(i.mutations) || !i.mutations.length || i.mutations.some(m => m.operation !== 'ADD' && !known.has(m.object_id) || m.operation === 'ADD' && (m.object_type !== 'CLAIM' || !m.object_id.startsWith('HYPOTHETICAL:') || !known.has(m.target_position_id ?? '')))) || result.questions.some(q => !q.question || !Array.isArray(q.objectIds) || q.objectIds.some(id => !known.has(id))) || (result.status === 'READY') !== (result.items.length > 0 && result.questions.length === 0)) throw new Error('The interpretation contains inconsistent changes or unresolved references.');
      return result;
    },
    async getSession() { await ready(); if (!actor) throw new Error('A case session is required.'); return { actor }; },
    async listCases() { await ready(); return current ? [current.caseRef] : []; },
    async loadCase(id, query) {
      if (id && id !== caseId) return null;
      if (query?.asOf) throw new Error('Refresh the current case before simulating.');
      await ready(); await load(); return current ?? null;
    },
    async listCaseMoments() { return []; },
    async listJournalStates() { return []; },
    async loadJournal() { return null; },
    async inspectObject() { return null; },
    async searchCase() { return []; },
    async execute() { throw new Error('The simulation workspace does not change the live case.'); },
    async runSimulation(id, body) {
      if (id !== caseId || !current?.simulationScope) throw new Error('Load the case and its simulation scope first.');
      if (body.mode === 'graph' || body.mode === 'graph_event') {
        if (!current.graphSimulationScope || body.caseVersion !== current.caseVersion || body.graphVersion !== current.graphSimulationScope.version) throw new Error('The graph simulation setup is stale. Refresh the case.');
        const result: SimulationResult = await request(body);
        validateGraph(result, body, current);
        return result;
      }
      // Preserve the versions the user actually viewed; never silently upgrade a stale request.
      if (body.caseVersion !== current.caseVersion || body.scopeVersion !== current.simulationScope.version) throw new Error('The simulation setup is stale. Refresh the case.');
      let sent: SimulationRequest & { peerActorId?: string; peerSessionId?: string } = body;
      if (body.mode === 'compare') {
        if (!body.peerCaseId || !options.peerCredentials) throw new Error('Access to the comparison case is required.');
        const peerSession = await options.peerCredentials(body.peerCaseId);
        sent = { ...body, peerActorId: peerSession.actorId, peerSessionId: peerSession.sessionId };
      }
      const result: SimulationResult = await request(sent);
      if (result.schemaVersion !== 'simulation/1.0' || result.caseId !== caseId || result.caseVersion !== body.caseVersion || result.scopeVersion !== body.scopeVersion || result.liveCaseUnchanged !== true || result.request?.optionId !== body.optionId || result.request?.originObjectId !== body.originObjectId || !Array.isArray(result.effects) || !Array.isArray(result.limits)) throw new Error('The simulation result does not match the requested case and input.');
      const mode = body.mode ?? 'manual';
      if ((result.request.mode ?? 'manual') !== mode) throw new Error('The result does not match the simulation mode.');
      if (mode === 'manual' && decimalIdentity(result.request.value) !== decimalIdentity(body.value)) throw new Error('The simulation value does not match the request.');
      if (mode === 'event' && (!result.event || result.id !== body.scenarioId || result.request.scenarioId !== body.scenarioId || !current.simulationScenarios?.some(s => s.id === body.scenarioId && s.event?.eventHash === result.event?.eventHash))) throw new Error('The event scenario does not match its admitted evidence.');
      if (mode === 'inverse' && (!result.inverse || !body.inverse || !result.request.inverse || !['FOUND', 'UNREACHABLE', 'UNSUPPORTED', 'NON_CONVERGENT'].includes(result.inverse.status) || result.inverse.outputId !== body.inverse.outputId || ['target', 'lower', 'upper'].some(key => decimalIdentity(result.request.inverse![key as 'target']) !== decimalIdentity(body.inverse![key as 'target'])))) throw new Error('The inverse result does not match the question.');
      if (mode === 'compare' && (!result.comparison || result.comparison.peerCaseId !== body.peerCaseId || result.comparison.peerCaseVersion !== body.peerCaseVersion || result.comparison.peerScopeVersion !== body.peerScopeVersion || decimalIdentity(result.comparison.percent) !== decimalIdentity(body.percent))) throw new Error('The comparison does not match both case versions and the requested shock.');
      validateTrace(result, new Set(current.modelNodes.map(n => n.id)));
      if (result.inverse?.status === 'FOUND') {
        const solved = result.inverse;
        if (decimalIdentity(result.request.value) !== decimalIdentity(solved.inputValue) || decimalIdentity(result.effects.find(e => e.objectId === body.optionId)?.magnitude?.after) !== decimalIdentity(solved.inputValue) || decimalIdentity(result.effects.find(e => e.objectId === solved.outputId)?.magnitude?.after) !== decimalIdentity(solved.actual)) throw new Error('The threshold does not match its calculated impact.');
      }
      if (result.comparison) {
        const comparison = result.comparison;
        const peer = options.peerSnapshot?.(comparison.peerCaseId);
        const trace = comparison.peerResult;
        if (!peer || !trace || trace.schemaVersion !== 'simulation/1.0' || trace.caseId !== comparison.peerCaseId || trace.caseVersion !== body.peerCaseVersion || trace.scopeVersion !== body.peerScopeVersion || trace.liveCaseUnchanged !== true || !Array.isArray(comparison.rows) || !Array.isArray(comparison.exclusions)) throw new Error('The comparison trace does not match the other case.');
        validateTrace(trace, new Set(peer.modelNodes.map(n => n.id)));
        if (new Set(comparison.rows.map(r => r.objectId)).size !== comparison.rows.length || new Set(comparison.rows.map(r => r.peerObjectId)).size !== comparison.rows.length) throw new Error('The comparison contains ambiguous matches.');
        for (const row of comparison.rows) {
          const left = result.effects.find(e => e.objectId === row.objectId)?.magnitude;
          const right = trace.effects.find(e => e.objectId === row.peerObjectId)?.magnitude;
          if (!left || !right || !row.current || !row.peer || ['before', 'after', 'delta', 'percent', 'unit'].some(key => left[key as keyof typeof left] !== row.current[key as keyof typeof left] || right[key as keyof typeof right] !== row.peer[key as keyof typeof right])) throw new Error('The comparison rows do not match the calculated impacts.');
        }
      }
      return result;
    },
  });
}

function stable(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => JSON.stringify(k) + ':' + stable(v)).join(',') + '}';
  return JSON.stringify(value);
}

function eventIdentity(value: unknown): string {
  if (!value || typeof value !== 'object' || !('mutations' in value) || !Array.isArray(value.mutations)) return stable(value);
  // The runtime canonically orders mutations. Preserve every mutation and its
  // contents when comparing the supplied envelope with the executed event.
  return stable({ ...value, mutations: value.mutations.map(stable).sort() });
}

function validateGraph(result: SimulationResult, body: SimulationRequest, current: PantaCaseSnapshot) {
  const graph = result.graph;
  if (!graph || result.schemaVersion !== 'simulation/1.0' || result.caseId !== current.caseRef.id || result.caseVersion !== body.caseVersion || result.liveCaseUnchanged !== true || result.request?.mode !== body.mode || result.request?.graphVersion !== body.graphVersion || graph.schemaVersion !== 'graph-simulation/1.0' || graph.version !== body.graphVersion || graph.engineVersion !== current.graphSimulationScope?.engineVersion || graph.engineResult?.candidate_state?.case_id !== current.caseRef.id || graph.engineResult?.transition_output?.case_id !== current.caseRef.id) throw new Error('The graph simulation result does not match the requested case and version.');
  if (body.mode === 'graph' && stable(result.request.mutations) !== stable(body.mutations)) throw new Error('The graph changes do not match the request.');
  const event = current.graphSimulationScenarios?.find(s => s.request.eventId === body.eventId && s.request.eventHash === body.eventHash);
  if (body.mode === 'graph_event' && (!event || result.id !== event.id || result.request.eventId !== body.eventId || result.request.eventHash !== body.eventHash || stable(event.graph?.event) !== stable(graph.event))) throw new Error('The graph event does not match its admitted evidence.');
  if (!Array.isArray(graph.rows) || !Array.isArray(graph.edges) || !Array.isArray(graph.issues) || !graph.counts || !graph.labels || !Array.isArray(graph.event?.mutations)) throw new Error('The graph result has inconsistent coverage.');
  const executed = graph.engineResult.normalized_event_batch;
  if (!Array.isArray(executed) || executed.length !== 1 || eventIdentity(executed[0]) !== eventIdentity(graph.event)) throw new Error('The graph event does not match the executed transition.');
  if (body.mode === 'graph') {
    if (graph.event.mutations.length !== body.mutations?.length || graph.event.source_ids.join() !== 'HYPOTHETICAL-USER-INPUT') throw new Error('The graph event does not match the requested changes.');
    for (let i = 0; i < body.mutations.length; i++) for (const [key, value] of Object.entries(body.mutations[i])) {
      if (stable(graph.event.mutations[i][key as keyof typeof graph.event.mutations[number]]) !== stable(value)) throw new Error('The graph event does not match the requested changes.');
    }
  }
  const known = new Set(current.graphSimulationScope!.objects.map(o => o.id));
  for (const mutation of graph.event.mutations) if (mutation.operation === 'ADD') known.add(mutation.object_id);
  const { rows, counts } = graph;
  if (new Set(rows.map(r => r.id)).size !== rows.length || rows.some(r => !known.has(r.id) || !['CHANGED', 'HELD', 'UNAVAILABLE'].includes(r.status) || !Array.isArray(r.changes)) || counts.examined !== rows.length || counts.changed !== rows.filter(r => r.status === 'CHANGED').length || counts.held !== rows.filter(r => r.status === 'HELD').length || counts.unavailable !== rows.filter(r => r.unresolved).length || graph.edges.some(e => !known.has(e.source) || !known.has(e.target) || !graph.labels[e.source] || !graph.labels[e.target])) throw new Error('The graph result has inconsistent coverage.');
}

// Compare requested decimal values exactly, without binary-float rounding.
function decimalIdentity(value?: string): string {
  const match = value?.trim().match(/^([+-]?)([0-9]*)(?:\.([0-9]*))?(?:e([+-]?[0-9]+))?$/i);
  if (!match || !(match[2] + (match[3] ?? '')).length) throw new Error('The simulation input is not a decimal number.');
  const digits = (match[2] + (match[3] ?? '')).replace(/^0+/, '');
  if (!digits) return '0';
  const significant = digits.replace(/0+$/, '');
  const power = BigInt(match[4] ?? '0') - BigInt((match[3] ?? '').length) + BigInt(digits.length - significant.length);
  return (match[1] === '-' ? '-' : '') + significant + 'e' + power;
}

function validateTrace(result: SimulationResult, known: Set<string>) {
  if (!Array.isArray(result.effects) || !Array.isArray(result.limits) || !result.coverage) throw new Error('The simulation result has inconsistent coverage.');
  const ids = [...result.effects.map(e => e.objectId), ...result.limits.map(e => e.objectId)];
  const changed = result.effects.filter(e => e.state !== 'HOLDS').length;
  if (new Set(ids).size !== ids.length || ids.some(id => !known.has(id)) || result.coverage.examinedCount !== ids.length || result.coverage.changedCount !== changed || result.coverage.heldCount !== result.effects.length - changed || result.coverage.unmappedCount !== result.limits.length) throw new Error('The simulation result has inconsistent coverage.');
}
