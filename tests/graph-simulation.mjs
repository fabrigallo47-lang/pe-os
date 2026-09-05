import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/graph-simulation.json', 'utf8'));
const source = fs.readFileSync('src/providers/simulations.ts', 'utf8').replace("import { withSourceDocuments } from './sourceDocuments';", 'const withSourceDocuments = adapter => adapter;');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { createSimulationsAdapter } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
let corrupt;
const adapter = createSimulationsAdapter(fixture.snapshot.caseRef.id, async () => ({ actorId: 'REVIEWER', sessionId: 'TOKEN' }), { fetchImpl: async (_, init) => {
  assert.equal(init.headers['X-Panta-Session'], 'TOKEN');
  if (init.method === 'GET') return new Response(JSON.stringify({ snapshot: fixture.snapshot, actor: { actorId: 'REVIEWER', entitlements: ['READ_CASE'] } }));
  const body = JSON.parse(init.body);
  const key = body.assumption === fixture.requests.graph_combined.assumption ? 'graph_combined' : body.mode;
  const result = structuredClone(fixture.results[key]);
  corrupt?.(result);
  return new Response(JSON.stringify(result));
} });
const current = await adapter.loadCase(fixture.snapshot.caseRef.id), before = structuredClone(current);
assert.notDeepEqual(fixture.results.graph_combined.graph.event.mutations, fixture.results.graph_combined.graph.engineResult.normalized_event_batch[0].mutations, 'The combined fixture must exercise runtime mutation reordering');
for (const mode of ['graph', 'graph_event', 'graph_combined']) {
  assert.deepEqual(await adapter.runSimulation(current.caseRef.id, fixture.requests[mode]), fixture.results[mode]);
  assert.deepEqual(current, before, 'Simulation must not rewrite the live frontend snapshot');
}
for (const [mode, mutate, error] of [
  ['graph', r => { r.caseId = 'OTHER'; }, /does not match/],
  ['graph', r => { r.graph.version = 'STALE'; }, /does not match/],
  ['graph', r => { r.graph.engineResult.candidate_state.case_id = 'OTHER'; }, /does not match/],
  ['graph', r => { r.request.mutations[0].object_id = 'OTHER'; }, /changes do not match/],
  ['graph', r => { r.graph.rows[0].id = 'PHANTOM'; }, /coverage/],
  ['graph', r => { r.graph.edges[0].source = 'PHANTOM'; }, /coverage/],
  ['graph', r => { r.graph.counts.held++; }, /coverage/],
  ['graph', r => { r.liveCaseUnchanged = false; }, /does not match/],
  ['graph_event', r => { r.request.eventHash = 'UNRELATED'; }, /admitted evidence/],
  ['graph_event', r => { r.graph.event.source_ids = ['FAKE']; }, /admitted evidence/],
  ['graph_combined', r => { r.graph.engineResult.normalized_event_batch[0].mutations.pop(); }, /executed transition/],
  ['graph_combined', r => { const m = r.graph.engineResult.normalized_event_batch[0].mutations; m[0] = structuredClone(m[1]); }, /executed transition/],
  ['graph_combined', r => { r.graph.engineResult.normalized_event_batch[0].mutations.find(m => m.field === 'value').to = '999'; }, /executed transition/],
  ['graph_combined', r => { r.graph.engineResult.normalized_event_batch.push(structuredClone(r.graph.event)); }, /executed transition/],
]) {
  corrupt = mutate;
  await assert.rejects(() => adapter.runSimulation(current.caseRef.id, fixture.requests[mode]), error);
}
corrupt = undefined;
await assert.rejects(() => adapter.runSimulation(current.caseRef.id, { ...fixture.requests.graph, graphVersion: 'OLD' }), /stale/);
console.log('Graph simulations PASS — real engine transport, evidence and case pins, no snapshot mutation, corrupt identities, traces and counts rejected');
