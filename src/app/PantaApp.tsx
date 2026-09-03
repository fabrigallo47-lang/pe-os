import React, { useEffect, useState } from 'react';
import type { PantaBackendAdapter } from '../providers/PantaBackendAdapter';
import { PantaProvider } from './PantaContext';
import { parseRoute, type PantaRoute } from './routes';
import { GlobalShell } from '../components/GlobalShell';
import { DealHome } from '../screens/DealHome';
import { WorkstreamFocus } from '../screens/WorkstreamFocus';
import { Trace } from '../screens/Trace';
import { Simulate } from '../screens/Simulate';
import { ReviewAdmit } from '../screens/ReviewAdmit';
import { Resolve } from '../screens/Resolve';
import { Formation } from '../screens/Formation';
import { ReplayDecision } from '../screens/ReplayDecision';
import { Outputs } from '../screens/Outputs';

export function PantaApp({ adapter, initialCaseId }: { adapter: PantaBackendAdapter; initialCaseId?: string }) {
  const [route,setRoute]=useState<PantaRoute>(()=>parseRoute(window.location.hash));
  useEffect(()=>{const h=()=>setRoute(parseRoute(window.location.hash));window.addEventListener('hashchange',h);if(!window.location.hash)window.location.hash='/deal';return()=>window.removeEventListener('hashchange',h)},[]);
  const screen = route==='deal'?<DealHome/>:route==='workstream'?<WorkstreamFocus/>:route==='trace'?<Trace/>:route==='simulate'?<Simulate/>:route==='review'?<ReviewAdmit/>:route==='resolve'?<Resolve/>:route==='formation'?<Formation/>:route==='replay'?<ReplayDecision/>:<Outputs/>;
  return <PantaProvider adapter={adapter} initialCaseId={initialCaseId}><div className="p-app"><GlobalShell route={route}>{screen}</GlobalShell></div></PantaProvider>;
}
