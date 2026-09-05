import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/graph-simulation.json', 'utf8'));
function moduleUrl(source) { return 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText).toString('base64'); }
const documentsUrl = moduleUrl(fs.readFileSync('src/providers/sourceDocuments.ts', 'utf8'));
const source = fs.readFileSync('src/providers/simulations.ts', 'utf8').replace("from './sourceDocuments'", 'from ' + JSON.stringify(documentsUrl));
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { createSimulationsAdapter } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
let corrupt, requestCount = 0;
const id = fixture.snapshot.caseRef.id;
const adapter = createSimulationsAdapter(id, async () => ({ actorId: 'REVIEWER', sessionId: 'TOKEN' }), { fetchImpl: async (path, init) => {
  assert.equal(init.headers['X-Panta-Session'], 'TOKEN');
  if (init.method === 'GET') return new Response(JSON.stringify({ snapshot: fixture.snapshot, actor: { actorId: 'REVIEWER', entitlements: ['READ_CASE'] } }));
  assert(path.endsWith('/propose'), 'Preparing text must not call the simulation execution endpoint');
  requestCount++;
  assert.deepEqual(JSON.parse(init.body), fixture.proposalRequest);
  const result = structuredClone(fixture.proposalResult); corrupt?.(result);
  return new Response(JSON.stringify(result));
} });
const current = await adapter.loadCase(id), before = structuredClone(current);
assert.deepEqual(await adapter.proposeSimulation(id, fixture.proposalRequest), fixture.proposalResult);
assert.deepEqual(current, before, 'Proposals must not alter Current');
for (const mutate of [
  r => { r.caseId = 'OTHER'; }, r => { r.graphVersion = 'OLD'; }, r => { r.text = 'Other description'; },
  r => { r.items[0].objectId = 'PHANTOM'; }, r => { r.items[0].mutations[0].object_id = 'FOREIGN'; },
  r => { r.items[0].sourceText = 'Invented'; }, r => { r.questions.push({ question: 'Missing detail', objectIds: [] }); },
  r => { r.status = 'NEEDS_CLARIFICATION'; }, r => { r.items.push(structuredClone(r.items[0])); },
]) {
  corrupt = mutate;
  await assert.rejects(() => adapter.proposeSimulation(id, fixture.proposalRequest), /interpretation/);
}
const calls = requestCount;
await assert.rejects(() => adapter.proposeSimulation(id, { ...fixture.proposalRequest, graphVersion: 'STALE' }), /Refresh/);
await assert.rejects(() => adapter.proposeSimulation('OTHER', fixture.proposalRequest), /Refresh/);
assert.equal(calls, requestCount, 'Stale or foreign-case proposals must not reach the provider');
console.log('Text proposals PASS — authenticated proposal-only endpoint, exact text/version, live snapshot preserved, unknown refs, invented quotations and unresolved results rejected');
