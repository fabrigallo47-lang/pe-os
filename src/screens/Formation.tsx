import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { unknownById, objectLabel, caseReadingById } from '../app/selectors';
import { goTo } from '../app/routes';

export function Formation(){
  const {snapshot,execute,setActiveObject,actor}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const draft=snapshot.formation;
  if(!draft)return <main className="p-page"><section className="p-empty"><div><h1>Formation</h1><p>No formation draft is currently available.</p></div></section></main>;
  const materials=draft.materialIds.map(id=>snapshot.sources.find(s=>s.id===id)).filter(Boolean)!;
  const workstreams=draft.proposedWorkstreamIds.map(id=>snapshot.workstreams.find(w=>w.id===id)).filter((w): w is NonNullable<typeof w> => Boolean(w));
  const blindSpots=draft.blindSpotUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean)!;
  const [selectedSourceId,setSelectedSourceId]=useState<string|undefined>(materials[0]?.id);
  const [editing,setEditing]=useState(false);
  const [names,setNames]=useState<Record<string,string>>({});
  const selectedMaterial=snapshot.formation?.materialIds.includes(selectedSourceId??'')?snapshot.formation:undefined;
  const mappedWorkstreamIds=useMemo(()=>{
    const fm=snapshot.formation; if(!fm||!selectedSourceId)return [];
    const sourceMaterial = (snapshot as any).formationMaterials?.find?.((m:any)=>m.sourceId===selectedSourceId);
    return sourceMaterial?.mappedWorkstreamIds ?? workstreams.filter(w=>caseReadingById(snapshot,w.currentCaseReadingId)?.supportObjectIds.some(id=>snapshot.claims.find(e=>e.id===id)?.sourceId===selectedSourceId)).map(w=>w.id);
  },[snapshot,selectedSourceId,workstreams]);
  const canAdopt=actor?.entitlements.includes('ADOPT_FORMATION')??false;

  const saveCorrection=async()=>{await execute({type:'CORRECT_FORMATION',patch:{workstreamNames:names}});setEditing(false)};
  return <main className="p-page p-formation-page">
    <section className="p-formation-head"><div><div className="p-kicker">Case formation</div><h1>Form the case</h1><p>{materials.length} materials received · {workstreams.length} proposed workstreams · {blindSpots.length} declared blind spots</p></div><div className="p-formation-state"><strong>{draft.status==='PROPOSED_NOT_LIVE'?'PANTA proposal · not yet live':'Case structure adopted'}</strong><span>{draft.unplacedSourceIds.length} unplaced item{draft.unplacedSourceIds.length===1?'':'s'}</span></div></section>

    <section className="p-assembly-surface">
      <aside className="p-material-tray"><div className="p-section-heading"><strong>What PANTA received</strong><span>{materials.length}</span></div>{materials.map(s=><button key={s!.id} className={selectedSourceId===s!.id?'is-selected':''} onClick={()=>setSelectedSourceId(s!.id)}><span>{s!.type}</span><strong>{s!.title}</strong>{s!.excerpt&&<p>{s!.excerpt}</p>}</button>)}</aside>

      <section className="p-case-assembly"><div className="p-case-premise"><div className="p-kicker">Proposed case structure</div>{draft.premise&&<h2>{draft.premise}</h2>}<span>{workstreams.length} workstreams · {blindSpots.length} blind spots · {draft.unplacedSourceIds.length} unplaced</span></div><div className="p-assembly-list">{workstreams.map((w,i)=>{const r=caseReadingById(snapshot,w!.currentCaseReadingId);const unknowns=w!.openUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);const highlighted=mappedWorkstreamIds.includes(w!.id);return <article key={w!.id} className={highlighted?'is-source-linked':''}><span>{String(i+1).padStart(2,'0')}</span><div>{editing?<input className="p-inline-edit" value={names[w!.id]??w!.name} onChange={(e: React.ChangeEvent<HTMLInputElement>)=>setNames(n=>({...n,[w!.id]:e.target.value}))}/>:<strong>{w!.name}</strong>}<button onClick={()=>r&&void setActiveObject(r.id)}>{r?.text??'No proposed reading'}</button></div><div>{unknowns[0]&&<><span className="p-meta">Still missing</span><p>{unknowns[0]!.title}</p></>}</div></article>})}</div></section>

      <aside className="p-formation-review"><div className="p-section-heading"><strong>What PANTA could not establish</strong></div>{blindSpots.map(g=><button key={g!.id} onClick={()=>void setActiveObject(g!.id)}>{g!.title}</button>)}<div className="p-formation-actions"><strong>{draft.status==='PROPOSED_NOT_LIVE'?'Not live until a human adopts the structure':'Structure is live'}</strong>{draft.status==='PROPOSED_NOT_LIVE'&&<>{editing?<><button className="p-btn p-btn-primary" onClick={()=>void saveCorrection()}>Save corrections</button><button className="p-btn" onClick={()=>setEditing(false)}>Cancel</button></>:<><button className="p-btn p-btn-primary" disabled={!canAdopt} onClick={()=>void execute({type:'ADOPT_FORMATION'})}>Adopt case structure</button><button className="p-btn" onClick={()=>setEditing(true)}>Correct structure</button><button className="p-btn p-btn-quiet" onClick={()=>goTo('deal')}>Keep as draft</button></>}</>}</div></aside>
    </section>
  </main>;
}
