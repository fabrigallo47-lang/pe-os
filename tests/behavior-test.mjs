import assert from 'node:assert/strict';
import { SyntheticAdapter } from './synthetic-adapter.mjs';
import { EMPTY_CASE_ID, EmptyCaseAdapter } from '../lab/empty-case-adapter.mjs';

// A created-but-empty case is distinct from having no selected case.
const emptyCaseAdapter=new EmptyCaseAdapter();
const emptyCaseSession=await emptyCaseAdapter.getSession();
const emptyCase=await emptyCaseAdapter.loadCase(EMPTY_CASE_ID);
assert.equal(emptyCase.caseRef.name,'New investment case');
assert.equal(emptyCase.actors.find(item=>item.id===emptyCaseSession.actor.actorId).role,'Case Owner');
assert.equal(emptyCase.events.find(item=>item.eventType==='CASE_CREATED').actorOrPolicyId,emptyCaseSession.actor.actorId);
for(const collection of ['sources','workstreams','questions','caseReadings','unknowns','workItems'])assert.deepEqual(emptyCase[collection],[]);
assert.equal(emptyCase.formation,undefined);
const emptyCaseWithMaterial=await emptyCaseAdapter.execute(EMPTY_CASE_ID,{actorId:emptyCaseSession.actor.actorId,submittedAt:'2026-01-12T10:00:00Z',action:{type:'ADD_MATERIAL',files:[{name:'First material.pdf'}]}});
assert.equal(emptyCaseWithMaterial.sources[0].title,'First material.pdf');
assert.equal(emptyCaseWithMaterial.events.filter(item=>item.eventType==='SOURCE_REGISTERED').length,1);
assert.equal(emptyCaseWithMaterial.events.filter(item=>item.eventType==='SOURCE_VERSION_RECORDED').length,1);
const emptyCaseJournal=await emptyCaseAdapter.loadJournal(EMPTY_CASE_ID);
assert.equal(emptyCaseJournal.schemaVersion,'case-journal/1.0');
assert.equal(emptyCaseJournal.eventCount,3);
assert.equal(emptyCaseJournal.summary.changeCount,0);
await assert.rejects(
  emptyCaseAdapter.execute(EMPTY_CASE_ID,{actorId:'ACT-NOT-AUTHORIZED',submittedAt:'2026-01-12T10:30:00Z',action:{type:'ADD_MATERIAL',files:[{name:'Unauthorized.pdf'}]}}),
  /authorized case actor/
);

const a=new SyntheticAdapter();
const session=await a.getSession();
assert.equal(session.actor.actorId,'ACT-1');

// Replay is a ledger/as-of projection, not a list of fabricated snapshots.
const past=await a.loadCase('CASE-1',{asOf:'2026-01-10T12:00:00Z'});
const current=await a.loadCase('CASE-1');
assert.notEqual(past.caseReadings[0].text,current.caseReadings[0].text);
const pastAgain=await a.loadCase('CASE-1',{asOf:'2026-01-10T12:00:00Z'});
assert.deepEqual(past,pastAgain);
assert.equal(past.workstreams.find(item=>item.id==='WS-1').latestChangeEventId,undefined);
assert.equal(past.caseReadings.find(item=>item.id==='CR-1').lastChangeEventId,undefined);
assert.ok(!past.events.some(item=>item.id==='EV-3'));
assert.equal(current.workstreams.find(item=>item.id==='WS-1').latestChangeEventId,'EV-3');
assert.equal(current.caseReadings.find(item=>item.id==='CR-1').lastChangeEventId,'EV-3');
assert.equal(current.events.find(item=>item.id==='EV-3').eventType,'CASE_READING_RECOMPUTED');
assert.equal(current.events.find(item=>item.id==='EV-3').objectId,'CR-1');

// Case changes are a deterministic read model over recorded events and immutable states.
const journalStates=await a.listJournalStates('CASE-1');
assert.equal(journalStates.length,2);
const journal=await a.loadJournal('CASE-1');
assert.equal(journal.schemaVersion,'case-journal/1.0');
assert.equal(journal.summary.rulesVersion,'journal-change-rules/1.1');
assert.deepEqual(journal.events.map(event=>event.eventId),['EV-0','EV-2','EV-3']);
assert.ok(journal.events.every(event=>event.effectiveDate&&event.knownAt&&event.recordedAt&&event.actorId));
assert.deepEqual((await a.loadJournal('CASE-1',{kind:'EVIDENCE'})).events.map(event=>event.eventId),['EV-2']);
assert.equal((await a.loadJournal('CASE-1',{workstream:'WS-NOT-PRESENT'})).summary.changeCount,0);
assert.equal((await a.loadJournal('CASE-1',{baselineStateId:'STATE-2',currentStateId:'STATE-2'})).summary.changeCount,0);
assert.equal((await a.loadJournal('CASE-1',{closeStateId:'STATE-1'})).drift.status,'AVAILABLE');
await assert.rejects(a.loadJournal('CASE-1',{baselineStateId:'STATE-2',currentStateId:'STATE-1'}),error=>error.status===409);

// The lab exercises governed lifecycle states and adapter-fed detail instead of hiding them.
assert.ok(session.actor.entitlements.includes('ADD_MATERIAL'));
assert.ok(session.actor.entitlements.includes('ADMIT_CASE_READING'));
assert.equal(current.pendingReviews.filter(item=>item.status==='NEW').length,1);
assert.ok(current.claims.length>current.pendingReviews.length);
assert.ok(current.findings.find(item=>item.id===current.pendingReviews[0].findingId).derivationObjectIds.length>1);
assert.equal(current.pendingReviews[0].title,'Narrow the product performance view');
assert.equal(current.formation.status,'PROPOSED_NOT_LIVE');
assert.equal(current.formation.materialIds.length,6);
assert.equal(current.formation.proposedWorkstreamIds.length,6);
assert.equal(current.unknowns.filter(item=>item.status==='OPEN').length,6);
assert.equal(current.events.find(item=>item.eventType==='CASE_CREATED').actorOrPolicyId,'ACT-1');
assert.ok(current.decisions.length>1);
assert.equal(current.decision.status,'OPEN');
assert.equal(current.decision.recordedDecisionId,undefined);
assert.equal(current.questions.filter(item=>item.decisionDimensions).length,4);
assert.equal(current.decision.dueAt,'2026-01-15T16:00:00Z');
assert.equal(current.artifactDiffs.length,1);
for(const workstream of current.workstreams.filter(item=>item.ownerActorId))assert.ok(current.actors.some(item=>item.id===workstream.ownerActorId));
assert.ok(current.workstreams.some(item=>!item.ownerActorId));

// Universal inspection returns refs/facts and temporary support exclusion changes only inspection.
const lens=await a.inspectObject('CASE-1','CR-1');
assert.deepEqual(lens.supportObjectIds,['CL-1','CL-2']);
assert.deepEqual(lens.independentSupportObjectIds,['CL-1']);
assert.deepEqual(lens.dependentObjectIds,['Q-C']);
const without=await a.inspectObject('CASE-1','CR-1',{excludeObjectIds:['CL-1']});
assert.deepEqual(without.supportObjectIds,['CL-2']);
assert.deepEqual(without.independentSupportObjectIds,[]);
const currentAfterInspection=await a.loadCase('CASE-1');
assert.equal(currentAfterInspection.caseReadings[0].supportObjectIds.length,2);
assert.deepEqual(currentAfterInspection.caseReadings[0].independentSupportObjectIds,['CL-1']);
const personLens=await a.inspectObject('CASE-1','ACT-2');
assert.deepEqual(personLens.supportObjectIds,[]);
assert.deepEqual(personLens.independentSupportObjectIds,[]);
assert.deepEqual(personLens.unknownIds,['U-M','U-D']);
assert.deepEqual(personLens.dependentObjectIds,['WS-1']);
assert.deepEqual(personLens.relatedObjectIds,['WI-M','WI-D']);
assert.deepEqual(personLens.sourceLocators,[]);
assert.deepEqual(personLens.allowedActions,[]);
const gapLens=await a.inspectObject('CASE-1','U-1');
assert.deepEqual(gapLens.dependentObjectIds,['Q-1']);
assert.deepEqual(gapLens.relatedObjectIds,['WI-1']);
assert.ok(!gapLens.allowedActions.includes('TRACE'));
const workLens=await a.inspectObject('CASE-1','WI-1');
assert.deepEqual(workLens.unknownIds,['U-1']);
assert.deepEqual(workLens.dependentObjectIds,['CR-1']);
assert.ok(!workLens.allowedActions.includes('SIMULATE'));

// Simulation has numeric coverage and explicit survivors.
const sim=await a.runSimulation('CASE-1',{optionId:'SIM-1',originObjectId:'CR-1',assumption:'Representative test fails'});
assert.equal(sim.coverage.examinedCount,3);
assert.equal(sim.coverage.changedCount,2);
assert.equal(sim.coverage.heldCount,1);
assert.ok(sim.effects.some(x=>x.state==='HOLDS'));
assert.ok(sim.effects.some(x=>x.objectId==='Q-C'&&x.reasonRelationIds.includes('REL-2')));

// HumanPosition is immutable attributed content; simulation/inspection did not grade or rewrite it.
assert.equal(current.humanPositions[0].text,'The team should verify performance before committing.');
assert.equal(current.humanPositions[0].institutionalState,'CURRENT');
assert.ok(!('epistemicStatus' in current.humanPositions[0]));

// Artifact sync is explicit and actor-attributed command behavior.
const synced=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T11:00:00Z',action:{type:'SYNC_ARTIFACT',artifactId:'ART-1'}});
assert.equal(synced.artifacts[0].pendingCaseChangeCount,0);
assert.equal(synced.artifacts[0].syncStatus,'CURRENT');

// Decision recording is actor-attributed and the only tested path to UI RECORDED state.
const decided=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T12:00:00Z',action:{type:'RECORD_DECISION',pathId:'PATH-2',rationale:'Proceed only after independent verification.',conditionText:'Independent production benchmark completed.'}});
assert.equal(decided.decision.status,'RECORDED');
const recorded=decided.decisions.find(item=>item.id===decided.decision.recordedDecisionId);
assert.equal(recorded.actorOrBodyId,'ACT-1');
assert.equal(recorded.recordedAt,'2026-01-11T12:00:00Z');
assert.equal(recorded.caseVersion,'v1');
assert.equal(recorded.basisObjectIds.length,4);
assert.equal(recorded.conditionIds.length,1);
assert.equal(decided.conditions.find(item=>item.id===recorded.conditionIds[0]).label,'Independent production benchmark completed.');
assert.ok(decided.events.some(item=>item.eventType==='DECISION_RECORDED'&&item.objectId===recorded.id));
assert.equal(decided.decisions.length,3);

const reviewed=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T13:00:00Z',action:{type:'REVIEW_ITEM',reviewId:'REV-1',disposition:'ADMIT'}});
assert.equal(reviewed.pendingReviews[0].status,'ADMITTED');
const formed=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T14:00:00Z',action:{type:'ADOPT_FORMATION'}});
assert.equal(formed.formation.status,'ADOPTED');
const material=await a.execute('CASE-1',{actorId:'ACT-1',submittedAt:'2026-01-11T15:00:00Z',action:{type:'ADD_MATERIAL',files:[{name:'Additional test material.pdf'}]}});
assert.ok(material.sources.some(source=>source.title==='Additional test material.pdf'));

// Uploading material never grants the creator-derived Case Owner authority.
const contributorAdapter=new SyntheticAdapter({actorId:'ACT-2'});
const contributorSession=await contributorAdapter.getSession();
assert.ok(contributorSession.actor.entitlements.includes('ADD_MATERIAL'));
assert.ok(!contributorSession.actor.entitlements.includes('ADOPT_FORMATION'));
await contributorAdapter.execute('CASE-1',{actorId:'ACT-2',submittedAt:'2026-01-11T15:30:00Z',action:{type:'ADD_MATERIAL',files:[{name:'Contributor note.pdf'}]}});
await assert.rejects(
  contributorAdapter.execute('CASE-1',{actorId:'ACT-2',submittedAt:'2026-01-11T16:00:00Z',action:{type:'ADOPT_FORMATION'}}),
  /Only the Case Owner/
);

console.log('Synthetic adapter behavior PASS');
