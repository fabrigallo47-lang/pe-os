(function(){
  'use strict';
  const FIXTURE = window.PANTA_V17_FIXTURE;
  const params = new URLSearchParams(location.search);
  const requestedMode = params.get('mode') || 'auto';
  const apiBase = (params.get('api') || window.PANTA_API_BASE || 'http://127.0.0.1:4177/api/v1').replace(/\/$/,'');
  let activeMode = requestedMode === 'demo' ? 'demo' : 'auto';

  async function request(path, options={}){
    const response = await fetch(`${apiBase}${path}`, {
      headers:{'Content-Type':'application/json', ...(options.headers||{})},
      ...options
    });
    if(!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  async function bootstrap(){
    if(requestedMode === 'demo' || location.protocol === 'file:'){
      activeMode='demo';
      return {mode:'demo', fixture:FIXTURE};
    }
    try{
      const payload = await request('/bootstrap');
      activeMode='connected';
      return {mode:'connected', payload, fixture:FIXTURE};
    }catch(error){
      if(requestedMode === 'connected') throw error;
      activeMode='demo';
      return {mode:'demo', fixture:FIXTURE, fallback_reason:error.message};
    }
  }

  async function loadCase(caseId='PROJECT-KEYSTONE'){
    if(activeMode!=='connected') return {frontend_projection:FIXTURE};
    return request(`/cases/${encodeURIComponent(caseId)}/projection`);
  }

  async function admitEvent(caseId,eventId){
    if(activeMode!=='connected'){
      const key = String(eventId).toLowerCase().includes('concentration') ? 'concentration' : 'earnings';
      await new Promise(resolve=>setTimeout(resolve,240));
      return FIXTURE.transitions[key];
    }
    const raw = await request(`/cases/${encodeURIComponent(caseId)}/events/${encodeURIComponent(eventId)}/admit`,{method:'POST',body:'{}'});
    return window.PantaProjectionAdapter.fromTransitionOutput(raw);
  }

  async function settle(caseId,candidateId,decision={}){
    if(activeMode!=='connected'){
      await new Promise(resolve=>setTimeout(resolve,180));
      return {case_id:caseId,candidate_id:candidateId,status:'SETTLED',current_state_id:`current-${Date.now()}`,approved_unchanged:true,replay_hash:`sha256:demo-settlement-${Date.now()}`};
    }
    return request(`/cases/${encodeURIComponent(caseId)}/settle`,{method:'POST',body:JSON.stringify({candidate_id:candidateId,decision})});
  }

  async function replay(caseId,knownAt){
    if(activeMode!=='connected') return FIXTURE.deal.replay.snapshots.find(item=>item.id===knownAt) || FIXTURE.deal.replay.snapshots[0];
    return request(`/cases/${encodeURIComponent(caseId)}/replay?known_at=${encodeURIComponent(knownAt)}`);
  }

  function getMode(){ return activeMode; }
  window.PantaIntegration={bootstrap,loadCase,admitEvent,settle,replay,getMode,apiBase};
})();
