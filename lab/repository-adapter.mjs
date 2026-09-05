import { withSourceDocuments } from '../src/providers/sourceDocuments';

/** Read-only test backend; the production application receives its normal adapter interface. */
export function repositoryAdapter(data, simulated = false) {
  const id = data.snapshot.caseRef.id;
  return withSourceDocuments({
    async getSession() { return {actor:{actorId:'FIXTURE-READER',entitlements:['READ_CASE']}}; },
    async listCases() { return [data.snapshot.caseRef]; },
    async loadCase(caseId, options) {
      if (options?.asOf) throw new Error('This fixed test graph has no institutional replay.');
      return caseId === id ? data.snapshot : null;
    },
    async listCaseMoments() { return []; },
    async loadJournal() { return null; },
    async listJournalStates() { return []; },
    async inspectObject(caseId, objectId, options) {
      if (caseId !== id) return null;
      const response = await fetch('/api/source-tracking-lab/reference/inspect?' + new URLSearchParams({object_id:objectId,simulate:String(simulated)}));
      if (!response.ok) throw new Error('The graph inspection could not be loaded.');
      const result = await response.json();
      if (result && options?.excludeObjectIds?.length) {
        result.supportObjectIds = result.supportObjectIds.filter(value=>!options.excludeObjectIds.includes(value));
      }
      return result;
    },
    async searchCase(caseId, query) {
      if (caseId !== id || !query.trim()) return [];
      const needle = query.trim().toLowerCase();
      return [...data.entries,...data.snapshot.sources.map(row=>({id:row.id,label:row.title,kind:'source'}))]
        .filter(row=>(row.id+' '+row.label).toLowerCase().includes(needle)).slice(0,40)
        .map(row=>({objectId:row.id,label:row.label,kind:row.kind}));
    },
    async runSimulation() { throw new Error('This source-tracking fixture has no financial simulation.'); },
    async execute() { throw new Error('This source-tracking fixture is read-only.'); },
  });
}
