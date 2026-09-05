import assert from 'node:assert/strict';
import { sourceLocatorForClaim, inspectionSourceLocators, resolveSourceEvidence } from '../src/app/sourceEvidence.ts';

const snapshot = {
  sources: [
    { id: 'DOCUMENT', title: 'Synthetic diligence report', currentVersionId: 'NEW', excerpt: 'Latest document overview', locator: 'document' },
    { id: 'WORKBOOK', title: 'Synthetic model', currentVersionId: 'MODEL' },
  ],
  sourceVersions: [
    { id: 'OLD', sourceId: 'DOCUMENT', knownAt: '2026-01-01' },
    { id: 'NEW', sourceId: 'DOCUMENT', knownAt: '2026-01-02' },
    { id: 'MODEL', sourceId: 'WORKBOOK', knownAt: '2026-01-01' },
  ],
  claims: [
    { id: 'STATEMENT', sourceVersionId: 'OLD', locator: 'p12:w40-64', normalizedStatement: 'A normalized proposition', verbatimOrLosslessSpan: 'The original cited words.', excerpt: 'A less precise excerpt' },
    { id: 'CELL', sourceId: 'WORKBOOK', sourceVersionId: 'MODEL', locator: "'Revenue Model'!C12:D12", normalizedStatement: 'A projected number' },
    { id: 'CALL', sourceId: 'DOCUMENT', sourceVersionId: 'OLD', locator: '00:12:34.500 --> 00:12:48.000', excerpt: 'A cited transcript segment' },
  ],
};
const original = structuredClone(snapshot);
const ref = sourceLocatorForClaim(snapshot, snapshot.claims[0]);
assert.equal(ref.sourceId, 'DOCUMENT', 'Source resolves through SourceVersion without a convenience sourceId');
const historical = resolveSourceEvidence(snapshot, ref);
assert.equal(historical.versionId, 'OLD');
assert.equal(historical.historical, true);
assert.equal(historical.locator, 'p12:w40-64');
assert.equal(historical.excerpt, 'The original cited words.');
assert.equal(historical.issue, undefined);

const cell = resolveSourceEvidence(snapshot, sourceLocatorForClaim(snapshot, snapshot.claims[1]));
assert.equal(cell.locator, "'Revenue Model'!C12:D12");
assert.equal(cell.excerpt, undefined, 'A normalized proposition is never presented as a source quotation');
const callRef = sourceLocatorForClaim(snapshot, snapshot.claims[2]);
assert.equal(resolveSourceEvidence(snapshot, callRef).locator, '00:12:34.500 --> 00:12:48.000');

for (const target of [
  { ...ref, sourceId: 'WORKBOOK' },
  { ...ref, sourceVersionId: 'NEW' },
  { ...ref, locator: 'p99' },
  { ...ref, claimId: 'MISSING' },
  { sourceId: 'MISSING' },
]) {
  const result = resolveSourceEvidence(snapshot, target);
  assert.ok(result.issue, 'Broken or inconsistent provenance must be visible');
  assert.equal(result.excerpt, undefined, 'No fallback excerpt may disguise a broken citation');
}
assert.equal(sourceLocatorForClaim(snapshot, { ...snapshot.claims[0], sourceId: 'WORKBOOK' }), undefined);
const noPassage = resolveSourceEvidence(snapshot, { sourceId: 'DOCUMENT', sourceVersionId: 'OLD' });
assert.equal(noPassage.excerpt, undefined, 'Never substitute a newer document excerpt for an older version');
assert.equal(noPassage.locator, undefined, 'A document location cannot impersonate a passage address');
assert.equal(resolveSourceEvidence(snapshot, { sourceId: 'DOCUMENT' }).excerpt, 'Latest document overview');
const noVersionDetails = resolveSourceEvidence({ ...snapshot, sourceVersions: [] }, ref);
assert.equal(noVersionDetails.versionId, 'OLD');
assert.equal(noVersionDetails.version, undefined);
assert.equal(noVersionDetails.excerpt, undefined, 'Unresolvable version lineage cannot be replaced by a caller-supplied source');
assert.ok(noVersionDetails.issue);
assert.equal(inspectionSourceLocators(snapshot, 'READING', [ref, callRef, ref]).length, 2, 'Keep distinct passages from the same source');
assert.deepEqual(inspectionSourceLocators(snapshot, 'STATEMENT', []), [ref]);
assert.deepEqual(inspectionSourceLocators(snapshot, 'STATEMENT', [{ sourceId: 'DOCUMENT', claimId: 'STATEMENT' }]), [ref]);
assert.deepEqual(snapshot, original, 'Evidence inspection never mutates the case');
console.log('Source evidence PASS — version lineage, exact addresses, quotations, missing references, multiple passages, immutable state');
