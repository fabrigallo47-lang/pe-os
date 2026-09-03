import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { objectLabel } from '../app/selectors';

export function FindInCaseModal({ onClose }: { onClose: () => void }) {
  const { search, searchResults, setActiveObject } = usePanta();
  const [query, setQuery] = useState('');
  useEffect(()=>{const t=setTimeout(()=>void search(query),140);return()=>clearTimeout(t)},[query,search]);
  return <div className="p-modal-backdrop" role="dialog" aria-modal="true"><div className="p-modal p-command-modal">
    <div className="p-modal-head"><strong>Find in case</strong><button className="p-btn p-btn-quiet" onClick={onClose}>Close</button></div>
    <div className="p-modal-body"><input autoFocus className="p-search-input" placeholder="Find a reading, source, number, person or event" value={query} onChange={(e: React.ChangeEvent<HTMLInputElement>)=>setQuery(e.target.value)} />
      <div className="p-search-results">{searchResults.map(r=><button key={r.objectId} onClick={()=>{void setActiveObject(r.objectId);onClose()}}><strong>{r.label}</strong><span>{r.kind}</span></button>)}{query && !searchResults.length&&<p className="p-muted">No matching case object.</p>}</div>
    </div>
  </div></div>;
}

export function SourceDrawer() {
  const { snapshot, sourcesOpen, selectedSourceId, closeSources, setActiveObject } = usePanta();
  if (!snapshot || !sourcesOpen) return null;
  const sources = selectedSourceId ? snapshot.sources.filter(s=>s.id===selectedSourceId) : snapshot.sources;
  return <div className="p-drawer-backdrop" onMouseDown={(e: React.MouseEvent<HTMLDivElement>)=>{if(e.target===e.currentTarget)closeSources()}}><aside className="p-source-drawer">
    <div className="p-modal-head"><div><strong>{selectedSourceId ? 'Source' : 'Sources'}</strong><div className="p-meta">{sources.length} mapped</div></div><button className="p-btn p-btn-quiet" onClick={closeSources}>Close</button></div>
    <div className="p-source-list">{sources.map(s=><button key={s.id} className="p-source-item" onClick={()=>void setActiveObject(s.id)}><span className="p-meta">{s.type}</span><strong>{s.title}</strong>{s.excerpt&&<p>“{s.excerpt}”</p>}{s.limitation&&<small>Doesn't prove: {s.limitation}</small>}</button>)}</div>
  </aside></div>;
}

export function SourcesModal({ onClose }: { onClose: () => void }) {
  const { openSource } = usePanta();
  useEffect(()=>{openSource(undefined); return ()=>{}},[openSource]);
  return <></>;
}
