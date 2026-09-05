import type { PantaBackendAdapter } from './PantaBackendAdapter';
import type { ActorContext, PantaCaseSnapshot } from '../types/domain';
import { withSourceDocuments } from './sourceDocuments';

export interface OutputCredentials { actorId: string; sessionId: string }

/** Authenticated output workspace. Credentials come from the host's case bootstrap. */
export function createOutputsAdapter(caseId: string, credentials: () => Promise<OutputCredentials>, options: { fetchImpl?: typeof fetch } = {}): PantaBackendAdapter {
  const fetchImpl = options.fetchImpl ?? fetch;
  let current: PantaCaseSnapshot | undefined;
  let actor: ActorContext | undefined;
  let initialLoad: Promise<void> | undefined;
  const path = '/api/v20/cases/' + encodeURIComponent(caseId) + '/outputs';
  async function request(suffix = '', init?: RequestInit) {
    const session = await credentials();
    return fetchImpl(path + suffix, { ...init, credentials: 'same-origin', headers: {
      Accept: 'application/json', 'Content-Type': 'application/json',
      'X-Panta-Actor': session.actorId, 'X-Panta-Session': session.sessionId,
    } });
  }
  async function data(response: Response) {
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The output request could not be completed.');
    if (result.snapshot?.caseRef?.id !== caseId || !result.snapshot?.outputCapabilities?.versioned || !Array.isArray(result.snapshot?.artifactBlocks)) throw new Error('The output projection does not match this case.');
    current = result.snapshot;
    if (result.actor) actor = result.actor;
  }
  async function load() { await data(await request()); }
  async function ready() { if (!initialLoad) initialLoad = load().catch(error => { initialLoad = undefined; throw error; }); await initialLoad; }
  return withSourceDocuments({
    async getSession() { await ready(); if (!actor) throw new Error('An output session is required.'); return { actor }; },
    async listCases() { await ready(); return current ? [current.caseRef] : []; },
    async loadCase(id, options) {
      if (id && id !== caseId) return null;
      if (options?.asOf) throw new Error('This output workspace shows the current case. Approved exports retain their frozen basis.');
      await ready(); await load(); return current ?? null;
    },
    async listCaseMoments() { return []; },
    async listJournalStates() { return []; },
    async loadJournal() { return null; },
    async inspectObject() { return null; }, // Existing projection inspection supplies explicit connections.
    async searchCase() { return []; },
    async runSimulation() { throw new Error('Financial simulation is unavailable in this output workspace.'); },
    async execute(id, command) {
      if (id !== caseId || !current) throw new Error('Load the case before editing an output.');
      const action = command.action;
      const artifact = 'artifactId' in action ? current.artifacts.find(item => item.id === action.artifactId) : undefined;
      const body = { ...command, requestId: crypto.randomUUID(), caseVersion: current.caseVersion, expectedRevision: artifact?.revisionId };
      await data(await request('/commands', { method: 'POST', body: JSON.stringify(body) }));
      return current ?? null;
    },
    async exportArtifact(id, artifactId, revision, format) {
      if (id !== caseId) throw new Error('This export belongs to a different case.');
      const response = await request('/' + encodeURIComponent(artifactId) + '/export?' + new URLSearchParams({ revision, format }));
      if (!response.ok) { const result = await response.json(); throw new Error(result.detail || 'The approved output could not be exported.'); }
      const filename = response.headers.get('Content-Disposition')?.match(/filename="([A-Za-z0-9_.-]+)"/)?.[1];
      if (!filename) throw new Error('The server did not supply an export filename.');
      return { filename, blob: await response.blob() };
    },
  });
}
