import type { PantaBackendAdapter } from './PantaBackendAdapter';

export const emptyAdapter: PantaBackendAdapter = {
  async getSession() { return { actor: { actorId: 'local-user', entitlements: ['READ_CASE'] }, actors: [] }; },
  async listCases() { return []; },
  async loadCase() { return null; },
  async listCaseMoments() { return []; },
  async loadJournal() { return null; },
  async listJournalStates() { return []; },
  async inspectObject() { return null; },
  async searchCase() { return []; },
  async runSimulation() { return null; },
  async execute() { return null; },
};
