import React, { useEffect, useRef, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { useDialogFocus } from './useDialogFocus';
import { formatCount } from '../app/selectors';
import { SourceEvidence } from './SourceEvidence';
import type { SourceDocument } from '../providers/sourceDocuments';

export function FindInCaseModal({ onClose }: { onClose: () => void }) {
  const { search, searching, searchResults, setActiveObject } = usePanta();
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useDialogFocus<HTMLDivElement>(true, onClose, inputRef);
  useEffect(() => {
    const timer = window.setTimeout(() => { void search(query); }, 140);
    return () => window.clearTimeout(timer);
  }, [query, search]);

  const inspectResult = (objectId: string) => {
    onClose();
    window.requestAnimationFrame(() => { void setActiveObject(objectId); });
  };

  return <div className="p-modal-backdrop"><div ref={dialogRef} tabIndex={-1} className="p-modal p-command-modal" role="dialog" aria-modal="true" aria-labelledby="find-in-case-title">
    <div className="p-modal-head"><strong id="find-in-case-title">Find in case</strong><button className="p-btn p-btn-quiet" onClick={onClose}>Close</button></div>
    <div className="p-modal-body">
      <label className="p-field-label" htmlFor="find-in-case-input">Reading, source, number, person, or event</label>
      <input ref={inputRef} id="find-in-case-input" className="p-search-input" placeholder="Search the current case" value={query} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} aria-describedby="find-in-case-status" />
      <div id="find-in-case-status" className="p-search-status" role="status" aria-live="polite">{searching ? 'Searching the case…' : query ? `${searchResults.length} result${searchResults.length === 1 ? '' : 's'}` : 'Start typing to search'}</div>
      <div className="p-search-results" aria-busy={searching}>{searchResults.map(result => <button key={result.objectId} disabled={searching} onClick={() => inspectResult(result.objectId)}><strong>{result.label}</strong><span>{result.kind}</span></button>)}{query && !searching && !searchResults.length && <p className="p-muted">No matching case object.</p>}</div>
    </div>
  </div></div>;
}

export function SourceDrawer() {
  const { snapshot, sourcesOpen, selectedSourceId, selectedSourceLocator, closeSources, openSource, setActiveObject, inspecting } = usePanta();
  const selectionKey = JSON.stringify([snapshot?.caseRef.id, snapshot?.asOf, selectedSourceId, selectedSourceLocator]);
  const [reader, setReader] = useState<{ key: string; document: SourceDocument }>();
  const original = sourcesOpen && reader?.key === selectionKey ? reader.document : undefined;
  const readerBackRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (!sourcesOpen) setReader(undefined); }, [sourcesOpen]);
  useEffect(() => { if (original) readerBackRef.current?.focus(); }, [original]);
  const dialogRef = useDialogFocus<HTMLElement>(sourcesOpen, closeSources);
  const sourceBackRef = useRef<HTMLButtonElement>(null);
  const firstSourceRef = useRef<HTMLButtonElement>(null);
  const previousSourceId = useRef<string>();
  useEffect(() => {
    if (!sourcesOpen || previousSourceId.current === selectedSourceId) return;
    const hadSelection = Boolean(previousSourceId.current);
    previousSourceId.current = selectedSourceId;
    const timer = window.setTimeout(() => (selectedSourceId ? sourceBackRef.current : hadSelection ? firstSourceRef.current : null)?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [selectedSourceId, sourcesOpen]);
  if (!snapshot || !sourcesOpen) return null;
  const source = selectedSourceId ? snapshot.sources.find(item => item.id === selectedSourceId) : undefined;

  const inspectSource = () => {
    if (!source || inspecting) return;
    const sourceId = source.id;
    closeSources();
    window.requestAnimationFrame(() => { void setActiveObject(sourceId); });
  };

  return <div className="p-drawer-backdrop" onMouseDown={(event: React.MouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget) closeSources(); }}><aside ref={dialogRef} tabIndex={-1} className={`p-source-drawer ${original ? 'p-source-reader-drawer' : ''}`} role="dialog" aria-modal="true" aria-labelledby="source-drawer-title">
    <div className="p-modal-head"><div><strong id="source-drawer-title">{source?.title ?? 'Sources'}</strong><div className="p-meta">{source ? source.type : `${formatCount(snapshot.sources.length,'source')} mapped`}</div></div><button className="p-btn p-btn-quiet" onClick={closeSources}>Close</button></div>
    {original ? <div className="p-source-reader">
      <div className="p-source-reader-toolbar"><button ref={readerBackRef} className="p-shell-link" onClick={() => { setReader(undefined); window.requestAnimationFrame(() => sourceBackRef.current?.focus()); }}>← Back to source details</button><a className="p-shell-link" href={original.downloadUrl} download>Download original</a></div>
      <p className="p-source-reader-position" role="status">{original.position.label}{original.position.status === 'UNRESOLVED' && ' · No verified passage selection'}</p>
      <iframe title={`Original document: ${original.filename}`} src={original.viewUrl} sandbox="allow-same-origin allow-downloads" />
    </div> : selectedSourceId ? <div className="p-source-detail">
      <button ref={sourceBackRef} className="p-shell-link p-source-back" onClick={() => openSource(undefined)}>← Back to all sources</button>
      {source?.occurredAt && <p className="p-meta">Dated {source.occurredAt}</p>}
      <SourceEvidence target={selectedSourceLocator ?? { sourceId: selectedSourceId }} onOpenOriginal={document => setReader({ key: selectionKey, document })} />
      {!selectedSourceLocator && source?.limitation && <div className="p-source-limit"><span>What this doesn't prove</span><p>{source.limitation}</p></div>}
      {source && <button className="p-btn p-btn-primary" disabled={inspecting} onClick={inspectSource}>{inspecting ? 'Opening inspection…' : 'Inspect in case'}</button>}
    </div> : <div className="p-source-list">{snapshot.sources.map((item,index) => <button ref={index===0?firstSourceRef:undefined} key={item.id} className="p-source-item" onClick={() => openSource(item.id)}><span className="p-meta">{item.type}</span><strong>{item.title}</strong>{item.excerpt && <p>“{item.excerpt}”</p>}{item.limitation && <small>Doesn't prove: {item.limitation}</small>}<span className="p-source-open-cue">Open source →</span></button>)}</div>}
  </aside></div>;
}

export function SourcesModal() {
  const { openSource } = usePanta();
  useEffect(() => { openSource(undefined); }, [openSource]);
  return null;
}
