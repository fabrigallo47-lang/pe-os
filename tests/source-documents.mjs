import assert from 'node:assert/strict';
import { fetchSourceDocument, sourceDocumentRequestPath, withSourceDocuments } from '../src/providers/sourceDocuments.ts';
import { SyntheticAdapter } from './synthetic-adapter.mjs';

const target = { sourceId: 'SRC-1', sourceVersionId: 'sha256:' + 'a'.repeat(64), claimId: 'CL-1', locator: "file.xlsx::'A & B'!C12:D12" };
const path = sourceDocumentRequestPath('CASE-1', target);
const query = path.split('?')[1];
const data = { schema_version: 'source-document/1.0', case_id: 'CASE-1', source_id: target.sourceId, source_version_id: target.sourceVersionId, locator: target.locator, filename: 'file.xlsx', position: {kind: 'workbook', status: 'LOCATED', label: 'A & B!C12:D12'}, view_url: '/api/v20/cases/CASE-1/source-document/view?' + query + '#selection', download_url: '/api/v20/cases/CASE-1/source-document/file?' + query + '&download=true' };
const options = payload => ({ baseUrl: 'https://panta.test', fetchImpl: async url => {
  assert.equal(url, 'https://panta.test' + path);
  return new Response(JSON.stringify(payload), { status: 200 });
} });
const result = await fetchSourceDocument('CASE-1', target, options(data));
assert.equal(result.position.label, 'A & B!C12:D12');
assert.equal(new URL(result.viewUrl).searchParams.get('locator'), target.locator);
assert.throws(() => sourceDocumentRequestPath('CASE-1', { sourceId: 'SRC-1' }), /version/);

for (const patch of [
  { case_id: 'OTHER' }, { source_id: 'OTHER' }, { source_version_id: 'LATEST' }, { locator: 'D99' },
  { schema_version: 'other/1.0' }, { position: { ...data.position, status: 'GUESSED' } },
  { view_url: 'https://outside.test' + data.view_url },
  { view_url: 'javascript:alert(1)' },
  { view_url: data.view_url.replace('CASE-1', 'CASE-2') },
  { view_url: data.view_url.replace('claim_id=CL-1', 'claim_id=CL-2') },
  { view_url: data.view_url.replace('#selection', '&source_id=OTHER') },
  { download_url: data.download_url.replace('source_id=SRC-1', 'source_id=OTHER') },
]) await assert.rejects(fetchSourceDocument('CASE-1', target, options({ ...data, ...patch })));
await assert.rejects(fetchSourceDocument('CASE-1', target, {baseUrl:'https://panta.test', fetchImpl:async()=>new Response(JSON.stringify({detail:'Version mismatch'}),{status:409})}), /Version mismatch/);
await assert.rejects(fetchSourceDocument('CASE-1', target, {baseUrl:'https://panta.test', fetchImpl:async()=>new Response('<html>') }), /unreadable/);

const adapter = new SyntheticAdapter();
const connected = withSourceDocuments(adapter, options(data));
assert.deepEqual(await connected.loadCase('CASE-1'), await adapter.loadCase('CASE-1'), 'Stateful receivers are preserved');
assert.equal((await connected.loadSourceDocument('CASE-1', target)).filename, 'file.xlsx');
adapter.loadSourceDocument = async function () { assert.equal(this, adapter); return result; };
assert.equal(await withSourceDocuments(adapter).loadSourceDocument('CASE-1', target), result, 'Explicit integration is preserved');
console.log('Source documents PASS — citation identity, trusted URLs, failures, full locator encoding, adapter receivers');
