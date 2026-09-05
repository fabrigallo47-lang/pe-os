import React, { useEffect, useRef, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { resolveSourceEvidence, sourceLocatorForClaim } from '../app/sourceEvidence';
import type { SourceLocator } from '../types/domain';
import type { SourceDocument } from '../providers/sourceDocuments';
import '../design/source-evidence.css';

export function SourceEvidence({ target, onOpenOriginal }: { target: SourceLocator; onOpenOriginal?: (document: SourceDocument) => void }) {
  const { snapshot, openSource } = usePanta();
  if (!snapshot) return null;
  const evidence = resolveSourceEvidence(snapshot, target);
  if (evidence.issue) return <p role="alert" className="p-source-evidence-issue">{evidence.issue}</p>;
  const { claim, version, versionId, locator, excerpt, historical } = evidence;
  const statements = snapshot.claims.flatMap(item => {
    const ref = sourceLocatorForClaim(snapshot, item);
    return ref?.sourceId === target.sourceId && (!versionId || ref.sourceVersionId === versionId) ? [{ claim: item, ref }] : [];
  });
  return <section className="p-source-evidence" aria-label="Source evidence">
    {claim && <div className="p-source-statement"><span className="p-field-label">{evidence.frozen ? 'Statement saved with the output' : 'Statement in the case'}</span><p>{claim.normalizedStatement || claim.label}</p></div>}
    <dl className="p-source-citation">
      {evidence.source?.origin && <div><dt>Origin</dt><dd>{evidence.source.origin}</dd></div>}
      <div><dt>Source location</dt><dd>{locator || 'Exact location not supplied'}</dd></div>
      {versionId && <div><dt>Cited version</dt><dd>{versionId}{historical && <small>Earlier version · preserved as cited</small>}{!version && <small>Version details unavailable</small>}</dd></div>}
      {version?.knownAt && <div><dt>Known since</dt><dd>{version.knownAt}</dd></div>}
    </dl>
    {excerpt ? <><span className="p-field-label">{claim ? 'Cited passage' : 'Source excerpt'}</span><blockquote>“{excerpt}”</blockquote></> : <p className="p-muted">{claim || evidence.exact ? 'The cited passage text is not available.' : 'No excerpt is available for this source.'}</p>}
    {claim?.limitation && <div className="p-source-limit"><span>What this doesn't prove</span><p>{claim.limitation}</p></div>}
    {onOpenOriginal && <OriginalDocumentButton key={JSON.stringify([snapshot.caseRef.id, snapshot.asOf, target, versionId, locator])} target={{ ...target, sourceVersionId: versionId, locator }} onOpen={onOpenOriginal} />}
    {!!statements.length && <div className="p-source-statements"><h3>{versionId ? 'Statements from this version' : 'Statements from this source'}</h3>{statements.map(item => <button key={item.claim.id} type="button" aria-pressed={item.claim.id === claim?.id} onClick={() => openSource(item.ref)}><strong>{item.claim.label}</strong><span>{item.ref.locator || 'Exact location not supplied'}</span></button>)}</div>}
  </section>;
}

function OriginalDocumentButton({ target, onOpen }: { target: SourceLocator; onOpen: (document: SourceDocument) => void }) {
  const { adapter, snapshot } = usePanta();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const available = Boolean(adapter.loadSourceDocument && target.sourceVersionId);
  async function open() {
    if (!snapshot || !adapter.loadSourceDocument || pending || !available) return;
    setPending(true);
    setError('');
    try {
      const document = await adapter.loadSourceDocument(snapshot.caseRef.id, target);
      if (mounted.current) onOpen(document);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : 'The original document could not be opened.');
    } finally { if (mounted.current) setPending(false); }
  }
  return <div className="p-source-original-action">
    <button type="button" className="p-btn p-btn-primary" disabled={!available || pending} onClick={() => { void open(); }}>{pending ? 'Checking original…' : 'Open original'}</button>
    {pending && <p className="p-meta" role="status">Verifying the cited file and location…</p>}
    {!available && <p className="p-meta">The original cannot be opened without its cited version.</p>}
    {error && <p role="alert" className="p-source-evidence-issue">{error}</p>}
  </div>;
}
