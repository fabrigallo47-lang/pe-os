import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

const fixture = JSON.parse(fs.readFileSync('tests/fixtures/simulation-queries.json', 'utf8'));
function moduleUrl(source) {
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  return 'data:text/javascript;base64,' + Buffer.from(code).toString('base64');
}
const simulationUrl = moduleUrl(fs.readFileSync('src/providers/simulations.ts', 'utf8').replace("import { withSourceDocuments } from './sourceDocuments';", 'const withSourceDocuments = adapter => adapter;'));
const connectedSource = fs.readFileSync('src/providers/connectedSimulations.ts', 'utf8').replace("from './simulations'", 'from ' + JSON.stringify(simulationUrl));
const { createConnectedSimulationsAdapter } = await import(moduleUrl(connectedSource));
const ids = Object.keys(fixture.snapshots);
const calls = [];
let corrupt, failBootstrap = true;
const adapter = createConnectedSimulationsAdapter(ids[0], { fetchImpl: async (path, init) => {
  calls.push({ path, init });
  if (path.startsWith('/api/v20/bootstrap')) {
    if (failBootstrap) return new Response(JSON.stringify({ detail: 'Temporary startup failure' }), { status: 503 });
    const id = new URL(path, 'http://test').searchParams.get('case_id');
    return new Response(JSON.stringify({ session_id: id + '-TOKEN', available_cases: ids, context: { case_id: id, authenticated_actor: { actor_id: 'REVIEWER' } } }));
  }
  const id = decodeURIComponent(path.split('/')[4]);
  assert.equal(init.headers['X-Panta-Session'], id + '-TOKEN');
  assert.equal(init.headers['X-Panta-Actor'], 'REVIEWER');
  if (init.method === 'GET') return new Response(JSON.stringify({ snapshot: fixture.snapshots[id], actor: { actorId: 'REVIEWER', entitlements: ['READ_CASE'] } }));
  const body = JSON.parse(init.body);
  if (body.mode === 'compare') {
    assert.equal(body.peerSessionId, ids[1] + '-TOKEN');
    assert.equal(body.peerActorId, 'REVIEWER');
  }
  const result = structuredClone(fixture.results[body.mode]);
  corrupt?.(result);
  return new Response(JSON.stringify(result));
} });
await assert.rejects(() => adapter.loadCase(ids[0]), /startup failure/);
failBootstrap = false;
await adapter.loadCase(ids[0]);
assert.equal((await adapter.getSession()).actor.actorId, 'REVIEWER');
assert.equal((await adapter.listCases()).length, 2);
await adapter.loadCase(ids[1]);
for (const mode of ['event', 'inverse', 'compare']) {
  const result = await adapter.runSimulation(ids[0], fixture.requests[mode]);
  assert.deepEqual(result, fixture.results[mode]);
  assert(!JSON.stringify(result).includes('TOKEN'));
}
for (const [mode, mutate, error] of [
  ['event', result => { result.event.eventHash = 'unrelated'; }, /admitted evidence/],
  ['inverse', result => { result.inverse.inputValue = '999'; }, /calculated impact/],
  ['inverse', result => { result.request.inverse.target = '4'; }, /does not match/],
  ['compare', result => { result.comparison.peerCaseVersion = 'OLD'; }, /both case versions/],
  ['compare', result => { result.comparison.peerResult.caseId = ids[0]; }, /other case/],
  ['compare', result => { result.comparison.rows[0].peer.after = '999'; }, /calculated impacts/],
  ['compare', result => { result.comparison.peerResult.effects[0].objectId = 'UNKNOWN'; }, /inconsistent coverage/],
]) {
  corrupt = mutate;
  await assert.rejects(() => adapter.runSimulation(ids[0], fixture.requests[mode]), error);
}
corrupt = undefined;
await assert.rejects(() => adapter.runSimulation(ids[0], { ...fixture.requests.inverse, scopeVersion: 'OLD' }), /stale/);
const before = calls.length;
await assert.rejects(() => adapter.loadCase('UNAUTHORIZED'), /not available/);
assert.equal(calls.length, before, 'Unavailable case must not be bootstrapped.');
console.log('Simulation queries PASS — bootstrap recovery, real engine event/inverse/comparison payloads, separate case sessions, stale and corrupt responses rejected');
