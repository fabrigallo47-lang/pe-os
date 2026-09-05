import assert from 'node:assert/strict';
import { SyntheticAdapter } from './synthetic-adapter.mjs';
import { emptyAdapter } from '../src/providers/emptyAdapter.ts';
import {
  composeLens,
  dealWorkstreamSummary,
  decisionCriticalQuestions,
  supportSummary,
  humanPositionsForScope,
  eventDisplayLabel,
  formatCount,
  formatRemaining,
  workItemDisplayState,
  quantityDisplayState,
  normalizeSimulationEffects,
  objectStateTokens,
  recordedDecision,
  relationshipNarrative,
  simulationImpactCounts,
} from '../src/app/selectors.ts';
import { buildRouteHash, parseRouteLocation } from '../src/app/routes.ts';
import { journalRequestPath, projectCaseJournal, projectJournalStates } from '../src/providers/journalProjection.ts';

// The Product Lab No-case mode is the production adapter's literal null-case projection.
const emptySession = await emptyAdapter.getSession();
assert.deepEqual(emptySession.actors, []);
assert.deepEqual(await emptyAdapter.listCases(), []);
assert.equal(await emptyAdapter.loadCase(), null);
assert.deepEqual(await emptyAdapter.listCaseMoments('CASE-NONE'), []);
assert.equal(await emptyAdapter.loadJournal('CASE-NONE'), null);
assert.deepEqual(await emptyAdapter.listJournalStates('CASE-NONE'), []);
assert.equal(await emptyAdapter.inspectObject('CASE-NONE', 'OBJECT-NONE'), null);
assert.deepEqual(await emptyAdapter.searchCase('CASE-NONE', 'anything'), []);
assert.equal(await emptyAdapter.runSimulation('CASE-NONE', {
  optionId: 'OPTION-NONE',
  originObjectId: 'OBJECT-NONE',
  assumption: 'No case exists',
}), null);
assert.equal(await emptyAdapter.execute('CASE-NONE', {
  actorId: emptySession.actor.actorId,
  submittedAt: '2026-01-01T00:00:00Z',
  action: { type: 'ADOPT_FORMATION' },
}), null);

const adapter = new SyntheticAdapter();
const snapshot = await adapter.loadCase('CASE-1');
assert.ok(snapshot);
const replayMoments = await adapter.listCaseMoments('CASE-1');
assert.deepEqual(replayMoments.map(moment=>moment.label),['Case created','Customer reference admitted','Technical reading changed']);
assert.ok(replayMoments.every(moment=>moment.eventId));
const decisionQuestions = decisionCriticalQuestions(snapshot);
assert.equal(decisionQuestions.length,4);
assert.ok(decisionQuestions.every(question=>question.decisionDimensions&&!('score' in question.decisionDimensions)));
const historicalSnapshot = await adapter.loadCase('CASE-1', { asOf: '2026-01-10T12:00:00Z' });
const creationSnapshot = await adapter.loadCase('CASE-1', { asOf: replayMoments[0].asOf });
assert.equal(creationSnapshot.workstreams.length,snapshot.workstreams.length);
assert.equal(creationSnapshot.questions.length,0);
assert.equal(creationSnapshot.unknowns.length,0);
assert.ok(creationSnapshot.caseReadings.every(reading=>reading.epistemicStatus==='UNEXAMINED'));
assert.ok(creationSnapshot.workstreams.every(workstream=>workstream.openUnknownIds.length===0));
const technicalWorkstream = snapshot.workstreams.find(item => item.id === 'WS-1');
const technicalSummary = dealWorkstreamSummary(snapshot, technicalWorkstream);
assert.equal(technicalSummary.reading?.id, 'CR-1');
assert.equal(technicalSummary.openPoint?.id, 'U-1');
assert.equal(technicalSummary.nextStep?.id, 'WI-1');
assert.equal(technicalSummary.owner?.id, 'ACT-2');
assert.equal(technicalSummary.latestChange?.id, 'EV-3');
assert.ok(eventDisplayLabel(snapshot, technicalSummary.latestChange).startsWith('Reading updated'));
assert.equal(dealWorkstreamSummary(historicalSnapshot, historicalSnapshot.workstreams.find(item => item.id === 'WS-1')).latestChange, undefined);
const summaryWithInactiveWork = dealWorkstreamSummary({
  ...snapshot,
  workItems: [
    { ...snapshot.workItems[0], id: 'WI-COMPLETE', status: 'COMPLETED' },
    { ...snapshot.workItems[0], id: 'WI-RETIRED', status: 'ACTIVE', institutionalState: 'RETIRED' },
    ...snapshot.workItems,
  ],
}, { ...technicalWorkstream, activeWorkItemIds: ['WI-COMPLETE', 'WI-RETIRED', 'WI-1'] });
assert.equal(summaryWithInactiveWork.nextStep?.id, 'WI-1');
assert.equal(dealWorkstreamSummary(snapshot, { ...technicalWorkstream, ownerActorId: 'ACT-NOT-LOADED' }).owner, undefined);

const reading = snapshot.caseReadings[0];
const support = supportSummary(snapshot, reading);
assert.equal(support.total, 2);
assert.equal(support.independent, 1);
const withoutIndependentSupport = supportSummary(snapshot, { ...reading, supportObjectIds: ['CL-2'] });
assert.deepEqual(withoutIndependentSupport, { total: 1, independent: 0, labels: ['Performance claim'] });
assert.equal(formatCount(0, 'place'), '0 places');
assert.equal(formatCount(1, 'place'), '1 place');
assert.equal(formatCount(3, 'place'), '3 places');
assert.equal(formatRemaining(0, 'support'), '0 supports remain');
assert.equal(formatRemaining(1, 'support'), '1 support remains');
assert.equal(formatRemaining(2, 'support'), '2 supports remain');

const deepLink = buildRouteHash('trace', { caseId: 'CASE-1', workstreamId: 'WS-1', questionId: 'Q-1', asOf: '2026-01-11T10:00:00Z' });
assert.equal(deepLink, '#/trace?caseId=CASE-1&workstreamId=WS-1&questionId=Q-1&asOf=2026-01-11T10%3A00%3A00Z');
assert.deepEqual(parseRouteLocation(deepLink), { route: 'trace', context: { caseId: 'CASE-1', workstreamId: 'WS-1', questionId: 'Q-1', asOf: '2026-01-11T10:00:00Z' } });
assert.equal(buildRouteHash('journal',{caseId:'CASE-1'}),'#/journal?caseId=CASE-1');
assert.equal(parseRouteLocation('#/journal?caseId=CASE-1').route,'journal');
assert.equal(journalRequestPath('CASE 1',{since:'2026-01-01',asOf:'2026-01-11',workstream:'WS-1',closeStateId:'STATE-1'}),'/api/v20/cases/CASE%201/journal?since=2026-01-01&as_of_date=2026-01-11&workstream=WS-1&close_state_id=STATE-1');
const projectedJournal=projectCaseJournal({
  schema_version:'case-journal/1.0',case_id:'CASE-1',generated_at:'2026-01-11T10:01:00Z',
  temporal:{effective_axis:'effective_date',knowledge_axis:'known_at',recording_axis:'recorded_at',since:null,until:null,as_of:null},
  baseline:{state_id:'STATE-1',version_id:'STATE-1',known_at:'2026-01-10T10:00:00Z',effective_date:'2026-01-10',graph_hash:'sha256:one'},
  current:{state_id:'STATE-2',version_id:'STATE-2',known_at:'2026-01-11T10:00:00Z',effective_date:'2026-01-11',graph_hash:'sha256:two'},
  event_count:1,event_kinds:{EVIDENCE:1},events:[{schema_version:'case-journal-event/1.0',journal_id:'sha256:event',event_id:'EV-1',case_id:'CASE-1',event_type:'EVIDENCE_ADMITTED',kind:'EVIDENCE',phase:'DILIGENCE',label:'Evidence admitted',actor_id:'ACT-1',actor_label:'Mara Bellini',actor_source:'DECLARED',effective_date:'2026-01-10',known_at:'2026-01-10T14:00:00Z',recorded_at:'2026-01-10T14:00:03Z',object_ids:['CL-1'],workstream_ids:['WS-1'],correlation_ids:[],source:'RUNTIME_LEDGER',integrity:{}}],
  summary:{rules_version:'journal-change-rules/1.1',change_count:0,advanced:0,regressed:0,changed:0,opened:0,closed:0,workstreams:[],changes:[]},
  drift:{status:'UNAVAILABLE',reason:'No closing state selected.'},
  integrity:{sources:['RUNTIME_LEDGER'],runtime_ledger_is_primary_for_admissions_and_settlements:true,inferred_system_actor_count:0,warnings:[]},
});
assert.equal(projectedJournal.events[0].knownAt,'2026-01-10T14:00:00Z');
assert.equal(projectedJournal.baseline.stateId,'STATE-1');
assert.deepEqual(projectJournalStates({versions:[{kind:'CANDIDATE',state_id:'C',version_id:'C'},{kind:'CURRENT',state_id:'STATE-1',version_id:'STATE-1',known_at:'2026-01-10T10:00:00Z'}]}).map(state=>state.stateId),['STATE-1']);
assert.throws(()=>projectCaseJournal({...projectedJournal,schema_version:'case-journal/2.0'}),/Unsupported Case Journal schema/);

const inspection = await adapter.inspectObject('CASE-1', reading.id);
assert.ok(inspection);
const lens = composeLens(snapshot, inspection);
assert.equal(lens.supportCount, 2);
assert.equal(lens.independentCount, 1);
assert.equal(lens.unknowns.length, 1);
assert.equal(lens.dependents.length, 1);
assert.equal(lens.dependents[0].label, 'Can customer acquisition become repeatable?');
assert.ok(lens.lastChange?.label.startsWith('Reading updated'));
assert.equal(relationshipNarrative(snapshot,'CR-1','Q-C'),'The ability to prove production performance shapes whether the commercial route can become repeatable.');
assert.deepEqual(objectStateTokens(snapshot,'CR-1').map(token=>token.axis),['Freshness','Evidence']);
assert.deepEqual(objectStateTokens(snapshot,'HP-1').map(token=>token.axis),['Position']);
const actorInspection = await adapter.inspectObject('CASE-1', 'ACT-2');
const actorLens = composeLens(snapshot, actorInspection);
assert.deepEqual(actorLens.dependents.map(item => item.label), ['Product & Technical Proof']);
assert.deepEqual(actorLens.unknowns.map(item => item.label), ['Named budget owner and renewal logic across the target buyer set', 'Evidence that the workflow advantage survives incumbent bundling']);

const views = humanPositionsForScope(snapshot, ['Q-1', reading.id]);
assert.equal(views.length, 1);
assert.equal(views[0].authorActorId, 'ACT-1');
assert.ok(!('epistemicStatus' in views[0]));

assert.equal(eventDisplayLabel(snapshot, snapshot.events[0]), 'Reading updated · ' + reading.text);
assert.equal(workItemDisplayState(snapshot.workItems[0]), 'Unassigned');
assert.equal(quantityDisplayState(snapshot.quantities[0]), 'Current');

// Decision views follow the explicit context link, even when another decision is newer.
snapshot.decisions = [
  { id: 'DEC-REFERRED', pathId: 'PATH-1', actorOrBodyId: 'ACT-1', rationale: 'Linked decision', recordedAt: '2026-01-11T10:00:00Z', caseVersion: 'v1' },
  { id: 'DEC-NEWER', pathId: 'PATH-1', actorOrBodyId: 'ACT-1', rationale: 'Newer unlinked decision', recordedAt: '2026-01-12T10:00:00Z', caseVersion: 'v2' },
];
snapshot.decision.status = 'RECORDED';
snapshot.decision.recordedDecisionId = 'DEC-REFERRED';
assert.equal(recordedDecision(snapshot)?.id, 'DEC-REFERRED');
delete snapshot.decision.recordedDecisionId;
assert.equal(recordedDecision(snapshot)?.id, 'DEC-NEWER');
snapshot.decision.status = 'OPEN';
assert.equal(recordedDecision(snapshot), undefined);

// Simulation counts and rendered rows share one normalized collection.
const simulation = await adapter.runSimulation('CASE-1', { optionId: 'SIM-1', originObjectId: 'CR-1', assumption: 'Representative test fails' });
const normalizedEffects = normalizeSimulationEffects([
  ...simulation.effects,
  { objectId: 'CR-1', objectLabel: 'Duplicate reading', state: 'HOLDS', before: 'Unproven', after: 'Unproven', reasonRelationIds: [] },
]);
const impactCounts = simulationImpactCounts(normalizedEffects);
assert.equal(normalizedEffects.length, 3);
assert.equal(normalizedEffects.find(effect => effect.objectId === 'CR-1')?.state, 'WEAKENS');
assert.deepEqual(impactCounts, { total: 3, changed: 2, held: 1 });

console.log('Frontend projection behavior PASS');
