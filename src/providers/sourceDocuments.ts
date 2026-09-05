import type { PantaBackendAdapter } from './PantaBackendAdapter';
import type { SourceLocator } from '../types/domain';

export interface SourceDocument {
  filename: string;
  viewUrl: string;
  downloadUrl: string;
  position: { kind: 'pdf' | 'workbook' | 'media' | 'text' | 'download' | 'image'; status: 'LOCATED' | 'UNRESOLVED'; label: string };
}

export interface SourceDocumentHttpOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export function sourceDocumentRequestPath(caseId: string, target: SourceLocator): string {
  if (!target.sourceVersionId) throw new Error('The cited source version is unavailable.');
  const query = new URLSearchParams({ source_id: target.sourceId, source_version_id: target.sourceVersionId });
  if (target.locator) query.set('locator', target.locator);
  if (target.claimId) query.set('claim_id', target.claimId);
  return '/api/v20/cases/' + encodeURIComponent(caseId) + '/source-document?' + query;
}

export async function fetchSourceDocument(caseId: string, target: SourceLocator, options: SourceDocumentHttpOptions = {}): Promise<SourceDocument> {
  const path = sourceDocumentRequestPath(caseId, target);
  const origin = options.baseUrl ?? globalThis.location?.origin;
  if (!origin) throw new Error('The original document service is unavailable.');
  const request = new URL(path, origin);
  const response = await (options.fetchImpl ?? fetch)(request.href, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
  let data;
  try { data = await response.json(); } catch { throw new Error('The original document service returned an unreadable response.'); }
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'The original document could not be opened.');
  if (data?.schema_version !== 'source-document/1.0' || data.case_id !== caseId || data.source_id !== target.sourceId || data.source_version_id !== target.sourceVersionId || data.locator !== (target.locator ?? '') || typeof data.filename !== 'string') {
    throw new Error('The returned document does not match the cited source and version.');
  }
  const position = data.position;
  if (!position || !['pdf', 'workbook', 'media', 'text', 'download', 'image'].includes(position.kind) || !['LOCATED', 'UNRESOLVED'].includes(position.status) || typeof position.label !== 'string') {
    throw new Error('The document location could not be verified.');
  }
  function verifiedUrl(value: unknown, action: 'view' | 'file') {
    if (typeof value !== 'string') throw new Error('The original document link is unavailable.');
    const url = new URL(value, request);
    if (url.origin !== request.origin || url.username || url.password || url.pathname !== request.pathname + '/' + action || url.searchParams.getAll('source_id').length !== 1 || url.searchParams.get('source_id') !== target.sourceId || url.searchParams.getAll('source_version_id').length !== 1 || url.searchParams.get('source_version_id') !== target.sourceVersionId || (action === 'view' && ((url.searchParams.get('locator') ?? '') !== (target.locator ?? '') || (url.searchParams.get('claim_id') ?? '') !== (target.claimId ?? '')))) {
      throw new Error('The original document link does not match the citation.');
    }
    return url.href;
  }
  return { filename: data.filename, position, viewUrl: verifiedUrl(data.view_url, 'view'), downloadUrl: verifiedUrl(data.download_url, 'file') };
}

/** Preserve adapter method receivers, including stateful adapters. */
export function withSourceDocuments(adapter: PantaBackendAdapter, options?: SourceDocumentHttpOptions): PantaBackendAdapter {
  return {
    getSession: adapter.getSession.bind(adapter),
    listCases: adapter.listCases.bind(adapter),
    loadCase: adapter.loadCase.bind(adapter),
    listCaseMoments: adapter.listCaseMoments.bind(adapter),
    loadJournal: adapter.loadJournal.bind(adapter),
    listJournalStates: adapter.listJournalStates.bind(adapter),
    inspectObject: adapter.inspectObject.bind(adapter),
    searchCase: adapter.searchCase.bind(adapter),
    runSimulation: adapter.runSimulation.bind(adapter),
    execute: adapter.execute.bind(adapter),
    loadSourceDocument: adapter.loadSourceDocument?.bind(adapter) ?? ((caseId, target) => fetchSourceDocument(caseId, target, options)),
  };
}
