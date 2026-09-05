import React, { useCallback, useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ObjectLens } from '../components/ObjectLens';
import type { Artifact, ArtifactBlock } from '../types/domain';
import '../design/live-outputs.css';

const TABS = ['IC_MEMO', 'MODEL', 'DECISION_PACK', 'DECK', 'TRACKER'] as const;
type OutputTab = typeof TABS[number];
const labels = { IC_MEMO: 'IC Memo', MODEL: 'Model', DECISION_PACK: 'Decision Pack', DECK: 'Deck', TRACKER: 'Tracker' };

export function Outputs() {
  const { snapshot, execute, actor, pendingAction, setActiveObject, refresh, asOf } = usePanta();
  const [tab, setTab] = useState<OutputTab>('IC_MEMO');
  const [mode, setMode] = useState<'READ' | 'EDIT'>('READ');
  const [hasDrafts, setHasDrafts] = useState(false);
  if (!snapshot) return <EmptyCase />;
  const artifact = snapshot.artifacts.find(item => item.type === tab);
  const live = snapshot.outputCapabilities?.versioned === true;
  const busy = Boolean(pendingAction);
  const canEdit = !asOf && live && (actor?.entitlements.includes('EDIT_ARTIFACT') ?? false);
  const canSync = !asOf && live && (actor?.entitlements.includes('SYNC_ARTIFACT') ?? false);
  const hasPending = artifact?.blockIds.some(id => snapshot.artifactBlocks.find(block => block.id === id)?.suggestion);
  function select(next: OutputTab) { if (hasDrafts || busy) return; setTab(next); setMode('READ'); void setActiveObject(undefined); }
  function move(event: React.KeyboardEvent) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const index = TABS.indexOf(tab);
    const next = TABS[event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length];
    select(next); requestAnimationFrame(() => document.getElementById(`output-tab-${next}`)?.focus());
  }
  return <main className="p-page p-output-page">
    <header className="p-output-toolbar">
      <div className="p-output-tabs" role="tablist" aria-label="Outputs" onKeyDown={move}>{TABS.map(type => <button key={type} id={`output-tab-${type}`} role="tab" aria-selected={tab === type} aria-controls={`output-panel-${type}`} tabIndex={tab === type ? 0 : -1} className={tab === type ? 'is-active' : ''} disabled={hasDrafts || busy} onClick={() => select(type)}>{labels[type]}</button>)}</div>
      <div className="p-output-actions"><button className="p-btn" disabled={busy || hasDrafts} onClick={() => void refresh()}>Reload case</button>
        {artifact ? <button className="p-btn p-btn-accent" disabled={!canSync || busy || hasDrafts || Boolean(hasPending)} title={hasPending ? 'Review the pending proposals first.' : undefined} onClick={() => void execute({ type: 'SYNC_ARTIFACT', artifactId: artifact.id })}>{pendingAction === 'SYNC_ARTIFACT' ? 'Preparing updates…' : 'Review case updates'}</button> : <button className="p-btn p-btn-primary" disabled={!canEdit || busy} onClick={() => void execute({ type: 'CREATE_ARTIFACT', artifactType: tab })}>Create from case</button>}
        {artifact && <div className="p-segmented" aria-label="Output mode"><button aria-pressed={mode === 'READ'} className={mode === 'READ' ? 'is-active' : ''} disabled={busy || hasDrafts} onClick={() => setMode('READ')}>Read</button><button aria-pressed={mode === 'EDIT'} className={mode === 'EDIT' ? 'is-active' : ''} disabled={!canEdit || busy} onClick={() => setMode('EDIT')}>Edit</button></div>}
      </div>
    </header>
    {hasDrafts && <p className="p-output-notice" role="status">Save or cancel your passage edits before leaving Edit mode or approving.</p>}
    {!live && <p className="p-output-notice" role="status">Editing requires a connected output service with saved versions and review support.</p>}
    <div id={`output-panel-${tab}`} role="tabpanel" aria-labelledby={`output-tab-${tab}`} tabIndex={0}>
      {artifact ? <OutputSurface key={artifact.id} artifact={artifact} mode={mode} canEdit={canEdit} canSync={canSync} onDraftsChange={setHasDrafts} /> : <section className="p-empty"><div><h1>{labels[tab]}</h1><p>Create an initial draft from the case. Open questions stay visible, and every passage retains its basis.</p></div></section>}
    </div>
  </main>;
}

function OutputSurface({ artifact, mode, canEdit, canSync, onDraftsChange }: { artifact: Artifact; mode: 'READ' | 'EDIT'; canEdit: boolean; canSync: boolean; onDraftsChange: (dirty: boolean) => void }) {
  const { snapshot, execute, setActiveObject, inspection, pendingAction, actor, adapter, asOf } = usePanta();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [dirtyIds, setDirtyIds] = useState<Set<string>>(new Set());
  const onDirtyChange = useCallback((id: string, dirty: boolean) => setDirtyIds(previous => { const next = new Set(previous); if (dirty) next.add(id); else next.delete(id); return next; }), []);
  useEffect(() => onDraftsChange(dirtyIds.size > 0), [dirtyIds, onDraftsChange]);
  if (!snapshot) return null;
  const blocks = artifact.blockIds.flatMap(id => { const block = snapshot.artifactBlocks.find(b => b.id === id); return block ? [block] : []; });
  const pending = blocks.filter(block => block.suggestion).length;
  const busy = Boolean(pendingAction) || exporting;
  const approved = artifact.approvalStatus === 'APPROVED';
  const canApprove = !asOf && snapshot.outputCapabilities?.versioned && actor?.entitlements.includes('APPROVE_ARTIFACT') && artifact.canApprove && !approved;
  const writer = snapshot.outputCapabilities?.writerLabel;
  const canRedraft = canSync && snapshot.outputCapabilities?.aiRedraftAvailable && !pending && !artifact.pendingCaseChangeCount;
  async function download(format: 'html' | 'json' | 'csv') {
    if (!snapshot || !artifact.revisionId || !adapter.exportArtifact) return;
    setExporting(true); setExportError('');
    try {
      const result = await adapter.exportArtifact(snapshot.caseRef.id, artifact.id, artifact.revisionId, format);
      const url = URL.createObjectURL(result.blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = result.filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setExportError(error instanceof Error ? error.message : 'Export failed.'); }
    finally { setExporting(false); }
  }
  return <>
    <div className="p-output-status" role="status">
      <div><strong>{approved ? 'Approved version' : 'Draft for review'}</strong><span>{artifact.pendingCaseChangeCount ? `${artifact.pendingCaseChangeCount} passages need review against the current case` : 'Aligned with the current case'}{pending ? ` · ${pending} proposals to review` : ''}</span></div>
      <div className="p-action-row"><button className="p-btn" disabled={busy || dirtyIds.size > 0 || !canRedraft} title={!snapshot.outputCapabilities?.aiRedraftAvailable ? 'Configure the writing model on the server to request a draft.' : 'Editorial suggestions remain subject to your review.'} onClick={() => void execute({ type: 'REDRAFT_ARTIFACT', artifactId: artifact.id })}>{pendingAction === 'REDRAFT_ARTIFACT' ? 'Drafting…' : 'Suggest redraft'}</button><button className="p-btn p-btn-primary" disabled={busy || dirtyIds.size > 0 || mode === 'EDIT' || !canApprove} title={!artifact.canApprove ? 'Resolve missing basis and review every proposal before approving.' : 'Approve this work product, with your name and the current case version.'} onClick={() => void execute({ type: 'APPROVE_ARTIFACT', artifactId: artifact.id })}>Approve this version</button></div>
    </div>
    <div className={`p-output-stage ${inspection ? 'has-lens' : ''}`}>
      <article className={`p-memo-paper p-output-${artifact.type.toLowerCase()}`}>
        <header className="p-memo-title-block"><div><h1>{artifact.title}</h1><span>{artifact.type === 'MODEL' ? 'Recorded model values and calculations' : artifact.type === 'DECK' ? 'Presentation draft' : artifact.type === 'TRACKER' ? 'Open diligence and conditions' : 'Case-backed work product'}</span></div><div className="p-meta">{writer ? `Writing assistant · ${writer}` : 'Writing assistant not configured'}</div></header>
        <div className="p-memo-content">{blocks.map((block, index) => <MemoBlock key={`${block.id}-${block.text}`} onDirtyChange={onDirtyChange} block={block} index={index + 1} mode={mode} disabled={busy} canEdit={canEdit} onSelect={() => void setActiveObject(block.id)} onSave={text => execute({ type: 'UPDATE_ARTIFACT_BLOCK', artifactId: artifact.id, blockId: block.id, text })} onAccept={() => void execute({ type: 'ACCEPT_ARTIFACT_SUGGESTION', artifactId: artifact.id, blockId: block.id })} onDismiss={() => void execute({ type: 'DISMISS_ARTIFACT_SUGGESTION', artifactId: artifact.id, blockId: block.id })} />)}</div>
        <footer className="p-output-export"><p>{approved ? `Approved by ${snapshot.actors.find(a => a.id === artifact.approval?.actorId)?.displayName ?? artifact.approval?.actorId} · ${artifact.approval?.recordedAt}` : 'Review and approve this version to export it.'}</p><div className="p-action-row"><button className="p-btn" disabled={busy || dirtyIds.size > 0 || !approved || !adapter.exportArtifact} onClick={() => void download('html')}>Export HTML</button><button className="p-btn" disabled={busy || dirtyIds.size > 0 || !approved || !adapter.exportArtifact} onClick={() => void download('json')}>Export with full basis</button>{['MODEL', 'TRACKER'].includes(artifact.type) && <button className="p-btn" disabled={busy || dirtyIds.size > 0 || !approved || !adapter.exportArtifact} onClick={() => void download('csv')}>Export CSV</button>}</div><small>Approval applies to this work product. Investment decisions remain separately recorded in the case.</small>{exportError && <p role="alert">{exportError}</p>}</footer>
      </article>
      {inspection && <aside className="p-output-lens"><ObjectLens /></aside>}
    </div>
  </>;
}

function MemoBlock({ block, index, mode, disabled, canEdit, onSelect, onSave, onAccept, onDismiss, onDirtyChange }: { onDirtyChange: (id: string, dirty: boolean) => void; block: ArtifactBlock; index: number; mode: 'READ' | 'EDIT'; disabled: boolean; canEdit: boolean; onSelect: () => void; onSave: (text: string) => Promise<boolean>; onAccept: () => void; onDismiss: () => void }) {
  const [text, setText] = useState(block.text ?? '');
  const changed = text !== (block.text ?? '');
  useEffect(() => { onDirtyChange(block.id, changed); return () => onDirtyChange(block.id, false); }, [block.id, changed, onDirtyChange]);
  const editing = mode === 'EDIT' && !block.editorialLocked;
  return <section className={`p-memo-block ${block.authorship === 'HUMAN_AUTHORED' ? 'is-human' : ''}`}>
    <div className="p-memo-block-head"><span>{String(index).padStart(2, '0')}</span><strong>{block.title}</strong>{block.authorship === 'HUMAN_AUTHORED' && <small>Edited by a reviewer</small>}{block.authorship === 'PANTA_SUGGESTION' && <small>AI draft{block.reviewedBy ? ' · reviewed' : ''}</small>}{block.freshnessStatus && block.freshnessStatus !== 'CURRENT' && <em className="p-output-stale">{block.freshnessStatus === 'MISSING_BASIS' ? 'Basis missing' : 'Needs update'}</em>}</div>
    {editing ? <><textarea aria-label={`Edit ${block.title}`} className="p-memo-editor" disabled={disabled || !canEdit} value={text} onChange={event => setText(event.target.value)} /><div className="p-action-row"><button className="p-btn p-btn-accent" disabled={disabled || !canEdit || !changed || !text.trim()} onClick={() => void onSave(text)}>Save passage</button><button className="p-btn" disabled={disabled || !changed} onClick={() => setText(block.text ?? '')}>Cancel edit</button><button className="p-btn" onClick={onSelect}>Inspect basis</button></div></> : <button className="p-memo-sentence" onClick={onSelect}>{block.text ?? '—'}</button>}
    {block.editorialLocked && mode === 'EDIT' && <p className="p-meta">This attributed view is changed in the case, then updated here.</p>}
    {block.suggestion && <aside className="p-anchored-suggestion"><strong>{block.suggestion.signal}</strong><p><del>{block.text}</del></p><p><ins>{block.suggestion.suggestedText}</ins></p><div className="p-action-row"><button className="p-btn p-btn-accent" disabled={disabled || !canEdit} onClick={onAccept}>{block.suggestion.remove ? 'Accept removal' : 'Accept proposal'}</button><button className="p-btn" onClick={onSelect}>Inspect why</button><button className="p-btn p-btn-quiet" disabled={disabled || !canEdit} onClick={onDismiss}>Dismiss</button></div></aside>}
  </section>;
}
