import React, { useEffect, useState } from 'react';
import type { PantaBackendAdapter } from '../providers/PantaBackendAdapter';
import { PantaProvider } from './PantaContext';
import { PANTA_NAVIGATION_EVENT, parseRoute, type PantaRoute } from './routes';
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

export interface PantaAppProps {
  adapter: PantaBackendAdapter;
  initialCaseId?: string;
  onStartNewCase?: () => void;
  onOpenExistingCase?: () => void;
}

export function PantaApp({ adapter, initialCaseId, onStartNewCase, onOpenExistingCase }: PantaAppProps) {
  const [route,setRoute]=useState<PantaRoute>(()=>parseRoute(window.location.hash));
  useEffect(()=>{
    const syncRoute=()=>setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange',syncRoute);
    window.addEventListener('popstate',syncRoute);
    window.addEventListener(PANTA_NAVIGATION_EVENT,syncRoute);
    if(!window.location.hash)window.history.replaceState(null,'','#/deal');
    return()=>{
      window.removeEventListener('hashchange',syncRoute);
      window.removeEventListener('popstate',syncRoute);
      window.removeEventListener(PANTA_NAVIGATION_EVENT,syncRoute);
    };
  },[]);
  const screen = route==='deal'?<DealHome/>:route==='workstream'?<WorkstreamFocus/>:route==='trace'?<Trace/>:route==='simulate'?<Simulate/>:route==='review'?<ReviewAdmit/>:route==='resolve'?<Resolve/>:route==='formation'?<Formation/>:route==='replay'?<ReplayDecision/>:<Outputs/>;
  return <PantaProvider adapter={adapter} initialCaseId={initialCaseId}><div className="p-app"><GlobalShell route={route} onStartNewCase={onStartNewCase} onOpenExistingCase={onOpenExistingCase}>{screen}</GlobalShell></div></PantaProvider>;
}
