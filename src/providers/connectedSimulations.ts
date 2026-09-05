import type { PantaCaseSnapshot } from '../types/domain';
import type { PantaBackendAdapter } from './PantaBackendAdapter';
import { createSimulationsAdapter, type SimulationCredentials } from './simulations';

/** Case sessions are issued by the existing host bootstrap, never by URL actor claims. */
export function createConnectedSimulationsAdapter(initialCaseId?: string, options: { fetchImpl?: typeof fetch } = {}): PantaBackendAdapter {
  const fetchImpl = options.fetchImpl ?? fetch;
  const sessions = new Map<string, Promise<SimulationCredentials>>();
  const snapshots = new Map<string, PantaCaseSnapshot>();
  const adapters = new Map<string, PantaBackendAdapter>();
  let defaultId = initialCaseId;
  let sessionCaseId = initialCaseId;
  const names = new Map<string, string>();
  let cases: { id: string; name: string }[] = [];
  let initial: Promise<void> | undefined;
  async function bootstrap(id?: string) {
    const response = await fetchImpl('/api/v20/bootstrap' + (id ? '?' + new URLSearchParams({ case_id: id }) : ''), { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The case session could not be opened.');
    const cid = result.context?.case_id;
    const actorId = result.context?.authenticated_actor?.actor_id;
    if (!cid || (id && id !== cid) || !actorId || !result.session_id || !Array.isArray(result.available_cases)) throw new Error('The host did not supply a valid case session.');
    if (!defaultId) defaultId = cid;
    cases = [...new Set<string>(result.available_cases.filter((value: unknown) => typeof value === 'string'))].map(value => ({ id: value, name: names.get(value) ?? value }));
    const session = { actorId, sessionId: result.session_id };
    sessions.set(cid, Promise.resolve(session));
    return session;
  }
  async function ready() {
    if (!initial) initial = bootstrap(defaultId).then(() => {}).catch(error => { initial = undefined; throw error; });
    await initial;
  }
  async function credentials(id: string) {
    await ready();
    if (!cases.some(c => c.id === id)) throw new Error('This case is not available in the current workspace.');
    if (!sessions.has(id)) sessions.set(id, bootstrap(id).catch(error => { sessions.delete(id); throw error; }));
    return sessions.get(id)!;
  }
  async function adapter(id?: string) {
    await ready();
    const cid = id ?? defaultId!;
    if (!cases.some(c => c.id === cid)) throw new Error('This case is not available in the current workspace.');
    if (!adapters.has(cid)) adapters.set(cid, createSimulationsAdapter(cid, () => credentials(cid), { fetchImpl, peerCredentials: credentials, peerSnapshot: id => snapshots.get(id) }));
    return adapters.get(cid)!;
  }
  return {
    async getSession() { return (await adapter(sessionCaseId)).getSession(); },
    async listCases() { await ready(); return cases; },
    async loadCase(id, query) {
      // Explicit refresh obtains a fresh expiring session. No automatic retry of a request.
      await ready();
      if (id && !cases.some(c => c.id === id)) throw new Error('This case is not available in the current workspace.');
      await bootstrap(id ?? defaultId);
      const loaded = await (await adapter(id)).loadCase(id ?? defaultId, query);
      if (loaded) {
        sessionCaseId = loaded.caseRef.id;
        snapshots.set(loaded.caseRef.id, loaded);
        names.set(loaded.caseRef.id, loaded.caseRef.name);
        cases = cases.map(c => ({ ...c, name: names.get(c.id) ?? c.name }));
      }
      return loaded;
    },
    async listCaseMoments() { return []; }, async listJournalStates() { return []; }, async loadJournal() { return null; },
    async inspectObject() { return null; }, async searchCase() { return []; },
    async runSimulation(id, request) { return (await adapter(id)).runSimulation(id, request); },
    async proposeSimulation(id, request) {
      const connected = await adapter(id);
      if (!connected.proposeSimulation) throw new Error('Text interpretation is not available in this workspace.');
      return connected.proposeSimulation(id, request);
    },
    async execute(id, command) { return (await adapter(id)).execute(id, command); },
  };
}
