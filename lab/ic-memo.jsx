import React, {useMemo,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {PantaProvider,usePanta} from '../src/app/PantaContext';
import {Outputs} from '../src/screens/Outputs';
import {SourceDrawer} from '../src/components/Utilities';
import {createOutputsAdapter} from '../src/providers/liveOutputs';
import '../src/design/global.css';
import './product-lab.css';
import './ic-memo.css';

let session;
async function credentials(){if(!session){const response=await fetch('/api/source-tracking-lab/memo/session');if(!response.ok)throw new Error('Start the source tracking lab backend.');session=await response.json();}return session;}
function Workspace(){
  const {refresh,loading,error,operationError,pendingAction,snapshot}=usePanta();
  const [changing,setChanging]=useState(false);const [failure,setFailure]=useState('');
  async function change(amount){setChanging(true);setFailure('');try{const auth=await credentials();const response=await fetch('/api/source-tracking-lab/memo/change',{method:'POST',headers:{'Content-Type':'application/json','X-Panta-Session':auth.sessionId},body:JSON.stringify({amount})});if(!response.ok)throw new Error('Test case update failed.');await refresh();}catch(error){setFailure(error.message);}finally{setChanging(false);}}
  return <><aside className="p-lab-mode-bar"><div className="p-lab-identity"><span>LAB</span><strong>IC memo · fictional case · simulated writing model</strong></div><span>Proposed capital: EUR {snapshot?.quantities[0]?.value??'…'}m</span><button className="p-btn" disabled={changing||loading||Boolean(pendingAction)} onClick={()=>void change(6)}>Simulate EUR 6m update</button><button className="p-btn" disabled={changing||loading||Boolean(pendingAction)} onClick={()=>void change(5)}>Restore EUR 5m case</button><a href="/repository-tracking.html?simulate=true&app=true#/trace">Source tracking</a></aside>{(failure||error||operationError)&&<p className="p-output-notice" role="alert">{failure||error||operationError}</p>}{loading?<p role="status">Loading the saved case and memo…</p>:<Outputs/>}<SourceDrawer/></>;
}
function Lab(){const adapter=useMemo(()=>createOutputsAdapter('MEMO-TEST',credentials),[]);return <div className="p-product-lab p-memo-lab"><PantaProvider adapter={adapter} initialCaseId="MEMO-TEST"><Workspace/></PantaProvider></div>}
createRoot(document.getElementById('root')).render(<Lab/>);
