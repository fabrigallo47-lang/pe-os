import React, { useEffect, useRef, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import type { PantaRoute } from '../app/routes';
import { goTo, replaceRoute } from '../app/routes';
import { FindInCaseModal, SourceDrawer } from './Utilities';
import { caseLifecycleEntries } from './CaseLifecycle';
import type { Entitlement } from '../types/domain';
import { ObjectLens } from './ObjectLens';
import { useDialogFocus } from './useDialogFocus';
import { caseOwner, decisionCriticalQuestions, formatCount, isCaseUnformed } from '../app/selectors';
import { NewEmptyCase, NoCaseSelected } from './EmptyCase';

interface GlobalShellProps {
  route: PantaRoute;
  children: React.ReactNode;
  onStartNewCase?: () => void;
  onOpenExistingCase?: () => void;
}

export function GlobalShell({ route, children, onStartNewCase, onOpenExistingCase }: GlobalShellProps) {
  const {
    snapshot, cases, caseId, execute, focusedWorkstreamId, focusedQuestionId, openSource, actor,
    loading, error, refresh, pendingAction, simulationRunning, searching, inspecting, operationError, clearOperationError,
  } = usePanta();
  const [findOpen, setFindOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [caseFlowOpen, setCaseFlowOpen] = useState(false);
  const caseFlowRef = useRef<HTMLDivElement>(null);
  const caseFlowButtonRef = useRef<HTMLButtonElement>(null);
  const previousRoute = useRef(route);
  const caseName = snapshot?.caseRef.name ?? cases.find(item => item.id === caseId)?.name ?? 'New case';
  const caseOptions = cases.length ? cases : snapshot ? [{ id: snapshot.caseRef.id, name: snapshot.caseRef.name }] : [];
  const unformedCase = snapshot ? isCaseUnformed(snapshot) : false;
  const awaitingFirstMaterial = Boolean(snapshot && unformedCase && snapshot.sources.length === 0);
  const shellRoute: PantaRoute = unformedCase ? 'formation' : route;
  const owner = snapshot ? caseOwner(snapshot) : undefined;
  const decision = snapshot?.decision;
  const decisionIssueCount = snapshot ? decisionCriticalQuestions(snapshot).length : 0;
  const decisionStateSummary = decision?.status === 'RECORDED' ? 'Institutional decision recorded' : formatCount(decisionIssueCount, 'decision-critical issue');
  const decisionTiming = decision?.dueAt ? `Due ${formatDecisionDate(decision.dueAt)}` : 'Date not set';
  const workstream = snapshot?.workstreams.find(w => w.id === focusedWorkstreamId) ?? snapshot?.workstreams[0];
  const question = snapshot?.questions.find(t => t.id === focusedQuestionId) ?? snapshot?.questions.find(t => t.workstreamId === workstream?.id);
  const crumbs = getCrumbs(shellRoute, workstream?.name, question?.name);
  const currentRoom = crumbs.at(-1) ?? 'Deal Home';
  const roomContext = crumbs.slice(0, -1).join(' / ');
  const roomPath = crumbs.join(' / ');
  const can = (entitlement: Entitlement) => actor?.entitlements.includes(entitlement) ?? false;
  const lifecycle = snapshot && !unformedCase ? caseLifecycleEntries(snapshot, actor) : [];
  const pendingOutputChanges = snapshot?.artifacts.reduce((total, artifact) => total + artifact.pendingCaseChangeCount, 0) ?? 0;
  const globalLensRoute = shellRoute === 'trace' || shellRoute === 'simulate' || shellRoute === 'resolve' || shellRoute === 'formation' || shellRoute === 'replay' || shellRoute === 'journal';
  const backTarget: PantaRoute = shellRoute === 'workstream' ? 'deal' : shellRoute === 'trace' || shellRoute === 'simulate' || shellRoute === 'resolve' ? 'workstream' : 'deal';
  const backLabel = backTarget === 'workstream' ? 'Back to Workstream Focus' : 'Back to Deal Home';

  useEffect(() => {
    if (!caseFlowOpen) return;
    const closeOnPointerDown = (event: PointerEvent) => {
      if (!caseFlowRef.current?.contains(event.target as Node)) setCaseFlowOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setCaseFlowOpen(false);
        caseFlowButtonRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', closeOnPointerDown);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnPointerDown);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [caseFlowOpen]);

  useEffect(() => {
    if (previousRoute.current !== route) {
      document.getElementById('p-main-content')?.focus();
      previousRoute.current = route;
    }
  }, [route]);

  useEffect(() => {
    if (loading || error) return;
    if (!snapshot && route !== 'deal') {
      replaceRoute('deal', { caseId: undefined, workstreamId: undefined, questionId: undefined, asOf: undefined });
    } else if (unformedCase && route !== 'formation') {
      replaceRoute('formation', { workstreamId: undefined, questionId: undefined, asOf: undefined });
    }
  }, [error, loading, route, snapshot, unformedCase]);

  const navigate = (nextRoute: PantaRoute) => {
    setCaseFlowOpen(false);
    goTo(nextRoute);
  };

  const openFromCaseFlow = (open: () => void) => {
    setCaseFlowOpen(false);
    caseFlowButtonRef.current?.focus();
    window.requestAnimationFrame(open);
  };

  return <div className="p-shell">
    <a className="p-skip-link" href="#p-main-content">{snapshot ? 'Skip to case' : 'Skip to main content'}</a>
    <header className={`p-topbar ${!snapshot ? 'is-no-case' : unformedCase ? 'is-unformed-case' : ''}`}>
      <div className="p-top-left">
        <button className="p-brand-button" onClick={()=>goTo('deal')}><span className="p-brand-mark">P</span><span className="p-brand">PANTA</span></button>
        {snapshot ? <nav className="p-breadcrumb" aria-label="Current case and room">
          <label className="p-case-context">
            <span className="p-case-context-label">Current case</span>
            <span className="p-case-picker">
              <select className="p-case-select" aria-label="Switch current case" title={caseOptions.length > 1 ? 'Switch current case' : 'Current case · no other cases available'} value={caseId ?? snapshot?.caseRef.id ?? ''} disabled={!caseOptions.length} onChange={(e: React.ChangeEvent<HTMLSelectElement>) => goTo('deal', { caseId: e.target.value, asOf: undefined, workstreamId: undefined, questionId: undefined })}>
                {caseOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <span aria-hidden="true">⌄</span>
            </span>
          </label>
          <span className="p-shell-sequence" aria-hidden="true">›</span>
          <div className="p-room-context" title={roomPath}>
            <span className="p-room-context-label">Current room</span>
            <span className="p-room-path">
              {roomContext && <><span className="p-room-parent">{roomContext}</span><span className="p-room-sep" aria-hidden="true">/</span></>}
              <strong aria-current="page">{currentRoom}</strong>
            </span>
          </div>
        </nav> : !loading ? <div className="p-case-context is-empty" aria-label="Current case: no case selected">
          <span className="p-case-context-label">Current case</span>
          <span className="p-case-empty-value">No case selected</span>
        </div> : null}
      </div>
      {snapshot && !unformedCase && <div className="p-top-right">
        {decision && <button className="p-decision p-decision-link" title="Open Replay & Decision" aria-label={`Open Decision desk for ${decision.label}. ${decisionStateSummary}. ${decisionTiming}.`} onClick={() => navigate('replay')}>
          <span className="p-decision-label">Decision context <em>{decisionTiming}</em></span>
          <strong>{decision.label}</strong>
          <small><span>{decisionStateSummary}</span><b>Open →</b></small>
        </button>}
        <div className="p-shell-utilities" role="group" aria-label="Case utilities">
          {route !== 'outputs' && <button className="p-shell-link p-desktop-action" onClick={() => navigate('outputs')}>Outputs</button>}
          <button className="p-shell-link p-desktop-action" data-object-lens-return onClick={() => openSource(undefined)}>Sources</button>
          <div className="p-shell-menu" ref={caseFlowRef}>
            <button
              ref={caseFlowButtonRef}
              data-object-lens-return
              className="p-btn p-shell-menu-trigger"
              aria-label="Open case rooms navigation"
              aria-haspopup="true"
              aria-expanded={caseFlowOpen}
              aria-controls="case-flow-menu"
              onClick={() => setCaseFlowOpen(value => !value)}
            ><span className="p-case-flow-label">Case rooms</span><span className="p-case-flow-short">Rooms</span><span aria-hidden="true">⌄</span></button>
            {caseFlowOpen && <nav id="case-flow-menu" className="p-shell-menu-popover" aria-label="Case rooms navigation">
              <button className="p-shell-menu-item p-shell-mobile-item" aria-current={route === 'outputs' ? 'page' : undefined} onClick={() => navigate('outputs')}>
                <span><strong>Outputs</strong><small>{pendingOutputChanges ? `${pendingOutputChanges} case change${pendingOutputChanges === 1 ? '' : 's'} waiting to sync` : 'Connected work products'}</small></span>
              </button>
              <button className="p-shell-menu-item p-shell-mobile-item" onClick={() => openFromCaseFlow(() => openSource(undefined))}>
                <span><strong>Sources</strong><small>{snapshot ? `${formatCount(snapshot.sources.length,'source')} mapped` : 'No case loaded'}</small></span>
              </button>
              <button className="p-shell-menu-item p-shell-mobile-item" onClick={() => openFromCaseFlow(() => setFindOpen(true))}>
                <span><strong>Find in case</strong><small>Readings, sources, numbers, people, and events</small></span>
              </button>
              <button className="p-shell-menu-item p-shell-mobile-item" disabled={!can('ADD_MATERIAL') || Boolean(pendingAction)} onClick={() => openFromCaseFlow(() => setAddOpen(true))}>
                <span><strong>Add material</strong><small>{can('ADD_MATERIAL') ? 'Add governed case material' : 'Requires Add material authority'}</small></span>
              </button>
              <button className="p-shell-menu-item" aria-current={route === 'journal' ? 'page' : undefined} onClick={() => navigate('journal')}>
                <span><strong>Case changes</strong><small>Recorded timeline and differences between case states</small></span><em>{route === 'journal' ? 'Current' : 'Open'}</em>
              </button>
              {lifecycle.map(entry => <button key={entry.route} className="p-shell-menu-item" aria-current={route === entry.route ? 'page' : undefined} onClick={() => navigate(entry.route)}>
                <span><strong>{entry.label}</strong><small>{entry.precondition}</small></span><em>{entry.state}</em>
              </button>)}
              {!snapshot && <div className="p-shell-menu-empty">Load a case to see its governed lifecycle.</div>}
            </nav>}
          </div>
          <button className="p-btn p-desktop-action" data-object-lens-return onClick={() => setFindOpen(true)}>Find in case</button>
          <button className="p-btn p-btn-primary p-desktop-action" disabled={!can('ADD_MATERIAL') || Boolean(pendingAction)} title={!can('ADD_MATERIAL')?'Requires Add material entitlement':undefined} onClick={() => setAddOpen(true)}>Add material</button>
        </div>
      </div>}
    </header>
    {(pendingAction || simulationRunning || searching || inspecting || operationError) && <div className="p-async-feedback" aria-live="polite" aria-atomic="true">
      {(pendingAction || simulationRunning || searching || inspecting) && <div role="status"><span className="p-progress-mark" aria-hidden="true"/>{pendingAction ? actionProgressLabel(pendingAction) : simulationRunning ? 'Running the mapped impact trace…' : searching ? 'Searching the case…' : 'Opening case object…'}</div>}
      {operationError && <div className="p-operation-error" role="alert"><span>{operationError}</span><button onClick={clearOperationError}>Dismiss</button></div>}
    </div>}
    <div id="p-main-content" tabIndex={-1} aria-busy={loading || Boolean(pendingAction) || simulationRunning || searching || inspecting}>
      {snapshot && !unformedCase && shellRoute !== 'deal' && <div className="p-context-back"><button className="p-shell-link" onClick={() => goTo(backTarget)}>← {backLabel}</button></div>}
      {loading
        ? <CaseLoading caseName={caseName}/>
        : error
          ? <CaseLoadError message={error} onRetry={() => void refresh()}/>
          : !snapshot
            ? <NoCaseSelected cases={cases} onStartNewCase={onStartNewCase} onOpenExistingCase={onOpenExistingCase} onSelectCase={id => goTo('deal', { caseId: id, workstreamId: undefined, questionId: undefined, asOf: undefined })}/>
            : awaitingFirstMaterial
              ? <NewEmptyCase caseName={snapshot.caseRef.name} ownerName={owner?.displayName} canAddMaterial={can('ADD_MATERIAL')} adding={pendingAction === 'ADD_MATERIAL'} onAddMaterial={() => setAddOpen(true)}/>
              : children}
    </div>
    {snapshot && !unformedCase && globalLensRoute && <div className="p-floating-lens"><ObjectLens /></div>}
    {snapshot && findOpen && <FindInCaseModal onClose={() => setFindOpen(false)} />}
    {snapshot && addOpen && <AddMaterialModal submitting={pendingAction === 'ADD_MATERIAL'} onClose={() => setAddOpen(false)} onSubmit={async files => { if (await execute({ type: 'ADD_MATERIAL', files })) setAddOpen(false); }} />}
    <SourceDrawer />
  </div>;
}

function getCrumbs(route: PantaRoute, workstream?: string, question?: string): string[] {
  if (route === 'deal') return ['Deal Home'];
  if (route === 'workstream') return [workstream, 'Workstream Focus'].filter(Boolean) as string[];
  if (route === 'trace' || route === 'simulate' || route === 'resolve') return [workstream, question, route === 'trace' ? 'Trace' : route === 'simulate' ? 'Simulate' : 'Resolve'].filter(Boolean) as string[];
  if (route === 'review') return ['Review changes'];
  if (route === 'formation') return ['Formation'];
  if (route === 'replay') return ['Replay & Decision'];
  if (route === 'journal') return ['Case changes'];
  if (route === 'outputs') return ['Outputs'];
  return [];
}

function AddMaterialModal({ onClose, onSubmit, submitting }: { onClose: () => void; onSubmit: (files: File[]) => Promise<void>; submitting: boolean }) {
  const [files, setFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useDialogFocus<HTMLDivElement>(true, onClose, inputRef);
  return <div className="p-modal-backdrop"><div ref={dialogRef} tabIndex={-1} className="p-modal" role="dialog" aria-modal="true" aria-labelledby="add-material-title">
    <div className="p-modal-head"><strong id="add-material-title">Add material</strong><button className="p-btn p-btn-quiet" onClick={onClose}>Close</button></div>
    <div className="p-modal-body"><p className="p-muted">Decks, emails, transcripts, models, expert notes and other deal material enter through the same governed intake.</p><label className="p-field-label" htmlFor="add-material-files">Case material</label><input ref={inputRef} id="add-material-files" type="file" multiple disabled={submitting} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFiles(Array.from(e.target.files ?? []))}/><div className="p-action-row" style={{marginTop:18}}><button className="p-btn p-btn-primary" disabled={!files.length || submitting} onClick={() => void onSubmit(files)}>{submitting ? 'Adding material…' : `Add ${files.length ? `${files.length} item${files.length>1?'s':''}` : 'material'}`}</button><button className="p-btn" disabled={submitting} onClick={onClose}>Cancel</button></div></div>
  </div></div>;
}
function formatDecisionDate(v:string){try{return new Intl.DateTimeFormat('en',{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(v));}catch{return v}}

function CaseLoading({ caseName }: { caseName: string }) {
  return <main className="p-page p-load-state" role="status" aria-live="polite"><div><span className="p-progress-mark" aria-hidden="true"/><div><strong>Loading {caseName}</strong><p>Rebuilding the case view from the authoritative record.</p></div></div></main>;
}

function CaseLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <main className="p-page p-load-state p-load-error" role="alert"><div><div><strong>This case could not be loaded</strong><p>The previous case has been cleared so it cannot be mistaken for the selected case.</p><small>{message}</small></div><button className="p-btn" onClick={onRetry}>Try again</button></div></main>;
}

function actionProgressLabel(action: string): string {
  if (action === 'ADD_MATERIAL') return 'Adding material to the case…';
  if (action === 'REVIEW_ITEM') return 'Updating the institutional case…';
  if (action === 'RECORD_DECISION') return 'Recording the institutional decision…';
  if (action.includes('ARTIFACT') || action.includes('SYNC')) return 'Updating the connected output…';
  if (action.includes('FORMATION')) return 'Updating the case structure…';
  return 'Updating the case…';
}
