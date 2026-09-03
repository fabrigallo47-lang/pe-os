import assert from 'node:assert/strict';
import { SyntheticAdapter } from './synthetic-adapter.mjs';
import {
  composeLens,
  supportSummary,
  humanPositionsForScope,
  eventDisplayLabel,
  workItemDisplayState,
  quantityDisplayState,
} from '../src/app/selectors.ts';

const adapter = new SyntheticAdapter();
const snapshot = await adapter.loadCase('CASE-1');
assert.ok(snapshot);

const reading = snapshot.caseReadings[0];
const support = supportSummary(snapshot, reading);
assert.equal(support.total, 2);
assert.equal(support.independent, 1);

const inspection = await adapter.inspectObject('CASE-1', reading.id);
assert.ok(inspection);
const lens = composeLens(snapshot, inspection);
assert.equal(lens.supportCount, 2);
assert.equal(lens.independentCount, 1);
assert.equal(lens.unknowns.length, 1);
assert.equal(lens.dependents.length, 1);
assert.ok(lens.lastChange?.label.startsWith('Reading updated'));

const views = humanPositionsForScope(snapshot, ['Q-1', reading.id]);
assert.equal(views.length, 1);
assert.equal(views[0].authorActorId, 'ACT-1');
assert.ok(!('epistemicStatus' in views[0]));

assert.equal(eventDisplayLabel(snapshot, snapshot.events[0]), 'Reading updated · ' + reading.text);
assert.equal(workItemDisplayState(snapshot.workItems[0]), 'Unassigned');
assert.equal(quantityDisplayState(snapshot.quantities[0]), 'Current');

console.log('Frontend projection behavior PASS');
