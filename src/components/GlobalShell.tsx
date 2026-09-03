import React, { useState } from 'react';
import { usePanta } from '../app/PantaContext';
import type { PantaRoute } from '../app/routes';
import { goTo } from '../app/routes';
import { FindInCaseModal, SourceDrawer } from './Utilities';
import type { Entitlement } from '../types/domain';

export function GlobalShell({ route, children }: { route: PantaRoute; children: React.ReactNode }) {
  const { snapshot, cases, caseId, setCase, execute, focusedWorkstreamId, focusedQuestionId, openSource, actor } = usePanta();
  const [findOpen, setFindOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const caseName = snapshot?.caseRef.name ?? 'New case';
  const decision = snapshot?.decision;
  const workstream = snapshot?.workstreams.find(w => w.id === focusedWorkstreamId) ?? snapshot?.workstreams[0];
  const question = snapshot?.questions.find(t => t.id === focusedQuestionId) ?? snapshot?.questions.find(t => t.workstreamId === workstream?.id);
  const crumbs = getCrumbs(route, workstream?.name, question?.name);
  const can = (entitlement: Entitlement) => actor?.entitlements.includes(entitlement) ?? false;

  return <div className="p-shell">
    <header className="p-topbar">
      <div className="p-top-left">
        <button className="p-brand-button" onClick={()=>goTo('deal')}><span className="p-brand-mark">P</span><span className="p-brand">PANTA</span></button>
        {route !== 'deal' && <><span className="p-shell-divider"/><button className="p-shell-link" onClick={() => history.back()}>‹ Back</button></>}
        <nav className="p-breadcrumb" aria-label="Breadcrumb">
          {cases.length > 1 ? <select className="p-case-select" aria-label="Case" value={caseId ?? ''} onChange={(e: React.ChangeEvent<HTMLSelectElement>) => { void setCase(e.target.value); goTo('deal'); }}>
            {cases.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select> : <button className="p-shell-link p-case-name" onClick={() => goTo('deal')}>{caseName}</button>}
          {crumbs.map((c, i) => <React.Fragment key={`${c}-${i}`}><span className="p-sep">/</span><span>{c}</span></React.Fragment>)}
        </nav>
      </div>
      <div className="p-top-right">
        {decision && <span className="p-decision">Decision: {decision.label}{decision.dueAt ? ` · ${formatDecisionDate(decision.dueAt)}` : ''}</span>}
        {route !== 'outputs' && <button className="p-shell-link" onClick={() => goTo('outputs')}>Outputs</button>}
        <button className="p-shell-link" onClick={() => openSource(undefined)}>Sources</button>
        <button className="p-btn" onClick={() => setFindOpen(true)}>Find in case</button>
        <button className="p-btn p-btn-primary" disabled={!can('ADD_MATERIAL')} title={!can('ADD_MATERIAL')?'Requires Add material entitlement':undefined} onClick={() => setAddOpen(true)}>Add material</button>
      </div>
    </header>
    {children}
    {findOpen && <FindInCaseModal onClose={() => setFindOpen(false)} />}
    {addOpen && <AddMaterialModal onClose={() => setAddOpen(false)} onSubmit={async files => { await execute({ type: 'ADD_MATERIAL', files }); setAddOpen(false); }} />}
    <SourceDrawer />
  </div>;
}

function getCrumbs(route: PantaRoute, workstream?: string, question?: string): string[] {
  if (route === 'deal') return [];
  if (route === 'workstream') return workstream ? [workstream] : ['Workstream'];
  if (route === 'trace' || route === 'simulate' || route === 'resolve') return [workstream, question, route === 'trace' ? 'Trace' : route === 'simulate' ? 'Simulate' : 'Resolve'].filter(Boolean) as string[];
  if (route === 'review') return ['Review & Admit'];
  if (route === 'formation') return ['Formation'];
  if (route === 'replay') return ['Replay & Decision'];
  if (route === 'outputs') return ['Outputs'];
  return [];
}

function AddMaterialModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (files: File[]) => Promise<void> }) {
  const [files, setFiles] = useState<File[]>([]);
  return <div className="p-modal-backdrop" role="dialog" aria-modal="true"><div className="p-modal">
    <div className="p-modal-head"><strong>Add material</strong><button className="p-btn p-btn-quiet" onClick={onClose}>Close</button></div>
    <div className="p-modal-body"><p className="p-muted">Decks, emails, transcripts, models, expert notes and other deal material enter through the same governed intake.</p><input type="file" multiple onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFiles(Array.from(e.target.files ?? []))}/><div className="p-action-row" style={{marginTop:18}}><button className="p-btn p-btn-primary" disabled={!files.length} onClick={() => void onSubmit(files)}>Add {files.length ? `${files.length} item${files.length>1?'s':''}` : 'material'}</button><button className="p-btn" onClick={onClose}>Cancel</button></div></div>
  </div></div>;
}
function formatDecisionDate(v:string){try{return new Intl.DateTimeFormat('en',{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(v));}catch{return v}}
