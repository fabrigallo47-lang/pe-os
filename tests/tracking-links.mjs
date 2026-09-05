import assert from 'node:assert/strict';
import { trackingLinks, projectionInspection } from '../src/app/trackingLinks.ts';

const snapshot = {
  caseRef: { id: 'TEST' }, caseVersion: 'v2',
  sources: [{ id: 'DOC' }], sourceVersions: [{ id: 'OLD', sourceId: 'DOC' }, { id: 'NEW', sourceId: 'DOC' }],
  claims: [{ id: 'CLAIM', sourceVersionId: 'OLD' }, { id: 'NEW-CLAIM', sourceVersionId: 'NEW' }],
  quantities: [{ id: 'FORMULA', sourceObjectIds: ['CLAIM', 'MISSING'] }], metricObservations: [],
  caseReadings: [], humanPositions: [{ id: 'VIEW', scopeObjectId: 'QUESTION' }],
  decisions: [{ id: 'DECISION', basisObjectIds: ['VIEW'], caseVersion: 'v2' }, { id: 'HISTORICAL', basisObjectIds: ['VIEW'], caseVersion: 'v1' }],
  artifactBlocks: [{ id: 'SENTENCE', boundObjectIds: ['DECISION'] }],
  relations: [
    { id: 'SUPPORT', caseId: 'TEST', sourceObjectId: 'FORMULA', targetObjectId: 'VIEW', type: 'SUPPORTS', institutionalState: 'CURRENT' },
    { id: 'CANDIDATE', caseId: 'TEST', sourceObjectId: 'CLAIM', targetObjectId: 'VIEW', type: 'SUPPORTS', institutionalState: 'CANDIDATE' },
    { id: 'FOREIGN', caseId: 'ANOTHER', sourceObjectId: 'CLAIM', targetObjectId: 'DECISION', type: 'SUPPORTS', institutionalState: 'CURRENT' },
    { id: 'CHALLENGE', caseId: 'TEST', sourceObjectId: 'NEW-CLAIM', targetObjectId: 'VIEW', type: 'CHALLENGES', institutionalState: 'CURRENT' },
    { id: 'OLD-BASIS', caseId: 'TEST', sourceObjectId: 'HISTORICAL', targetObjectId: 'VIEW', type: 'ADOPTS', institutionalState: 'CURRENT' },
  ],
};
const before = structuredClone(snapshot);
const path = ['DOC', 'OLD', 'CLAIM', 'FORMULA', 'VIEW', 'DECISION', 'SENTENCE'];
for (let i = 1; i < path.length; i++) {
  for (const [from, to] of [[path[i - 1], path[i]], [path[i], path[i - 1]]]) {
    assert.ok(trackingLinks(snapshot, from).some(link => link.objectId === to && link.available), `${from} → ${to}`);
  }
}
assert.ok(!trackingLinks(snapshot, 'NEW').some(link => link.objectId === 'CLAIM'), 'Old citation never moves to the new version');
assert.ok(!trackingLinks(snapshot, 'CLAIM').some(link => ['VIEW', 'DECISION'].includes(link.objectId)), 'Candidate/foreign edges never become current connections');
assert.equal(trackingLinks(snapshot, 'FORMULA').find(link => link.objectId === 'MISSING').available, false);
assert.equal(trackingLinks(snapshot, 'HISTORICAL').find(link => link.objectId === 'VIEW').available, false, 'Old decision basis cannot open newer current content');
assert.ok(trackingLinks(snapshot, 'HISTORICAL').every(link => !link.available), 'An additional relation cannot bypass the frozen decision version');
assert.equal(trackingLinks(snapshot, 'NEW-CLAIM').find(link => link.objectId === 'VIEW').label, 'Challenges');
assert.equal(projectionInspection(snapshot, 'UNKNOWN'), null);
assert.deepEqual(projectionInspection(snapshot, 'FORMULA').supportObjectIds, [], 'Navigation is not inferred causal support');
assert.equal(projectionInspection(snapshot, 'CLAIM').sourceLocators[0].sourceVersionId, 'OLD');
assert.deepEqual(projectionInspection(snapshot, 'CLAIM').allowedActions, ['OPEN_SOURCE'], 'Only an existing readable source is exposed; no mutation permissions are inferred');
const many = structuredClone(snapshot);
many.claims.push(...Array.from({ length: 10 }, (_, i) => ({ id: `EXTRA-${i}`, sourceVersionId: 'OLD' })));
assert.equal(trackingLinks(many, 'OLD').filter(link => link.label === 'Statement in this version').length, 11);
assert.deepEqual(snapshot, before, 'Inspection never mutates the case, person or decision');
console.log('Tracking links PASS — complete chain both ways, versions, missing refs, candidate isolation, challenge direction, no mutation');
