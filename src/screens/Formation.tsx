import React, { useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { actorById, caseOwner, caseReadingById, formatCount, questionById, unknownById, workItemById } from '../app/selectors';
import { goTo } from '../app/routes';
import type { PantaCaseSnapshot, Source, Unknown, Workstream } from '../types/domain';

function sourceTypeLabel(source: Source) {
  return source.type.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}

function questionsForWorkstream(snapshot: PantaCaseSnapshot, workstream: Workstream) {
  const ordered = workstream.questionIds.map(id => questionById(snapshot, id)).filter((question): question is NonNullable<typeof question> => Boolean(question));
  const listedIds = new Set(ordered.map(question => question.id));
  return [...ordered, ...snapshot.questions.filter(question => question.workstreamId === workstream.id && !listedIds.has(question.id))];
}

function gapNextStep(snapshot: PantaCaseSnapshot, gap: Unknown) {
  if (gap.resolutionPath) return gap.resolutionPath;
  const workItem = gap.workItemIds?.map(id => workItemById(snapshot, id)).find(item => item && item.status !== 'CANCELLED');
  return workItem?.whatToObtain ?? workItem?.name;
}

export function Formation() {
  const { snapshot, execute, setActiveObject, actor, pendingAction } = usePanta();
  const [selectedMaterialId, setSelectedMaterialId] = useState<string>();
  const [editing, setEditing] = useState(false);
  const [names, setNames] = useState<Record<string, string>>({});
  const [premise, setPremise] = useState<string>();

  if (!snapshot) return <EmptyCase />;
  const draft = snapshot.formation;
  if (!draft) return <main className="p-page p-zero-state p-formation-pending"><section>
    <div className="p-kicker">Formation</div>
    <h1>PANTA is preparing the initial case</h1>
    <p>{formatCount(snapshot.sources.length, 'material')} received. Proposed workstreams, questions, initial readings, and anything still open will appear here when the first structure is ready.</p>
    <div className="p-formation-pending-status"><span>Current state</span><strong>Material received · structure not yet proposed</strong></div>
  </section></main>;

  const formationMaterials = snapshot.formationMaterials ?? [];
  const materials = draft.materialIds.map(id => snapshot.sources.find(source => source.id === id)).filter((source): source is Source => Boolean(source));
  const workstreams = draft.proposedWorkstreamIds.map(id => snapshot.workstreams.find(workstream => workstream.id === id)).filter((workstream): workstream is Workstream => Boolean(workstream));
  const openGaps = draft.blindSpotUnknownIds.map(id => unknownById(snapshot, id)).filter((gap): gap is Unknown => Boolean(gap && gap.status === 'OPEN'));
  const activeMaterialId = selectedMaterialId && materials.some(material => material.id === selectedMaterialId) ? selectedMaterialId : materials[0]?.id;
  const activeMaterial = materials.find(material => material.id === activeMaterialId);
  const activeFormationMaterial = formationMaterials.find(material => material.sourceId === activeMaterialId);
  const mappedWorkstreamIds = new Set(activeFormationMaterial?.mappedWorkstreamIds ?? []);

  const owner = caseOwner(snapshot);
  const isCaseOwner = Boolean(owner && actor?.actorId === owner.id);
  const canAdopt = isCaseOwner && Boolean(actor?.entitlements.includes('ADOPT_FORMATION'));
  const isDraft = draft.status === 'PROPOSED_NOT_LIVE';
  const busy = Boolean(pendingAction);

  const saveEdits = async () => {
    const saved = await execute({
      type: 'CORRECT_FORMATION',
      patch: { premise: premise ?? draft.premise, workstreamNames: names },
    });
    if (saved) {
      setEditing(false);
      setNames({});
      setPremise(undefined);
    }
  };

  const cancelEdits = () => {
    setEditing(false);
    setNames({});
    setPremise(undefined);
  };

  const openResolve = (gap: Unknown) => {
    const question = gap.targetObjectIds.map(id => questionById(snapshot, id)).find(Boolean);
    goTo('resolve', { workstreamId: question?.workstreamId, questionId: question?.id });
  };

  return <main className="p-page p-formation-page">
    <section className="p-formation-head">
      <div>
        <div className="p-kicker">Formation</div>
        <h1 className="p-title">From raw material to a live investment case</h1>
        <p>PANTA has assembled the first coherent case from the material received. Review the structure, edit it if needed, then make it live.</p>
      </div>
      <div className={`p-formation-state ${isDraft ? 'is-draft' : 'is-live'}`}>
        <span>{isDraft ? 'Draft structure' : 'Live case'}</span>
        <strong>{formatCount(materials.length, 'material')} → {formatCount(workstreams.length, 'workstream')}</strong>
        <small>{formatCount(openGaps.length, 'item')} still open</small>
      </div>
    </section>

    <ol className="p-formation-journey" aria-label="Formation journey">
      <li className="is-complete"><span>1</span><div><strong>Raw materials</strong><small>{formatCount(materials.length, 'source')} received</small></div></li>
      <li className="is-complete"><span>2</span><div><strong>PANTA assembles</strong><small>Deal archetype + fund lenses</small></div></li>
      <li className={isDraft ? 'is-current' : 'is-complete'}><span>3</span><div><strong>Proposed case</strong><small>Workstreams, questions and readings</small></div></li>
      <li className={isDraft ? '' : 'is-complete'}><span>4</span><div><strong>Case Owner adopts</strong><small>{owner?.displayName ?? 'Owner not established'}</small></div></li>
      <li className={isDraft ? '' : 'is-current'}><span>5</span><div><strong>Case goes live</strong><small>{isDraft ? 'Ready after adoption' : 'Initial structure is live'}</small></div></li>
    </ol>

    <section className="p-formation-control" aria-label="Case structure approval">
      <div>
        <span className="p-kicker">Case ownership</span>
        <strong>{owner ? `${owner.displayName} · Case Owner` : 'Case Owner not established'}</strong>
        <p>The person who created this case can edit and adopt its initial structure. Adding material does not transfer that authority.</p>
      </div>
      {isDraft ? <div className="p-action-row">
        {editing ? <>
          <button className="p-btn p-btn-primary" disabled={!isCaseOwner || busy} onClick={() => void saveEdits()}>{pendingAction === 'CORRECT_FORMATION' ? 'Saving…' : 'Save edits'}</button>
          <button className="p-btn" disabled={busy} onClick={cancelEdits}>Cancel</button>
        </> : <>
          <button className="p-btn" disabled={!isCaseOwner || busy} title={!isCaseOwner ? 'Only the Case Owner can edit the initial structure.' : undefined} onClick={() => setEditing(true)}>Edit structure</button>
          <button className="p-btn p-btn-primary" disabled={!canAdopt || busy} title={!canAdopt ? 'Only the Case Owner with adoption authority can make this structure live.' : undefined} onClick={() => void execute({ type: 'ADOPT_FORMATION' })}>{pendingAction === 'ADOPT_FORMATION' ? 'Adopting…' : 'Adopt case structure'}</button>
        </>}
      </div> : <strong className="p-formation-live-note">Initial case structure is live</strong>}
    </section>

    <section className="p-formation-stage" aria-label="Case assembly">
      <aside className="p-formation-inputs">
        <div className="p-section-heading"><strong>What PANTA received</strong><span>{formatCount(materials.length, 'material')}</span></div>
        <div className="p-material-stack">
          {materials.map(material => {
            const materialProjection = formationMaterials.find(item => item.sourceId === material.id);
            const contributionCount = materialProjection?.mappedWorkstreamIds.length ?? 0;
            const selected = material.id === activeMaterialId;
            return <article key={material.id} className={selected ? 'is-selected' : undefined}>
              <button className="p-material-select" aria-pressed={selected} disabled={busy} onClick={() => setSelectedMaterialId(material.id)}>
                <span>{sourceTypeLabel(material)}</span>
                <strong>{material.title}</strong>
                {material.excerpt && <p>{material.excerpt}</p>}
                <small>{contributionCount ? `Feeds ${formatCount(contributionCount, 'workstream')}` : 'Not yet placed'}</small>
              </button>
              <button className="p-material-inspect" disabled={busy} onClick={() => void setActiveObject(material.id)}>Inspect source</button>
            </article>;
          })}
        </div>
      </aside>

      <div className="p-formation-transform" aria-live="polite">
        <span aria-hidden="true">→</span>
        <strong>PANTA applies</strong>
        <small>Deal archetype</small>
        <small>Fund lenses</small>
        {activeMaterial && <p><b>{activeMaterial.title}</b> contributes to {formatCount(mappedWorkstreamIds.size, 'proposed workstream')}.</p>}
      </div>

      <section className="p-formation-case-canvas">
        <header>
          <div>
            <span className="p-kicker">Proposed case</span>
            {editing ? <label className="p-formation-premise-edit"><span>Investment premise</span><textarea className="p-input" value={premise ?? draft.premise ?? ''} onChange={event => setPremise(event.target.value)} /></label> : <h2>{draft.premise ?? 'Initial investment case'}</h2>}
          </div>
          <span>{activeMaterial ? `Showing where “${activeMaterial.title}” contributed` : 'Select a material to see its contribution'}</span>
        </header>
        <div className="p-formation-workstreams">
          {workstreams.map((workstream, index) => {
            const questions = questionsForWorkstream(snapshot, workstream);
            const fallbackReading = caseReadingById(snapshot, workstream.currentCaseReadingId);
            const contributingSources = formationMaterials
              .filter(material => material.mappedWorkstreamIds.includes(workstream.id))
              .map(material => snapshot.sources.find(source => source.id === material.sourceId))
              .filter((source): source is Source => Boolean(source));
            const linked = mappedWorkstreamIds.has(workstream.id);
            const workstreamScopeIds = new Set([workstream.id, ...questions.map(question => question.id)]);
            const workstreamOpenCount = openGaps.filter(gap => workstream.openUnknownIds.includes(gap.id) || gap.targetObjectIds.some(id => workstreamScopeIds.has(id))).length;
            return <article key={workstream.id} className={`${linked ? 'is-material-linked' : ''} ${activeMaterialId && !linked ? 'is-muted' : ''}`}>
              <div className="p-formation-workstream-head">
                <span>{String(index + 1).padStart(2, '0')}</span>
                {editing ? <label><span className="p-field-label">Workstream name</span><input className="p-inline-edit" value={names[workstream.id] ?? workstream.name} onChange={event => setNames(current => ({ ...current, [workstream.id]: event.target.value }))} /></label> : <strong>{workstream.name}</strong>}
              </div>
              <div className="p-formation-question-list">
                {questions.length ? questions.map(question => {
                  const reading = caseReadingById(snapshot, question.currentCaseReadingId);
                  return <section key={question.id}>
                    <p className="p-formation-question">{question.name}</p>
                    <button className="p-formation-reading" disabled={!reading || busy} onClick={() => reading && void setActiveObject(reading.id)}>
                      <span>Initial reading</span>
                      <strong>{reading?.text ?? 'No reading established yet.'}</strong>
                    </button>
                  </section>;
                }) : <section>
                  <p className="p-formation-question">No questions proposed yet.</p>
                  <button className="p-formation-reading" disabled={!fallbackReading || busy} onClick={() => fallbackReading && void setActiveObject(fallbackReading.id)}>
                    <span>Workstream reading</span>
                    <strong>{fallbackReading?.text ?? 'No reading established yet.'}</strong>
                  </button>
                </section>}
              </div>
              <div className="p-formation-provenance"><span>Built from</span><p>{contributingSources.map(source => source.title).join(' · ') || 'No material mapped yet'}</p></div>
              <div className="p-formation-open-count"><span>{formatCount(workstreamOpenCount, 'item')} still open</span></div>
            </article>;
          })}
        </div>
      </section>
    </section>

    <section className="p-still-open">
      <header className="p-section-heading"><div><span className="p-kicker">Still open</span><strong>What the initial case does not yet answer</strong></div><span>{formatCount(openGaps.length, 'item')}</span></header>
      {openGaps.length ? <div className="p-still-open-grid">{openGaps.map(gap => {
        const owner = actorById(snapshot, gap.ownerActorId);
        const nextStep = gapNextStep(snapshot, gap);
        const difficult = gap.materiality === 'HIGH' || gap.workItemIds?.some(id => workItemById(snapshot, id)?.status === 'BLOCKED');
        return <article key={gap.id}>
          <div><span>What is missing</span><strong>{gap.title}</strong></div>
          <div><span>Working on it</span><p>{owner?.displayName ?? 'No owner yet'}</p></div>
          <div><span>Next practical step</span><p>{nextStep ?? 'Not yet defined'}</p></div>
          {difficult && <div className="p-action-row"><button className="p-btn" disabled={busy} onClick={() => openResolve(gap)}>Take to Resolve</button></div>}
        </article>;
      })}</div> : <p className="p-formation-all-clear">No open items remain in the proposed structure.</p>}
      <p className="p-still-open-note">As new evidence closes a gap, this list updates automatically. Resolve is available when a difficult gap needs a designed evidence path; it is not a required step.</p>
    </section>
  </main>;
}
