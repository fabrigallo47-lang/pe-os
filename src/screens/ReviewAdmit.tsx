import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ObjectLens } from '../components/ObjectLens';
import { objectLabel } from '../app/selectors';

export function ReviewAdmit(){
  const {snapshot,execute,setActiveObject,openSource,actor}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const items=snapshot.pendingReviews.filter(x=>x.status==='NEW'||x.status==='UNDER_REVIEW');
  const [selectedId,setSelectedId]=useState(items[0]?.id);
  const item=items.find(x=>x.id===selectedId)??items[0];
  const [correcting,setCorrecting]=useState(false);
  const [corrected,setCorrected]=useState(item?.proposedCaseReading.text??'');
  const canAdmit=actor?.entitlements.includes('ADMIT_CASE_READING')??false;
  const source=item?.sourceId?snapshot.sources.find(s=>s.id===item.sourceId):undefined;
  const finding=item?.findingId?snapshot.findings.find(f=>f.id===item.findingId):undefined;
  const derivationIds=finding?.derivationObjectIds??[];
  const changed=item?.effectPreview.filter(x=>x.state!=='HOLDS')??[];
  const held=item?.effectPreview.filter(x=>x.state==='HOLDS')??[];
  useEffect(()=>{if(item){setCorrected(item.proposedCaseReading.text);setCorrecting(false)}},[item?.id]);

  if(!item)return <main className="p-page"><section className="p-empty"><div><h1>Review & Admit</h1><p>No case change is waiting for human review.</p></div></section></main>;

  const act=(disposition:'ADMIT'|'CORRECT'|'REJECT')=>execute({type:'REVIEW_ITEM',reviewId:item.id,disposition,correctedText:disposition==='CORRECT'?corrected:undefined});
  return <main className="p-page p-review-page">
    <section className="p-review-head"><div><div className="p-kicker">{item.kind==='FINDING'?'PANTA finding':'New evidence'}</div><h1>{item.title}</h1></div><div className="p-review-queue">{items.map(x=><button key={x.id} className={x.id===item.id?'is-selected':''} onClick={()=>setSelectedId(x.id)}>{x.title}</button>)}</div></section>

    <section className="p-review-field">
      <section className="p-review-source">
        <div className="p-section-heading"><strong>{item.kind==='FINDING'?'How PANTA found this':'What arrived'}</strong></div>
        {source&&<><div className="p-source-summary"><span>{source.type}</span><strong>{source.title}</strong>{source.occurredAt&&<small>{source.occurredAt}</small>}</div>{source.excerpt&&<blockquote>“{source.excerpt}”</blockquote>}{source.limitation&&<div className="p-source-limit"><span>What this doesn't prove</span><p>{source.limitation}</p></div>}<button className="p-btn" onClick={()=>openSource(source.id)}>Open source</button></>}
        {finding&&<><p className="p-reading-small">{finding.proposition}</p><div className="p-derivation-list">{derivationIds.map(id=><button key={id} onClick={()=>void setActiveObject(id)}>{objectLabel(snapshot,id)}</button>)}</div></>}
      </section>

      <section className="p-review-reading">
        <div className="p-kicker">PANTA proposal · not yet institutional</div>{correcting?<textarea className="p-review-editor" value={corrected} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>)=>setCorrected(e.target.value)} autoFocus/>:<h2>{item.proposedCaseReading.text}</h2>}
        {item.proposedCaseReading.supportingLine&&<p>{item.proposedCaseReading.supportingLine}</p>}
        <div className="p-judgment-strip"><button className="p-btn p-btn-primary" disabled={!canAdmit} onClick={()=>void act(correcting?'CORRECT':'ADMIT')}>{correcting?'Admit corrected reading':'Admit to case'}</button><button className="p-btn" onClick={()=>setCorrecting(x=>!x)}>{correcting?'Cancel correction':'Correct'}</button><button className="p-btn p-btn-quiet" disabled={!canAdmit} onClick={()=>void act('REJECT')}>Reject</button><span className="p-sandbox-note">Live case unchanged · review pending</span></div>
      </section>

      <aside className="p-review-effects"><div className="p-section-heading"><strong>What would change</strong><span>{changed.length} change · {held.length} hold</span></div>{changed.map(e=><button key={e.objectId} className="p-effect-row" onClick={()=>void setActiveObject(e.objectId)}><div><strong>{e.objectLabel}</strong><span>{humanState(e.state)}</span></div>{e.before&&e.after&&<p>{e.before}<b> → </b>{e.after}</p>}</button>)}{held.length>0&&<div className="p-effect-holds"><span>Holds</span>{held.map(e=><button key={e.objectId} onClick={()=>void setActiveObject(e.objectId)}>{e.objectLabel}</button>)}</div>}</aside>
    </section>
    <div className="p-floating-lens"><ObjectLens compact/></div>
  </main>;
}
function humanState(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
