import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ObjectLens } from '../components/ObjectLens';
import { ImpactTrace } from '../components/CausalTrace';
import { formatCount } from '../app/selectors';

export function ReviewAdmit(){
  const {snapshot,execute,setActiveObject,actor,pendingAction}=usePanta();
  const items=snapshot?.pendingReviews.filter(x=>x.status==='NEW'||x.status==='UNDER_REVIEW')??[];
  const [selectedId,setSelectedId]=useState(items[0]?.id);
  const item=items.find(x=>x.id===selectedId)??items[0];
  const [editing,setEditing]=useState(false);
  const [editedProposal,setEditedProposal]=useState(item?.proposedCaseReading.text??'');

  useEffect(()=>{
    if(item){
      setEditedProposal(item.proposedCaseReading.text);
      setEditing(false);
    }
  },[item?.id]);

  if(!snapshot)return <EmptyCase/>;
  if(!item)return <main className="p-page"><section className="p-empty"><div><div className="p-kicker">Exceptional review</div><h1>Review changes</h1><p>Nothing needs your judgment. PANTA has applied clear factual updates automatically.</p></div></section></main>;

  const canUpdate=actor?.entitlements.includes('ADMIT_CASE_READING')??false;
  const finding=item.findingId?snapshot.findings.find(value=>value.id===item.findingId):undefined;
  const source=item.sourceId?snapshot.sources.find(value=>value.id===item.sourceId):undefined;
  const changed=item.effectPreview.filter(effect=>effect.state!=='HOLDS');
  const primaryChange=changed.find(effect=>Boolean(effect.before||effect.after))??changed[0];
  const why=finding?.proposition
    ?? item.proposedCaseReading.supportingLine
    ?? (source?`PANTA found a material case impact in ${source.title}.`:'This proposal carries material judgment for the institutional case.');
  const currentText=primaryChange?.before??'No current institutional reading';
  const proposedText=editing?editedProposal:item.proposedCaseReading.text;
  const selectedIndex=Math.max(0,items.findIndex(value=>value.id===item.id));
  const act=(disposition:'ADMIT'|'CORRECT'|'REJECT')=>execute({
    type:'REVIEW_ITEM',
    reviewId:item.id,
    disposition,
    correctedText:disposition==='CORRECT'?editedProposal:undefined,
  });

  return <main className="p-page p-review-page">
    <header className="p-review-head">
      <div>
        <div className="p-kicker">Exceptional review</div>
        <h1>Review changes</h1>
        <p>Clear factual updates are already in the case. Only material, ambiguous, or judgment-bearing changes appear here.</p>
      </div>
      <span className="p-review-count">{formatCount(items.length,'change')} requiring judgment</span>
    </header>

    {items.length>1&&<nav className="p-review-queue" aria-label="Changes requiring review">
      {items.map((value,index)=><button key={value.id} aria-pressed={value.id===item.id} disabled={Boolean(pendingAction)} className={value.id===item.id?'is-selected':''} onClick={()=>setSelectedId(value.id)}><span>{String(index+1).padStart(2,'0')}</span>{value.title}</button>)}
    </nav>}

    <article className="p-review-change">
      <header className="p-review-change-head">
        <span>{String(selectedIndex+1).padStart(2,'0')} / {String(items.length).padStart(2,'0')}</span>
        <strong>Requires human judgment</strong>
      </header>

      <section className="p-review-proposal" aria-labelledby="review-proposal-title">
        <h2 id="review-proposal-title">What PANTA proposes to change</h2>
        <p>{item.title}</p>
      </section>

      <section className="p-review-why" aria-labelledby="review-why-title">
        <h2 id="review-why-title">Why</h2>
        <p>{why}</p>
      </section>

      <section className="p-review-diff" aria-labelledby="review-diff-title">
        <h2 id="review-diff-title">Current → Proposed</h2>
        <div className="p-review-diff-grid">
          <div><span>Current</span><p>{currentText}</p></div>
          <b aria-hidden="true">→</b>
          <div><span>Proposed</span>{editing?<><label className="p-visually-hidden" htmlFor="review-proposal-editor">Edit proposed case reading</label><textarea id="review-proposal-editor" className="p-review-editor" value={editedProposal} onChange={(event:React.ChangeEvent<HTMLTextAreaElement>)=>setEditedProposal(event.target.value)} autoFocus/></>:<p>{proposedText}</p>}</div>
        </div>
      </section>

      <section className="p-review-effects" aria-labelledby="review-effects-title">
        <ImpactTrace
          title="What else would change"
          originLabel={item.title}
          originDetail={why}
          effects={item.effectPreview}
          currentLabel="Current"
          changedLabel="Proposed"
          onSelect={objectId=>void setActiveObject(objectId)}
        />
      </section>

      <footer className="p-judgment-strip">
        <div>
          <button className="p-btn p-btn-primary" disabled={!canUpdate||Boolean(pendingAction)||!proposedText.trim()} onClick={()=>void act(editing?'CORRECT':'ADMIT')}>{pendingAction==='REVIEW_ITEM'?'Updating case…':'Update case'}</button>
          <button className="p-btn" disabled={!canUpdate||Boolean(pendingAction)} aria-pressed={editing} onClick={()=>setEditing(value=>!value)}>{editing?'Cancel edit':'Edit'}</button>
          <button className="p-btn p-btn-quiet" disabled={!canUpdate||Boolean(pendingAction)} onClick={()=>void act('REJECT')}>Dismiss</button>
        </div>
        <span className="p-sandbox-note" role="status">{pendingAction==='REVIEW_ITEM'?'Recording the accountable case update…':'The case stays unchanged until you decide.'}</span>
      </footer>
    </article>
    <div className="p-floating-lens"><ObjectLens compact/></div>
  </main>;
}
