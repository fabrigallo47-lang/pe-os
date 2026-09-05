import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { PantaProvider, usePanta } from '../src/app/PantaContext';
import { ObjectLens } from '../src/components/ObjectLens';
import { SourceDrawer } from '../src/components/Utilities';
import { repositoryAdapter } from './repository-adapter.mjs';
import { PantaApp } from '../src/app/PantaApp';
const params = new URLSearchParams(window.location.search);
const simulated = params.get('simulate') === 'true';
const fullApp = simulated && params.get('app') === 'true';
import '../src/design/global.css';
import './product-lab.css';
import './repository-tracking.css';

function GraphBrowser({data}) {
  const {snapshot,loading,error,setActiveObject,activeObjectId,openSource,inspecting,sourcesOpen,operationError} = usePanta();
  const [query,setQuery] = useState('');
  const [category,setCategory] = useState('claim');
  const statusById = useMemo(()=>new Map(data.audit.map(row=>[row.id,row.status])),[data]);
  const choices = category === 'source' ? data.snapshot.sources.map(row=>({id:row.id,label:row.title,kind:'source'})) : data.entries;
  const matching = choices.filter(row=>(category === 'missing' ? statusById.get(row.id)==='UNRESOLVED' : row.kind===category) && (row.id+' '+row.label).toLowerCase().includes(query.toLowerCase()));
  if(error) return <p role="alert">{error}</p>;
  if(loading || !snapshot) return <p role="status">Loading the supplied test graph…</p>;
  const report=data.report;
  return <>
    <header className="p-reference-header"><div className="p-kicker">{simulated ? 'Simulated precise references' : 'Repository test graph'}</div><h1>Follow an information item to its original</h1><p>Existing Keystone graphs and source files, plus the repository's document fixtures. This is a read-only fixture audit; it does not create a live investment case.</p><div className="p-reference-counts"><span>{report.source_count} originals</span><span>{report.model_node_count.toLocaleString()} model nodes</span><span>{report.declared_edge_count.toLocaleString()} declared links</span><span>{report.direct_reference_counts.UNRESOLVED ?? 0} exact locations missing</span></div></header>
    <div className={'p-reference-layout '+(activeObjectId&&!sourcesOpen?'has-selection':'')}>
      <section className="p-reference-list" aria-label="Test graph information">
        <nav className="p-reference-filters" aria-label="Information type">{[['claim','Statements'],['quantity','Model values'],['source','Documents'],['missing','Missing locations']].map(([value,label])=><button key={value} className="p-btn" aria-pressed={category===value} onClick={()=>setCategory(value)}>{label}</button>)}</nav>
        <label className="p-field-label" htmlFor="reference-search">Find text or a graph reference</label><input id="reference-search" className="p-search-input" placeholder="Search these test documents and graphs" value={query} onChange={event=>setQuery(event.target.value)}/>
        <p className="p-meta" role="status">{matching.length.toLocaleString()} matches · showing up to 40</p>
        {operationError&&<p role="alert">{operationError}</p>}
        {matching.slice(0,40).map(row=><button key={row.id} className="p-reference-row" disabled={inspecting} onClick={()=>row.kind==='source'?openSource(row.id):void setActiveObject(row.id)}><strong>{row.label}</strong><span>{row.id}</span><small>{statusById.get(row.id)==='UNRESOLVED'?'Exact location not resolved':statusById.get(row.id)==='LOCATED'?'Source location verified':row.kind==='source'?'Open original source':'Follow the recorded inputs'}</small></button>)}
      </section><ObjectLens/>
    </div><SourceDrawer/>
  </>;
}

function ReferenceLab() {
  const [data,setData]=useState(); const [error,setError]=useState('');
  useEffect(()=>{let active=true; async function load(){try{const response=await fetch('/api/source-tracking-lab/reference?simulate='+String(simulated));const result=await response.json();if(!response.ok)throw new Error(result.detail||'The supplied test graph could not be loaded.');if(active)setData(result);}catch(cause){if(active)setError(cause.message);}}void load();return()=>{active=false;};},[]);
  const adapter=useMemo(()=>data&&repositoryAdapter(data,simulated),[data]);
  return <div className="p-product-lab"><aside className="p-lab-mode-bar"><div className="p-lab-identity"><span>LAB</span><strong>{simulated?'Tracking simulation':'Repository tracking'}</strong></div><a href={fullApp?'?simulate=true':simulated?'?simulate=true&app=true#/trace':'?simulate=true'}>{fullApp?'Test results':simulated?'Open in PANTA':'Simulate precise references'}</a><a href="/source-tracking.html">Small source fixture</a><a href="/">Product Lab</a></aside>{error?<p role="alert">{error}</p>:data?fullApp?<PantaApp adapter={adapter} initialCaseId={data.snapshot.caseRef.id}/>:<PantaProvider adapter={adapter} initialCaseId={data.snapshot.caseRef.id}><GraphBrowser data={data}/></PantaProvider>:<p role="status">Reading the existing test documents and graphs…</p>}</div>;
}

createRoot(document.getElementById('root')).render(<ReferenceLab/>);
