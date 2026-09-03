import assert from 'node:assert/strict';
import { SyntheticAdapter } from './synthetic-adapter.mjs';

const a=new SyntheticAdapter();
const session=await a.getSession();
assert.equal(session.actor.actorId,'ACT-1');

// Replay is a ledger/as-of projection, not a list of fabricated snapshots.
const past=await a.loadCase('CASE-1',{asOf:'2026-01-10T12:00:00Z'});
const current=await a.loadCase('CASE-1');
assert.notEqual(past.caseReadings[0].text,current.caseReadings[0].text);
const pastAgain=await a.loadCase('CASE-1',{asOf:'2026-01-10T12:00:00Z'});
assert.deepEqual(past,pastAgain);

// Universal inspection returns refs/facts and temporary support exclusion changes only inspection.
const lens=await a.inspectObject('CASE-1','CR-1');
assert.deepEqual(lens.supportObjectIds,['CL-1','CL-2']);
assert.deepEqual(lens.independentSupportObjectIds,['CL-1']);
const without=await a.inspectObject('CASE-1','CR-1',{excludeObjectIds:['CL-1']});
assert.deepEqual(without.supportObjectIds,['CL-2']);
assert.deepEqual(without.independentSupportObjectIds,[]);
const currentAfterInspection=await a.loadCase('CASE-1');
assert.equal(currentAfterInspection.caseReadings[0].supportObjectIds.length,2);
assert.deepEqual(currentAfterInspection.caseReadings[0].independentSupportObjectIds,['CL-1']);

// Simulation has numeric coverage and explicit survivors.
const sim=await a.runSimulation('CASE-1',{optionId:'SIM-1',originObjectId:'CR-1',assumption:'Representative test fails'});
assert.equal(sim.coverage.examinedCount,2);
assert.equal(sim.coverage.changedCount,1);
assert.equal(sim.coverage.heldCount,1);
assert.ok(sim.effects.some(x=>x.state==='HOLDS'));

// HumanPosition is immutable attributed content; simulation/inspection did not grade or rewrite it.
assert.equal(current.humanPositions[0].text,'The team should verify performance before committing.');
assert.equal(current.humanPositions[0].institutionalState,'CURRENT');
assert.ok(!('epistemicStatus' in current.humanPositions[0]));

// Artifact sync is explicit and actor-attributed command behavior.
const synced=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T11:00:00Z',action:{type:'SYNC_ARTIFACT',artifactId:'ART-1'}});
assert.equal(synced.artifacts[0].pendingCaseChangeCount,0);
assert.equal(synced.artifacts[0].syncStatus,'CURRENT');

// Decision recording is actor-attributed and the only tested path to UI RECORDED state.
const decided=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T12:00:00Z',action:{type:'RECORD_DECISION',pathId:'PATH-1',rationale:'Wait for evidence.'}});
assert.equal(decided.decision.status,'RECORDED');
assert.equal(decided.decisions[0].actorOrBodyId,'ACT-1');

console.log('Synthetic adapter behavior PASS');
