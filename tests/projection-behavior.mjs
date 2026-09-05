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
  recordedDecision,
  simulationImpactCounts,
} from '../src/app/selectors.ts';
import { buildRouteHash, parseRouteLocation } from '../src/app/routes.ts';

// The Product Lab No-case mode is the production adapter's literal null-case projection.
const emptySession = await emptyAdapter.getSession();
assert.deepEqual(emptySession.actors, []);
assert.deepEqual(await emptyAdapter.listCases(), []);
assert.equal(await emptyAdapter.loadCase(), null);
assert.deepEqual(await emptyAdapter.listCaseMoments('CASE-NONE'), []);
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

const inspection = await adapter.inspectObject('CASE-1', reading.id);
assert.ok(inspection);
const lens = composeLens(snapshot, inspection);
assert.equal(lens.supportCount, 2);
assert.equal(lens.independentCount, 1);
assert.equal(lens.unknowns.length, 1);
assert.equal(lens.dependents.length, 1);
assert.equal(lens.dependents[0].label, 'Can customer acquisition become repeatable?');
assert.ok(lens.lastChange?.label.startsWith('Reading updated'));
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
assert.equal(normalizedEffects.length, 2);
assert.equal(normalizedEffects.find(effect => effect.objectId === 'CR-1')?.state, 'WEAKENS');
assert.deepEqual(impactCounts, { total: 2, changed: 1, held: 1 });

console.log('Frontend projection behavior PASS');
