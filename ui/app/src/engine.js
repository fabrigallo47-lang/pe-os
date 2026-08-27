(function(){
  'use strict';
  const F = window.PANTA_V17_FIXTURE;
  const V16 = F.v16;
  const listeners = new Set();
  const clone = value => JSON.parse(JSON.stringify(value));
  const storage = {
    get(key,fallback){try{const raw=localStorage.getItem(key);return raw?JSON.parse(raw):fallback}catch(_){return fallback}},
    set(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch(_){}},
    remove(key){try{localStorage.removeItem(key)}catch(_){} }
  };

  const baseHistory = [
    {id:'REG-001',kind:'SOURCE',actor:'Compiler',time:'08:32',label:'QoE Report v3 ingested',detail:'Source version registered; 27 adjustments extracted.',object_id:'SRC-QOE'},
    {id:'REG-002',kind:'BIND',actor:'Compiler',time:'08:34',label:'Earnings claims bound',detail:'QoE EBITDA and rejected initiative linked to UQ-EARNINGS.',object_id:'UQ-EARNINGS'},
    {id:'REG-003',kind:'SYSTEM',actor:'PANTA',time:'08:35',label:'Morning Delta prepared',detail:'One material treatment and three active work items ranked.',object_id:'DELTA-1'}
  ];

  function initialState(){
    return {
      loading:true,
      mode:'demo',
      projectionSource:'embedded',
      connectionFallback:null,
      scale:'fund',
      view:'fund-command',
      role:'associate',
      lens:'command',
      selectedSituationId:'SIT-KEYSTONE',
      selectedQuestionId:'UQ-EARNINGS',
      selectedWorkstream:'All',
      selectedArtifactId:'ART-MODEL',
      selectedScenarioId:'base',
      selectedReplayId:'firm-initial',
      selectedCourseId:null,
      selectedRoom:null,
      drawer:null,
      drawerId:null,
      drawerTab:'basis',
      commandOpen:false,
      commandQuery:'',
      commandResults:[],
      actionRailOpen:true,
      activeScene:null,
      flowPhase:'idle',
      transitionResult:null,
      transitionIndex:-1,
      transitionRun:0,
      transitionError:null,
      selectedChangeSets:[],
      decisionAttested:false,
      executionStatus:'draft',
      settled:null,
      comments:storage.get('panta-v17-comments',{}),
      history:storage.get('panta-v17-history',clone(baseHistory)),
      toast:null,
      reducedMotion:false,
      demoRunning:false
    };
  }

  let state=initialState();
  let timer=null;
  const emit=()=>listeners.forEach(fn=>fn(getState()));
  const getState=()=>state;
  const patch=partial=>{state=Object.assign({},state,partial);emit();};
  const subscribe=fn=>{listeners.add(fn);fn(getState());return()=>listeners.delete(fn)};
  const stopTimer=()=>{if(timer)clearTimeout(timer);timer=null};
  const persistHistory=()=>storage.set('panta-v17-history',state.history);

  // Personas belong to the demo. With the fixture stripped there is no
  // A. Rossi, so an act is attributed to the role that performed it —
  // inventing a name for a real registry entry is how a record stops
  // being a record.
  const actorName=()=>window.PantaLive?.stripped
    ?(state.role==='partner'?'Partner':'Associate')
    :(state.role==='partner'?'M. Alvarez':'A. Rossi');

  function record(kind,label,detail,objectId,actor='PANTA',extra={}){
    const event={id:`REG-${String(state.history.length+1).padStart(3,'0')}`,kind,actor,time:new Date().toISOString().slice(11,16),label,detail,object_id:objectId||null,...extra};
    state.history.push(event);persistHistory();return event;
  }

  function applyProjection(projection){
    if(!projection||typeof projection!=='object')return false;
    for(const key of ['fund','deal','events']){
      if(projection[key]&&typeof projection[key]==='object')F[key]=projection[key];
    }
    // Which screens the projection could not fill, and why. render.js shows the
    // reason in place of the screen, so an absence reads as an absence.
    if(window.PantaLive&&projection.absent_views)window.PantaLive.setAbsent(projection.absent_views,projection.available_views);
    if(window.PantaLive){window.PantaLive.extraction=projection.extraction||null;window.PantaLive.sources=projection.sources||[];window.PantaLive.disclosure=projection.disclosure||'';}
    // The registry is the ingest log, not a demo script: replace it rather than
    // appending real events to fixture ones.
    if(window.PantaLive?.stripped&&projection.deal?.registry){
      state.history=clone(projection.deal.registry);persistHistory();
    }
    return Boolean(projection.fund||projection.deal||projection.events);
  }

  async function init(){
    try{
      const boot=await window.PantaIntegration.bootstrap();
      let projectionSource='embedded';
      if(boot.mode==='connected'){
        const payload=await window.PantaIntegration.loadCase(F.deal.case_id);
        const projection=window.PantaProjectionAdapter.frontendProjectionFromBackend(payload);
        if(applyProjection(projection))projectionSource='backend';
      }
      patch({loading:false,mode:boot.mode,projectionSource,connectionFallback:boot.fallback_reason||null});
      record('SYSTEM',boot.mode==='connected'?'Backend connected':'Integration demo loaded',projectionSource==='backend'?'Fund and Deal World projections loaded from the API.':'Embedded fixture active; API adapter remains available.','SYSTEM');
    }catch(error){
      patch({loading:false,mode:'error',connectionFallback:error.message});
    }
  }

  function setRole(role){if(!['associate','partner'].includes(role))return;patch({role});record('VIEW','Role projection changed',`The same state is now projected for ${role}.`,'ROLE',actorName())}
  function setLens(lens){patch({lens});}
  function setScale(scale){patch({scale,view:scale==='fund'?'fund-command':'deal-command',selectedRoom:null});}
  function openFund(){patch({scale:'fund',view:'fund-command',selectedRoom:null,activeScene:null,flowPhase:'idle'});}
  function openDeal(caseId='PROJECT-KEYSTONE'){if(caseId!=='PROJECT-KEYSTONE'){showToast('Only Project Keystone is connected in this handoff package.');return;}patch({scale:'deal',view:'deal-command',selectedRoom:null,activeScene:null,flowPhase:'idle'});record('VIEW','Deal World opened','Project Keystone selected from Fund Command.',caseId,actorName());}
  function navigate(view){patch({view,selectedRoom:['foundations','unknowns','shadow-ic','registry'].includes(view)?view:null});}
  function setSituation(id){patch({selectedSituationId:id});}
  function setQuestion(id,open=true){patch({selectedQuestionId:id,...(open?{drawer:'question',drawerId:id,drawerTab:'basis'}:{})});}
  function setWorkstream(id){patch({selectedWorkstream:id,view:'work'});}
  function setArtifact(id){patch({selectedArtifactId:id,view:'artifacts'});}
  function setScenario(id){patch({selectedScenarioId:id});}
  function setReplay(id){patch({selectedReplayId:id});}
  function openDrawer(type,id,tab='basis'){patch({drawer:type,drawerId:id,drawerTab:tab});}
  function closeDrawer(){patch({drawer:null,drawerId:null});}
  function setDrawerTab(tab){patch({drawerTab:tab});}
  function toggleActionRail(){patch({actionRailOpen:!state.actionRailOpen});}
  function showToast(message){patch({toast:message});setTimeout(()=>{if(state.toast===message)patch({toast:null})},1800)}

  // The palette is a list of objects you can jump to. In the demo those are the
  // fixture's; with the fixture stripped they have to be the ones an ingest
  // actually produced, or the search finds things that are not there.
  function commandIndex(){
    if(!window.PantaLive?.stripped){
      return [
        {id:'UQ-EARNINGS',type:'Question',label:'What earnings can we underwrite?',view:'deal-command'},
        {id:'FND-REVENUE',type:'Foundation',label:'Revenue durability support set',view:'foundations'},
        {id:'UNK-CONTRACTS',type:'Unknown',label:'Can Riverton reduce volume without penalty?',view:'unknowns'},
        {id:'SIC-DISSENT',type:'Shadow IC',label:'Recorded dissent on multiple and risk',view:'shadow-ic'},
        {id:'ART-MEMO',type:'Artifact',label:'Project Keystone IC memorandum',view:'artifacts'},
        {id:'REG-003',type:'Registry',label:'Morning Delta prepared',view:'registry'},
        {id:'final-ic',type:'Replay',label:'Final IC snapshot',view:'replay'}
      ];
    }
    const out=[];
    (F.deal?.scenarioLab?.scenarios||[]).forEach(s=>out.push({id:s.id,type:'Scenario',label:`${s.label} · ${s.moic??'—'}x`,view:'scenario'}));
    (F.deal?.rooms?.foundations?.sets||[]).forEach(s=>out.push({id:s.id,type:'Foundation',label:s.label,view:'foundations'}));
    (F.deal?.rooms?.unknowns?.items||[]).forEach(u=>out.push({id:u.id,type:'Unknown',label:u.label,view:'unknowns'}));
    (state.history||[]).forEach(ev=>out.push({id:ev.id,type:'Registry',label:ev.label,view:'registry'}));
    return out;
  }

  function command(query){
    const clean=(query||'').trim();
    const all=commandIndex();
    const terms=clean.toLowerCase().split(/\s+/).filter(Boolean);
    const results=(terms.length?all.filter(item=>terms.every(t=>(item.label+' '+item.type).toLowerCase().includes(t))):all).slice(0,5);
    patch({commandQuery:clean,commandResults:results,commandOpen:true});
  }
  function closeCommand(){patch({commandOpen:false,commandQuery:'',commandResults:[]});}
  function openCommandResult(item){
    closeCommand();
    if(item.view==='replay'){patch({scale:'deal',view:'replay',selectedReplayId:item.id});return;}
    patch({scale:'deal',view:item.view});
    if(item.type==='Question')setQuestion(item.id,true);else openDrawer('object',item.id,'basis');
  }

  function openScene(id){
    if(!F.events[id])return;
    stopTimer();
    patch({scale:'deal',view:'change',activeScene:id,flowPhase:'arrival',transitionResult:null,transitionIndex:-1,transitionError:null,selectedChangeSets:[],selectedCourseId:null,decisionAttested:false,executionStatus:'draft',settled:null});
    record('SOURCE','Material source opened',F.events[id].label,F.events[id].event_id,actorName());
  }
  function reviewSource(){if(state.flowPhase!=='arrival')return;patch({flowPhase:'evidence'});record('REVIEW','Source review started','Exact passage, definition, period and perimeter opened.',F.events[state.activeScene].event_id,actorName());}
  function prepareTreatment(){if(!['evidence','arrival'].includes(state.flowPhase))return;patch({flowPhase:'treatment'});}

  async function confirmTreatment(){
    if(state.flowPhase!=='treatment')return;
    const id=state.activeScene;const event=F.events[id];
    patch({flowPhase:'impact',transitionError:null,transitionIndex:-1});
    record('ADMISSION','Professional treatment admitted',event.proposed_position,event.event_id,actorName());
    try{
      const result=await window.PantaIntegration.admitEvent(F.deal.case_id,event.event_id);
      state.transitionRun+=1;
      patch({transitionResult:result});
      record('SYSTEM','Transition Engine returned Candidate',`${result.affected_set.length} mapped consequences; ${result.human_stops.length} human stop(s).`,result.candidate_state_id||result.run_id,'Transition Engine');
      animateTransition();
    }catch(error){patch({transitionError:error.message,flowPhase:'impact-error'});}
  }

  function animateTransition(){
    stopTimer();
    const result=state.transitionResult;if(!result)return;
    let index=0;const delay=state.reducedMotion?30:420;
    const tick=()=>{
      if(index>=result.affected_set.length){patch({transitionIndex:result.affected_set.length-1,flowPhase:'impact-complete'});record('SYSTEM','Propagation completed','Every mapped object received an explicit disposition.',result.run_id,'Transition Engine');return;}
      patch({transitionIndex:index});
      const item=result.affected_set[index];
      record('PROPAGATION',`${item.disposition}: ${item.label}`,`${item.before||''} → ${item.after||''}`,item.object_id,'Transition Engine',{order:index+1});
      index+=1;timer=setTimeout(tick,delay);
    };
    timer=setTimeout(tick,delay);
  }
  function skipTransition(){if(!state.transitionResult)return;stopTimer();patch({transitionIndex:state.transitionResult.affected_set.length-1,flowPhase:'impact-complete'});}
  function replayTransition(){if(!state.transitionResult)return;patch({transitionIndex:-1,flowPhase:'impact'});animateTransition();}
  function continueFromImpact(){if(state.flowPhase!=='impact-complete')return;patch({flowPhase:'action'});}
  function toggleChangeSet(id){const set=new Set(state.selectedChangeSets);set.has(id)?set.delete(id):set.add(id);patch({selectedChangeSets:[...set]});}
  function prepareResponse(){
    const result=state.transitionResult;
    if(!result)return;
    if(!state.selectedChangeSets.length)state.selectedChangeSets=result.artifact_change_sets.map(x=>x.artifact_id);
    record('ARTIFACT','Synchronized response prepared',`${state.selectedChangeSets.length||result.artifact_change_sets.length} artifact change sets prepared.`,result.run_id,'Artifact Projection Service');
    if(result.human_stops.length)patch({view:'decision',flowPhase:'decision'});else settleWithoutAuthority();
  }
  async function settleWithoutAuthority(){
    const result=state.transitionResult;patch({flowPhase:'settling'});
    const settled=await window.PantaIntegration.settle(F.deal.case_id,result.candidate_state_id,{type:'professional_review'});
    patch({settled,flowPhase:'settled',view:'change'});record('STATE','Case state settled','Candidate promoted to Current; Approved remains historical.',settled.current_state_id,'PANTA');
  }
  function selectCourse(id){patch({selectedCourseId:id});}
  function attestDecision(){
    if(!state.selectedCourseId){showToast('Select a course of action first.');return;}
    const course=F.deal.decisionRoom.courses.find(x=>x.id===state.selectedCourseId);
    patch({decisionAttested:true,view:'execution',flowPhase:'execution'});
    record('AUTHORITY','Offer authority attested',course.label,F.deal.decisionRoom.request_id,actorName(),{authority_verb:'approve_offer'});
  }
  async function executeExternal(){
    if(!state.decisionAttested)return;
    patch({executionStatus:'sending'});
    await new Promise(resolve=>setTimeout(resolve,state.reducedMotion?30:700));
    patch({executionStatus:'simulated-sent'});
    record('EXECUTION','External action simulated','Offer package passed all checks; no external message was sent in demo mode.','EXEC-OFFER-001','Execution Service');
    const result=state.transitionResult;
    const settled=await window.PantaIntegration.settle(F.deal.case_id,result.candidate_state_id,{course_id:state.selectedCourseId,authority_record:F.deal.decisionRoom.request_id});
    patch({settled,flowPhase:'settled',view:'change'});
    record('STATE','Deal World settled','New Current case recorded; Approved snapshot remains immutable.',settled.current_state_id,'PANTA');
  }

  function addComment(objectId,text,mention){
    const clean=(text||'').trim();if(!clean)return false;
    const comment={id:`C-${Date.now()}`,author:actorName(),text:clean,mention:mention||null,time:new Date().toISOString().slice(11,16)};
    state.comments[objectId]=state.comments[objectId]||[];state.comments[objectId].push(comment);storage.set('panta-v17-comments',state.comments);
    record('COMMENT','Comment attached',mention?`Routed to ${mention}.`:'Stored on the object.',objectId,comment.author);emit();return true;
  }

  function reset(){stopTimer();storage.remove('panta-v17-comments');storage.remove('panta-v17-history');state=initialState();emit();init();}
  function setReducedMotion(value){patch({reducedMotion:typeof value==='boolean'?value:!state.reducedMotion});}
  function setDemoRunning(value){patch({demoRunning:value});}

  window.PantaRuntime={
    ready:init(),getState,subscribe,setRole,setLens,setScale,openFund,openDeal,navigate,setSituation,setQuestion,setWorkstream,setArtifact,setScenario,setReplay,openDrawer,closeDrawer,setDrawerTab,toggleActionRail,showToast,command,closeCommand,openCommandResult,
    openScene,reviewSource,prepareTreatment,confirmTreatment,skipTransition,replayTransition,continueFromImpact,toggleChangeSet,prepareResponse,selectCourse,attestDecision,executeExternal,
    addComment,reset,setReducedMotion,setDemoRunning,record
  };
})();
