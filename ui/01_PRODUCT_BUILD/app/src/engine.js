(function(){
  'use strict';
  const S=window.PantaStore,C=window.PantaContracts,PA=window.PantaProjectionAdapter,API=window.PantaApi,K=window.PantaConstants;
  const clone=v=>S.clone(v);
  let transitionTimer=null,ingestTimer=null,batchTimer=null,requestEpoch=0;
  const now=()=>new Date().toISOString();
  const list=value=>Array.isArray(value)?value:[];
  const status=(message)=>{S.set({statusMessage:message});document.getElementById('status-region').textContent=message;setTimeout(()=>{if(S.get().statusMessage===message)S.set({statusMessage:''})},2600)};
  const toast=(message,type='info')=>{S.set({toast:{message,type}});setTimeout(()=>{if(S.get().toast?.message===message)S.set({toast:null})},3200)};
  const actor=()=>S.get().context?.authenticated_actor||{actor_id:'UNAUTHENTICATED',name:'Unauthenticated',role:'Observer'};
  const projection=()=>S.get().projection;
  const activeEvent=()=>{const p=projection(),id=S.get().activeEventId;return Object.values(p?.events||{}).find(e=>e.event_id===id)||(p?.events&&Object.values(p.events)[0])||null};
  const authorityLevel=()=>S.get().context?.authority_assignments?.find(x=>x.actor_id===actor().actor_id)?.authority_level||'NONE';
  const rank={NONE:0,PROFESSIONAL_REVIEW:1,PRINCIPAL:2,DEAL_PARTNER:3,INVESTMENT_COMMITTEE:4};
  const hasAuthority=required=>(rank[authorityLevel()]||0)>=(rank[required]||99);
  const changeSetId=item=>item?.change_set_id||item?.artifact_id||item?.change_id||item?.id||null;
  const transitionChangeSets=(transition=S.get().transition)=>list(transition?.change_sets?.length?transition.change_sets:transition?.artifact_change_sets);
  const authorityRecords=(state=S.get())=>state.authorityRecordsByStopId||{};
  function scopedHumanStops(state=S.get()){
    const stops=list(state.transition?.human_stops),selected=new Set(list(state.selectedChangeIds));
    const sets=transitionChangeSets(state.transition).filter(item=>selected.has(changeSetId(item)));
    const objectIds=new Set(sets.flatMap(item=>list(item.object_ids).map(String)));
    if(!sets.length||!objectIds.size)return stops;
    const declaredStopIds=new Set(sets.flatMap(item=>list(item.blocking_stop_ids).map(String)));
    return stops.filter(stop=>{
      const objectId=String(stop.object_id||stop.object_or_component_id||'');
      return declaredStopIds.has(String(stop.stop_id))||objectId==='candidate-change-set'||objectIds.has(objectId)||list(stop.downstream_scope).some(id=>objectIds.has(String(id)));
    });
  }
  function unresolvedHumanStops(state=S.get()){
    const records=authorityRecords(state);
    return scopedHumanStops(state).filter(stop=>stop.status!=='CLOSED'&&!records[stop.stop_id]);
  }
  function authorityEligibility(stop,state=S.get()){
    if(!stop)return{allowed:false,verified:false,reason:'No Human Stop is active.'};
    if(stop.attestable===false)return{allowed:false,verified:true,reason:stop.requested_action||'This stop requires correction or another non-attestation resolution.'};
    if(typeof stop.authorization?.can_attest==='boolean')return{allowed:stop.authorization.can_attest,verified:true,reason:stop.authorization.reason||stop.authorization.reason_code||''};
    const currentActor=state.context?.authenticated_actor||actor(),verb=stop.authority_verb,verbs=currentActor.authority_verbs;
    if(Array.isArray(verbs)&&verb&&verb!=='RESOLVE_HUMAN_STOP')return{allowed:verbs.includes(verb),verified:true,reason:verbs.includes(verb)?'Authority verb granted by server context.':`${currentActor.actor_id||'Actor'} lacks ${verb}.`};
    const required=stop.required_authority_level,assignments=list(state.context?.authority_assignments);
    if(required&&rank[required]&&assignments.length)return{allowed:hasAuthority(required),verified:true,reason:hasAuthority(required)?'Authority level granted by server context.':`${required} is required.`};
    if(stop.required_role&&currentActor.role===stop.required_role)return{allowed:true,verified:true,reason:'Required role matches the authenticated actor.'};
    return{allowed:true,verified:false,reason:'Authority metadata is incomplete; the server will make the authoritative decision.'};
  }
  const canAttestStop=stop=>authorityEligibility(stop).allowed;
  const uid=prefix=>API.uid(prefix);

  function normalizePayload(raw){
    const p=raw.projection||raw.frontend_projection||raw;
    const context={...(raw.context||p.context||{})};
    p.context=context;
    const val=C.safe(C.validateProjection,p);if(!val.ok){const e=new Error('Projection failed the V20 boundary contract.');e.code='UNSUPPORTED_PROJECTION';e.details=val.errors;throw e}
    return {projection:p,context,registry:raw.registry||p.deal.registry||[]};
  }
  function applyProjection(raw,{preserveView=true}={}){
    const {projection:p,context,registry}=normalizePayload(raw);const st=S.get(),focus=p.initial_focus||{};
    const next={projection:p,context,caseId:p.deal.case_id,registry:clone(registry),availableCapabilities:p.deal.capabilities||p.deal.navigation_capabilities||{},lastRefreshAt:now(),boot:'ready',busy:false,lastError:null,
      viewerProjection:context.viewer_projection||st.viewerProjection||'associate',selectedSituationId:st.selectedSituationId||focus.situation_id||p.fund?.situations?.[0]?.id||null,
      selectedQuestionId:st.selectedQuestionId||focus.question_id||p.deal.question_spine?.[0]?.id||null,selectedArtifactId:st.selectedArtifactId||focus.artifact_id||p.deal.artifacts?.[0]?.id||null,
      selectedScenarioId:st.selectedScenarioId||focus.scenario_id||p.deal.scenarioLab?.scenarios?.[0]?.id||null,selectedReplayId:st.selectedReplayId||focus.replay_id||p.deal.replay?.snapshots?.at(-1)?.event_id||null,selectedAsOfDate:context.as_of_date||p.deal.as_of_date||st.selectedAsOfDate||null,selectedLensId:context.active_lens_id||p.deal.active_lens_id||p.deal.default_lens_id||st.selectedLensId||null,activeEventId:st.activeEventId||(p.deal.primary_event_key&&p.events?.[p.deal.primary_event_key]?.event_id)||Object.values(p.events||{})[0]?.event_id||null};
    if(!preserveView)Object.assign(next,{view:focus.view||'fund-command',scale:(focus.view||'fund-command')==='fund-command'?'fund':'deal'});
    S.set(next);syncRoute();return p;
  }
  function modeQuery(mode=S.get().mode){return mode==='mock'?'mock':mode==='offline'?'offline':'connected'}
  function syncRoute(){const st=S.get(),q=new URLSearchParams();if(st.caseId)q.set('case',st.caseId);q.set('view',st.view);if(st.drawerObjectId)q.set('object',st.drawerObjectId);if(st.context?.as_of_date)q.set('as_of_date',st.context.as_of_date);if(st.activeRun?.run_id)q.set('run',st.activeRun.run_id);history.replaceState(null,'',`${location.pathname}${location.search}#${q}`)}
  function readRoute(){const x=Object.fromEntries(new URLSearchParams(location.hash.replace(/^#/,'')));return x}

  async function boot(){
    const st=S.get();if(st.mode==='empty'){S.set({boot:'ready',projection:null,context:{mode:'EMPTY_SYSTEM',action_capability:'READ_ONLY',synthetic:false},busy:false});return}
    S.set({boot:'loading',busy:true,operation:'BOOTSTRAP'});const initialRoute=readRoute();try{const api=API.adapter(),b=await api.bootstrap(st.caseId,new URLSearchParams(location.search).get('actor')||'partner');if(b.session_id){sessionStorage.setItem('panta-v20-session',b.session_id);S.set({sessionId:b.session_id})}S.set({availableCases:b.available_cases||b.cases||[]});const raw=await api.loadProjection(st.caseId||b.context?.case_id||b.available_cases?.[0]);applyProjection(raw,{preserveView:false});const route=initialRoute;if(route.view)S.set({view:route.view,scale:route.view==='fund-command'?'fund':'deal'});if(route.object)S.set({drawerObjectId:route.object});if(route.as_of_date)await setAsOfDate(route.as_of_date);await Promise.allSettled([refreshSources(),refreshInbox()]);status(`${b.context?.mode||st.mode} projection loaded`)}catch(e){S.set({boot:'error',busy:false,lastError:errorShape(e),error:errorShape(e)});throw e}}
  const errorShape=e=>({code:e.code||'APPLICATION_ERROR',message:e.message||String(e),details:e.details||{},status:e.status||null});
  async function refreshProjection({asOfDate=null,preserveView=true}={}){const epoch=++requestEpoch;S.set({busy:true,operation:'REFRESH'});try{const raw=await API.adapter().loadProjection(S.get().caseId,S.get().activeRun?.run_id,asOfDate);if(epoch!==requestEpoch)return;applyProjection(raw,{preserveView});status('Projection refreshed from the authoritative source')}catch(e){if(epoch===requestEpoch)S.set({busy:false,lastError:errorShape(e)});throw e}}
  async function setAsOfDate(value){if(!value)return;await refreshProjection({asOfDate:value});S.set(st=>({selectedAsOfDate:value,selectedReplayId:st.projection?.deal?.replay?.snapshots?.at(-1)?.event_id||null}));syncRoute()}
  const setAsOfState=setAsOfDate;
  async function openCase(caseId){if(!caseId)return;if(caseId!==S.get().caseId){const q=new URLSearchParams(location.search);q.set('mode',modeQuery());q.set('case',caseId);if(S.get().sessionId)q.set('session',S.get().sessionId);location.search='?'+q.toString();return}S.set({scale:'deal',view:'deal-command'});syncRoute()}
  function setView(view){const room=K.rooms.find(r=>r.id===view);if(room?.gated){const gate=view==='decision'?decisionGate():executionGate();if(!gate.ok){S.set({view:'blocked',lastError:{code:gate.code,message:gate.message,details:gate.details||{}}});syncRoute();return}}S.set({view,scale:view==='fund-command'?'fund':'deal',lastError:null});syncRoute()}
  function setViewerProjection(v){if(!['associate','partner'].includes(v))return;S.set({viewerProjection:v});}
  function selectSituation(id){S.set({selectedSituationId:id})}
  function selectQuestion(id){S.set({selectedQuestionId:id,drawerObjectId:id,drawerTab:'basis'});syncRoute()}
  function selectArtifact(id){S.set({selectedArtifactId:id,view:'artifacts'});syncRoute()}
  function selectScenario(id){S.set({selectedScenarioId:id})}
  function setWorkstream(id){S.set({selectedWorkstream:id})}
  function openObject(id,tab='basis'){S.set({drawerObjectId:id,drawerTab:tab});syncRoute()}
  function closeDrawer(){S.set({drawerObjectId:null});syncRoute()}
  function setDrawerTab(tab){S.set({drawerTab:tab})}
  function toggleActionRail(){S.set(st=>({actionRailOpen:!st.actionRailOpen}))}
  function toggleNav(){S.set(st=>({navOpen:!st.navOpen}))}
  function toggleInspector(){S.set(st=>({inspectorOpen:!st.inspectorOpen}))}
  function setReducedMotion(v){S.set(st=>({reducedMotion:typeof v==='boolean'?v:!st.reducedMotion}))}
  function clearError(){S.set({lastError:null,error:null})}
  function resetInterface(){const p=projection();S.set({view:'fund-command',scale:'fund',activeEventId:null,activeRun:null,transition:null,transitionIndex:-1,selectedChangeIds:[],selectedCourseId:null,activeHumanStopId:null,authorityRecord:null,authorityRecordsByStopId:{},executionPackage:null,executionPackagesByRecordId:{},executionOutcome:null,settlement:null,selectedGraphVersionId:null,graphVersionDetail:null,drawerObjectId:null,lastError:null,selectedSituationId:p?.fund?.situations?.[0]?.id||null})}

  function getWorkItems(){const p=projection();return p?.deal?.work_items||p?.v16?.work?.items||p?.deal?.question_spine?.flatMap(q=>(q.work_plan||[]).map((w,i)=>({id:w.id||`${q.id}-W${i+1}`,object_id:q.id,question_id:q.id,label:w.label||w.task||`Close ${q.label}`,owner:w.owner||q.owner||'Unassigned',status:w.status||'OPEN',priority:w.priority||q.criticality||'MEDIUM',deadline:w.deadline||'Not set',required_evidence:w.required_evidence||w.evidence||'Not specified',next_action:w.next_action||'Prepare work',authority_boundary:w.authority_boundary||'Professional review'})))||[]}
  async function prepareWork(id){try{const item=getWorkItems().find(x=>x.id===id);const out=await API.adapter().prepareWork(id,{owner:item?.owner,object_id:item?.object_id,actor_id:actor().actor_id});toast(out.message||'Work draft prepared. No external dispatch occurred.','success')}catch(e){toast(e.message,'error')}}

  async function command(q){S.set({commandOpen:true,commandQuery:q,busy:true});try{const out=await API.adapter().search(q||'');S.set({commandResults:out.results||[],busy:false})}catch(e){S.set({commandResults:API.localIndex(projection(),q),busy:false});toast('Backend search unavailable; showing current-projection results.','warning')}}
  function closeCommand(){S.set({commandOpen:false,commandQuery:'',commandResults:[]})}
  function openCommandResult(item){if(!item)return;closeCommand();setView(item.route||item.view||'deal-command');if(item.type&&item.type!=='ROOM')openObject(item.id,'basis')}

  async function refreshSources(){if(!S.get().caseId)return;try{const out=await API.adapter().listSources();S.set({sources:out.sources||projection()?.deal?.source_center?.sources||[]})}catch(_){S.set({sources:projection()?.deal?.source_center?.sources||[]})}}
  async function refreshInbox(){if(!S.get().caseId)return;try{const out=await API.adapter().listInbox();S.set({inbox:Array.isArray(out)?out:(out.items||projection()?.deal?.source_center?.inbox||[])})}catch(_){S.set({inbox:projection()?.deal?.source_center?.inbox||[]})}}
  function setSourceTab(tab){S.set({sourceTab:tab,sourcePage:1})}
  function setSourceSearch(q){S.set({sourceSearch:q,sourcePage:1})}
  function setSourceFilter(name,value){S.set(st=>({sourceFilters:{...st.sourceFilters,[name]:value},sourcePage:1}))}
  function setSourceSort(v){S.set({sourceSort:v,sourcePage:1})}
  function setSourcePage(v){S.set({sourcePage:Math.max(1,Number(v)||1)})}
  function getClaims(){const st=S.get(),filters=st.sourceFilters,q=st.sourceSearch.trim().toLowerCase();let claims=[...(projection()?.deal?.claims||[])];claims=claims.filter(c=>!q||`${c.statement||''} ${c.claim_id||c.id||''} ${c.locator||''} ${c.value??''} ${c.perimeter||''}`.toLowerCase().includes(q));for(const [k,v] of Object.entries(filters)){if(!v)continue;const map={epistemic:'epistemic_class',source:'source_id'};const field=map[k]||k;claims=claims.filter(c=>String(c[field]??'').toLowerCase().includes(String(v).toLowerCase()))}claims.sort((a,b)=>{if(st.sourceSort==='period')return String(a.period||'').localeCompare(String(b.period||''));if(st.sourceSort==='source')return String(a.source_id||'').localeCompare(String(b.source_id||''));if(st.sourceSort==='epistemic')return String(a.epistemic_class||'').localeCompare(String(b.epistemic_class||''));return (b.bears_on?.length||0)-(a.bears_on?.length||0)});return claims}
  async function ingest(form){if(S.get().mobileReadOnly){toast('Source ingestion is available on desktop.','warning');return}S.set({busy:true,operation:'INGEST',ingestError:null});try{const payload={...form,actor_id:actor().actor_id,idempotency_key:uid('INGEST')};if(form.file instanceof File){payload.content_b64=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]||'');r.onerror=()=>reject(r.error||new Error('File could not be read'));r.readAsDataURL(form.file)});delete payload.file;}const out=await API.adapter().ingest(payload);const job=out.job||out;S.set(st=>({ingestJobs:[job,...st.ingestJobs.filter(x=>x.job_id!==job.job_id)],activeIngestJobId:job.job_id,busy:false}));pollIngestJob(job.job_id)}catch(e){S.set({busy:false,ingestError:errorShape(e)});toast(`Ingest not started: ${e.message}`,'error')}}
  const filePayload=file=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve({file_name:file.name,size:file.size,mime_type:file.type,content_b64:String(r.result).split(',')[1]||''});r.onerror=()=>reject(r.error||new Error(`${file.name} could not be read`));r.readAsDataURL(file)});
  async function ingestFiles(files,purpose=''){if(S.get().mobileReadOnly){toast('Source ingestion is available on desktop.','warning');return}const selected=Array.from(files||[]);if(!selected.length){toast('Choose at least one file.','warning');return}S.set({busy:true,operation:'BULK_INGEST',ingestError:null});try{const payloads=await Promise.all(selected.map(filePayload)),out=await API.adapter().bulkIngest({files:payloads,purpose,concurrency:3,actor_id:actor().actor_id,idempotency_key:uid('BATCH')}),batch=out.batch||out;S.set(st=>({ingestBatches:[batch,...st.ingestBatches.filter(x=>x.batch_id!==batch.batch_id)],ingestJobs:[...(batch.jobs||[]),...st.ingestJobs.filter(x=>!(batch.jobs||[]).some(j=>j.job_id===x.job_id))],activeIngestBatchId:batch.batch_id,activeIngestJobId:batch.jobs?.[0]?.job_id||null,busy:false}));pollIngestBatch(batch.batch_id)}catch(e){S.set({busy:false,ingestError:errorShape(e)});toast(`Batch not started: ${e.message}`,'error')}}
  function pollIngestJob(jobId){clearTimeout(ingestTimer);const tick=async()=>{try{const out=await API.adapter().getJob(jobId),job=out.job||out;S.set(st=>({ingestJobs:st.ingestJobs.map(x=>x.job_id===jobId?job:x),activeIngestJobId:jobId}));if(['COMPLETE','FAILED','ERROR','CANCELLED'].includes(job.status)){if(job.status==='COMPLETE'){await refreshProjection();await refreshSources();await refreshInbox();status(job.admission_status==='PENDING_REVIEW'?'Extraction ready for evidence review':'Ingestion complete')}else{await refreshInbox();toast(job.fix||job.message||'Ingest failed','error')}return}ingestTimer=setTimeout(tick,Math.max(600,job.poll_after_ms||900))}catch(e){toast(`Job status unavailable: ${e.message}`,'error')}};ingestTimer=setTimeout(tick,300)}
  function pollIngestBatch(batchId){clearTimeout(batchTimer);const tick=async()=>{try{const out=await API.adapter().getIngestBatch(batchId),batch=out.batch||out,jobs=batch.jobs||[];S.set(st=>({ingestBatches:[batch,...st.ingestBatches.filter(x=>x.batch_id!==batchId)],ingestJobs:[...jobs,...st.ingestJobs.filter(x=>!jobs.some(j=>j.job_id===x.job_id))],activeIngestBatchId:batchId}));if(['COMPLETE','PARTIAL_ERROR','ERROR'].includes(batch.status)){await refreshProjection();await refreshSources();await refreshInbox();toast(batch.status==='COMPLETE'?`Batch complete: ${batch.counts?.complete||jobs.length}/${jobs.length} files processed.`:`Batch finished with ${batch.counts?.error||0} file error(s).`,batch.status==='COMPLETE'?'success':'warning');return}batchTimer=setTimeout(tick,Math.max(650,batch.poll_after_ms||900))}catch(e){toast(`Batch status unavailable: ${e.message}`,'error')}};batchTimer=setTimeout(tick,300)}
  async function retryBatchJob(batchId,jobId){try{S.set({busy:true,operation:'BATCH_RETRY'});const out=await API.adapter().retryBatchJob(batchId,jobId),batch=out.batch||out;S.set(st=>({busy:false,ingestBatches:[batch,...st.ingestBatches.filter(x=>x.batch_id!==batchId)]}));pollIngestBatch(batchId);toast('Failed file queued for retry. Successful files were left untouched.','success')}catch(e){S.set({busy:false});toast(`Retry not started: ${e.message}`,'error')}}
  async function openEvidenceReview(jobId){try{S.set({busy:true,operation:'EVIDENCE_REVIEW'});const out=await API.adapter().getEvidenceProposal(jobId);S.set({busy:false,evidenceProposal:out.proposal,evidenceProposalQuestions:out.questions||[],evidenceSemanticPreview:out.semantic_preview||null,sourceTab:'inbox'});status('Review extracted claims and question bindings before admission')}catch(e){S.set({busy:false});toast(`Evidence proposal unavailable: ${e.message}`,'error')}}
  function closeEvidenceReview(){S.set({evidenceProposal:null,evidenceProposalQuestions:[],evidenceSemanticPreview:null})}
  async function admitEvidence(jobId,decision='ADMIT',claims=null){try{S.set({busy:true,operation:'EVIDENCE_ADMISSION'});const payload={decision,actor_id:actor().actor_id,idempotency_key:uid('EVIDENCE')};if(Array.isArray(claims))payload.claims=claims;const out=await API.adapter().admitEvidence(jobId,payload);S.set({busy:false,evidenceProposal:null,evidenceProposalQuestions:[],evidenceSemanticPreview:null});if(decision==='ADMIT')await refreshProjection();await refreshSources();await refreshInbox();toast(out.message||(decision==='ADMIT'?'Reviewed evidence admitted into semantic Current.':'Evidence rejected; Current is unchanged.'),'success')}catch(e){S.set({busy:false});toast(`Evidence decision was not recorded: ${e.message}`,'error')}}
  // Explicit second step after admission: admission only compiles the
  // runtime-ready event (or declares why it can't). Invoking dynamics -
  // producing a Candidate from that event - is a separate, visible action so
  // a reviewer sees exactly what compiled before choosing to run it.
  async function processAdmittedEvent(jobId){
    const job=(S.get().inbox||[]).find(x=>x.job_id===jobId)||(S.get().ingestJobs||[]).find(x=>x.job_id===jobId);
    const eventId=job?.runtime_event_id;
    if(!eventId){toast(job?.runtime_blocker?.reason||'No runtime event is ready to process for this source.','warning');return}
    const epoch=++requestEpoch;
    S.set({busy:true,operation:'TRANSITION',lastError:null,view:'change-impact'});
    try{
      const payload={actor_id:actor().actor_id,idempotency_key:uid('ADMIT')};
      const out=await API.adapter().admitEvent(eventId,payload);
      if(epoch!==requestEpoch)return;
      const t=PA.normalizeTransition(out.transition||out),cv=C.safe(C.validateTransition,t);
      if(!cv.ok)throw Object.assign(new Error('Transition failed the frontend contract.'),{code:'INVALID_TRANSITION',details:cv.errors});
      const nextProjection=clone(S.get().projection);
      if(out.candidate_graph&&nextProjection?.deal){
        nextProjection.deal.candidate_graph=clone(out.candidate_graph);
        const versions=[...(nextProjection.deal.graph_versions||[])];
        for(const version of [out.current_graph_version,out.candidate_graph_version])if(version&&!versions.some(x=>x.version_id===version.version_id))versions.push(clone(version));
        nextProjection.deal.graph_versions=versions;
      }
      S.set({busy:false,projection:nextProjection,activeEventId:eventId,activeRun:out.run||{run_id:t.run_id,status:'CANDIDATE'},transition:t,transitionIndex:-1,selectedChangeIds:[],context:{...S.get().context,...(out.context||{}),run_id:t.run_id,candidate_state_id:t.candidate_state_id,human_stop_id:t.human_stops?.[0]?.stop_id||null},registry:out.registry||out.registry_events||S.get().registry});
      syncRoute();
      animateTransition();
      toast('Admitted event processed into a Candidate.','success')
    }catch(e){if(epoch!==requestEpoch)return;S.set({busy:false,lastError:errorShape(e)});toast(`Processing the admitted event failed: ${e.message}`,'error')}
  }
  async function removeSource(id){try{await API.adapter().removeSource(id);await refreshSources();await refreshProjection();toast('Source version retired; history preserved.','success')}catch(e){toast(e.message,'error')}}
  async function saveOpenDeal(payload){try{const out=await API.adapter().openDeal({...payload,actor_id:actor().actor_id,idempotency_key:uid('OPENDEAL')});toast(out.message||'Deal decomposition recorded.','success');await refreshProjection()}catch(e){toast(e.message,'error')}}
  async function saveICRecord(payload){try{const out=await API.adapter().recordIC({...payload,actor_id:actor().actor_id,idempotency_key:uid('IC')});toast(out.message||'IC decision ritual recorded.','success');await refreshProjection()}catch(e){toast(e.message,'error')}}
  async function reviewClaim(id,decision,correction=''){try{const knownAt=now(),note={object_id:id,claim_id:id,kind:'CLAIM_REVIEW',decision,action:decision,correction,text:correction,actor_id:actor().actor_id,timestamp:knownAt,effective_date:knownAt.slice(0,10),known_at:knownAt,idempotency_key:uid('REVIEW')};await API.adapter().addNote(note);const claims=projection()?.deal?.claims||[],c=claims.find(x=>(x.claim_id||x.id)===id);if(c)c.review_status=decision;toast('Review acknowledged by the case store.','success');S.set({renderRevision:S.get().renderRevision+1})}catch(e){toast(`Review not written: ${e.message}`,'error')}}
  async function addNote(id,text){if(!text?.trim())return;try{await API.adapter().addNote({object_id:id,kind:'ANNOTATION',text:text.trim(),actor_id:actor().actor_id,timestamp:now(),idempotency_key:uid('NOTE')});toast('Note acknowledged.','success');await refreshProjection()}catch(e){toast(`Note was not written: ${e.message}`,'error')}}

  function setUnknownTab(tab){S.set({unknownTab:tab,unknownPage:1})}
  function setUnknownSearch(q){S.set({unknownSearch:q,unknownPage:1})}
  function setUnknownSort(v){S.set({unknownSort:v,unknownPage:1})}
  function setUnknownPage(v){S.set({unknownPage:Math.max(1,Number(v)||1)})}
  function setRegistryFilter(kind,q=''){S.set({registryKind:kind||'',registrySearch:q})}
  function copyText(text){navigator.clipboard?.writeText(String(text||''));toast('Copied to clipboard.','success')}
  function deepLink(id){const q=new URLSearchParams(location.hash.replace(/^#/,''));q.set('object',id);copyText(`${location.origin}${location.pathname}${location.search}#${q}`)}
  function exportJSON(name,data){const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}

  function showChangeArrival(){const ev=activeEvent();if(!ev){toast('No pending event is available.','warning');return}S.set({activeEventId:ev.event_id,view:'change-arrival',scale:'deal'});syncRoute()}
  function startReview(){const ev=activeEvent();if(!ev){toast('No pending event is available.','warning');return}S.set({activeEventId:ev.event_id,view:'change-review',selectedChangeIds:[],selectedCourseId:null,activeHumanStopId:null,activeRun:null,transition:null,authorityRecord:null,authorityRecordsByStopId:{},executionPackage:null,executionPackagesByRecordId:{},settlement:null,editingTreatment:false,treatmentDraft:ev.proposed_treatment?.statement||ev.proposed_treatment||''});syncRoute()}
  function editTreatment(){S.set({editingTreatment:true})}
  function cancelEdit(){S.set({editingTreatment:false,treatmentDraft:activeEvent()?.proposed_treatment?.statement||activeEvent()?.proposed_treatment||''})}
  function setTreatmentDraft(v){S.set({treatmentDraft:v})}
  async function rejectTreatment(){const ev=activeEvent();if(!ev)return;await addNote(ev.event_id,'Treatment rejected before admission.');S.set({view:'deal-command',activeEventId:null});}
  async function admitTreatment(){
    const ev=activeEvent();if(!ev)return;
    const epoch=++requestEpoch;
    S.set({busy:true,operation:'TRANSITION',lastError:null,view:'change-impact'});
    const payload={treatment_id:ev.treatment_id,treatment_hash:ev.treatment_hash||await API.jsonHash(S.get().treatmentDraft||ev.proposed_treatment),source_version_id:ev.source_version_id,event_id:ev.event_id,actor_id:actor().actor_id,as_of_state_id:S.get().context?.as_of_state_id,as_of_date:S.get().context?.as_of_date,effective_date:ev.effective_date,known_at:now(),timestamp:now(),idempotency_key:`ADMIT-${ev.event_id}-${S.get().sessionId||'SESSION'}`,treatment_text:S.get().treatmentDraft};
    try{
      const out=await API.adapter().admitEvent(ev.event_id,payload);if(epoch!==requestEpoch)return;
      const t=PA.normalizeTransition(out.transition||out),cv=C.safe(C.validateTransition,t);
      if(!cv.ok)throw Object.assign(new Error('Transition failed the frontend contract.'),{code:'INVALID_TRANSITION',details:cv.errors});
      const nextProjection=clone(S.get().projection);
      if(out.candidate_graph&&nextProjection?.deal){
        nextProjection.deal.candidate_graph=clone(out.candidate_graph);
        const versions=[...(nextProjection.deal.graph_versions||[])];
        for(const version of [out.current_graph_version,out.candidate_graph_version])if(version&&!versions.some(x=>x.version_id===version.version_id))versions.push(clone(version));
        nextProjection.deal.graph_versions=versions;
      }
      const firstStop=list(t.human_stops).find(stop=>stop.status==='OPEN')||t.human_stops?.[0]||null;
      S.set({busy:false,projection:nextProjection,activeRun:out.run||{run_id:t.run_id,status:'CANDIDATE'},transition:t,transitionIndex:-1,selectedChangeIds:[],selectedCourseId:null,activeHumanStopId:firstStop?.stop_id||null,authorityRecord:null,authorityRecordsByStopId:{},executionPackage:null,executionPackagesByRecordId:{},context:{...S.get().context,...(out.context||{}),run_id:t.run_id,candidate_state_id:t.candidate_state_id,human_stop_id:firstStop?.stop_id||null,human_stop_ids:list(t.human_stops).map(stop=>stop.stop_id)},registry:out.registry||out.registry_events||S.get().registry});
      animateTransition();
    }catch(e){if(epoch!==requestEpoch)return;S.set({busy:false,lastError:errorShape(e)});toast(`Transition rejected: ${e.message}`,'error')}
  }
  // Runs every PENDING_REVIEW source through admit -> dynamics -> settle in
  // one sequential server-side pass, so a reviewer doesn't have to click
  // through each source and each settlement individually while testing.
  async function admitAllPending(){
    S.set({busy:true,operation:'ADMIT_ALL'});
    try{
      const out=await API.adapter().admitAllPending({actor_id:actor().actor_id});
      await refreshProjection();
      await refreshSources();
      await refreshInbox();
      S.set({busy:false});
      toast(out.message||`Settled ${out.settled_count||0} of ${out.requested||0} pending source(s).`, out.settled_count===out.requested?'success':'warning');
      return out;
    }catch(e){S.set({busy:false});toast(`Admit all failed: ${e.message}`,'error')}
  }
  function animateTransition(){clearTimeout(transitionTimer);const t=S.get().transition;if(!t)return;let i=0;const n=t.affected_set.length,delay=S.get().reducedMotion?10:Math.max(80,Math.min(420,2200/Math.max(n,1)));S.set({transitionPlaying:true,transitionIndex:-1});const tick=()=>{if(i>=n){S.set({transitionPlaying:false,transitionIndex:Math.max(0,n-1)});status('Candidate consequences ready');return}S.set({transitionIndex:i++});transitionTimer=setTimeout(tick,delay)};tick()}
  function skipTransition(){clearTimeout(transitionTimer);const n=S.get().transition?.affected_set?.length||0;S.set({transitionPlaying:false,transitionIndex:Math.max(0,n-1)})}
  function replayTransition(){animateTransition()}
  function openActionFrontier(){if(!S.get().transition)return;S.set({view:'action-frontier'});syncRoute()}
  function toggleChange(id){S.set(st=>{const x=new Set(st.selectedChangeIds);x.has(id)?x.delete(id):x.add(id);return{selectedChangeIds:[...x]}})}
  function selectAllChanges(){S.set({selectedChangeIds:transitionChangeSets().filter(item=>item.status!=='BLOCKED').map(changeSetId).filter(Boolean)})}
  function decisionGate(){
    const st=S.get(),t=st.transition;
    if(!st.activeRun?.run_id)return{ok:false,code:'RUN_REQUIRED',message:'A valid transition run is required.'};
    if(!t?.candidate_state_id)return{ok:false,code:'CANDIDATE_REQUIRED',message:'A current Candidate state is required.'};
    const allStops=list(t.human_stops);
    if(!allStops.length)return{ok:false,code:'HUMAN_STOP_REQUIRED',message:'This run does not contain a Human Stop.'};
    const remaining=unresolvedHumanStops(st),hs=remaining.find(stop=>stop.stop_id===st.activeHumanStopId)||remaining[0];
    if(!hs)return{ok:false,code:'HUMAN_STOPS_RESOLVED',message:'All Human Stops for this Candidate are resolved.'};
    if(hs.attestable===false)return{ok:false,code:'HUMAN_STOP_REQUIRES_CORRECTION',message:hs.requested_action||'This Human Stop requires a correction before replay.',human_stop:hs};
    return{ok:true,human_stop:hs,remaining_stop_ids:remaining.map(stop=>stop.stop_id)};
  }
  function executionGate(){const st=S.get();if(!st.authorityRecord)return{ok:false,code:'AUTHORITY_RECORD_REQUIRED',message:'A valid authority record is required.'};if(!st.executionPackage||st.executionPackage.status!=='READY')return{ok:false,code:'EXECUTION_PACKAGE_REQUIRED',message:'A READY immutable execution package is required.'};return{ok:true}}
  async function prepareResponse(){
    if(!S.get().selectedChangeIds.length){toast('Select at least one change. There is no hidden select-all.','warning');return}
    try{
      const priorRun=S.get().activeRun,out=await API.adapter().prepareRun(priorRun.run_id,S.get().selectedChangeIds),preparedRun=out.run||{...priorRun,...out,run_id:out.run_id||priorRun.run_id};
      S.set({activeRun:preparedRun});
      const gate=decisionGate();
      if(gate.ok){S.set({activeHumanStopId:gate.human_stop.stop_id,selectedCourseId:null});setView('decision');return}
      if(['HUMAN_STOP_REQUIRED','HUMAN_STOPS_RESOLVED'].includes(gate.code)){await settleCurrent();return}
      S.set({view:'blocked',lastError:{code:gate.code,message:gate.message,details:{human_stop_id:gate.human_stop?.stop_id}}});syncRoute();
    }catch(e){toast(e.message,'error')}
  }
  function selectCourse(id){S.set({selectedCourseId:id})}
  async function attestDecision(){
    const st=S.get(),gate=decisionGate();if(!gate.ok){S.set({view:'blocked',lastError:{code:gate.code,message:gate.message}});syncRoute();return}
    if(st.mobileReadOnly){toast('Formal attestation is desktop-only.','warning');return}
    if(!st.selectedCourseId){toast('Select exactly one course of action.','warning');return}
    const eligibility=authorityEligibility(gate.human_stop,st);
    if(!eligibility.allowed){S.set({view:'blocked',lastError:{code:'INSUFFICIENT_AUTHORITY',message:eligibility.reason||`${gate.human_stop.required_role} is required.`}});syncRoute();return}
    try{
      S.set({busy:true,operation:'ATTEST'});
      const out=await API.adapter().attest(st.activeRun.run_id,{run_id:st.activeRun.run_id,candidate_state_id:st.transition.candidate_state_id,human_stop_id:gate.human_stop.stop_id,course_id:st.selectedCourseId,actor_id:actor().actor_id,actor_role:actor().role,artifact_hash:st.transition.replay_hash,idempotency_key:`AUTH-${st.activeRun.run_id}-${gate.human_stop.stop_id}-${st.selectedCourseId}`});
      const ar=out.authority_record;C.validateAuthorityRecord(ar);
      const pkg=out.execution_package||null,records={...authorityRecords(st),[gate.human_stop.stop_id]:ar},packages={...(st.executionPackagesByRecordId||{})};
      if(pkg)packages[ar.authority_record_id]=pkg;
      const transition={...st.transition,human_stops:list(st.transition.human_stops).map(stop=>stop.stop_id===gate.human_stop.stop_id?{...stop,status:'CLOSED',authority_record_id:ar.authority_record_id}:stop)};
      S.set({busy:false,transition,authorityRecord:ar,authorityRecordsByStopId:records,executionPackage:pkg,executionPackagesByRecordId:packages,registry:out.registry||st.registry,selectedCourseId:null});
      const next=unresolvedHumanStops()[0]||null;S.set({activeHumanStopId:next?.stop_id||null});
      if(pkg){setView('execution');return}
      if(next){setView('decision');status(`${Object.keys(records).length} authority record(s) captured; ${unresolvedHumanStops().length} Human Stop(s) remain.`);return}
      if(ar.effect_type==='DEFER'){
        S.set({view:'action-frontier',lastError:null});syncRoute();toast('Decision deferred. Candidate remains unpromoted and Current is unchanged.','warning');return;
      }
      await settleCurrent();
    }catch(e){S.set({busy:false});toast(`Attestation rejected: ${e.message}`,'error')}
  }
  async function sendExecution(simulateFailure=false){
    const gate=executionGate();if(!gate.ok){setView('execution');return}
    const current=S.get().executionPackage,sending={...current,status:'SENDING'};
    S.set(st=>({busy:true,operation:'DELIVERY',executionPackage:sending,executionPackagesByRecordId:{...(st.executionPackagesByRecordId||{}),[current.authority_record_id]:sending}}));
    try{
      const out=await API.adapter().sendPackage(current.execution_package_id,simulateFailure),pkg=out.execution_package||out;
      S.set(st=>({busy:false,executionPackage:pkg,executionPackagesByRecordId:{...(st.executionPackagesByRecordId||{}),[pkg.authority_record_id]:pkg},executionOutcome:out,registry:out.registry||st.registry}));
      if(['ACCEPTED','DELIVERED'].includes(pkg.status))toast('Server acknowledged the simulated package. No external system was contacted.','success');else toast(`Package state: ${pkg.status}`,'warning');
    }catch(e){S.set(st=>{const failed={...st.executionPackage,status:'FAILED'};return{busy:false,executionPackage:failed,executionPackagesByRecordId:{...(st.executionPackagesByRecordId||{}),[failed.authority_record_id]:failed}}});toast(`Not sent: ${e.message}`,'error')}
  }
  async function settleCurrent(extra={}){
    const st=S.get();
    if(!st.selectedChangeIds.length){toast('Settlement requires explicit selected changes.','warning');return}
    const remaining=unresolvedHumanStops(st);
    if(remaining.length){const next=remaining.find(stop=>stop.stop_id===st.activeHumanStopId)||remaining[0];S.set({activeHumanStopId:next.stop_id,selectedCourseId:null,view:next.attestable===false?'blocked':'decision',lastError:next.attestable===false?{code:'HUMAN_STOP_REQUIRES_CORRECTION',message:next.requested_action}:null});syncRoute();toast(`${remaining.length} Human Stop(s) still require resolution.`,'warning');return}
    if(st.transition?.settlement_capability?.mode==='FORBIDDEN'){S.set({view:'blocked',lastError:{code:'SETTLEMENT_FORBIDDEN',message:st.transition.settlement_capability.reason||'This Candidate cannot be settled.'}});syncRoute();return}
    const recordIds=[...new Set([...Object.values(authorityRecords(st)).map(record=>record?.authority_record_id),...list(st.transition?.human_stops).map(stop=>stop.authority_record_id),st.authorityRecord?.authority_record_id].filter(Boolean))];
    const packageIds=[...new Set([...Object.values(st.executionPackagesByRecordId||{}).map(pkg=>pkg?.execution_package_id),st.executionPackage?.execution_package_id].filter(Boolean))];
    try{
      S.set({busy:true,operation:'SETTLEMENT'});
      const partialStatus=st.transition.partial_settlement_status||{},partialRequired=partialStatus.candidate!=='FULL'||list(partialStatus.unsettled_component_ids).length>0||list(st.transition.blocked_components).length>0;
      const out=await API.adapter().settle(st.activeRun.run_id,{run_id:st.activeRun.run_id,candidate_state_id:st.transition.candidate_state_id,prior_state_id:st.transition.prior_state_id,as_of_state_id:st.context.as_of_state_id,as_of_date:st.context.as_of_date,effective_date:new Date().toISOString().slice(0,10),selected_change_ids:st.selectedChangeIds,human_stop_ids:scopedHumanStops(st).map(stop=>stop.stop_id),authority_record_ids:recordIds,execution_package_ids:packageIds,actor_id:actor().actor_id,allow_partial_settlement:partialRequired,idempotency_key:`SETTLE-${st.activeRun.run_id}-${[...st.selectedChangeIds].sort().join('-')}`,...extra});
      const nextProjection=out.projection?.projection||out.projection||st.projection;S.set({busy:false,settlement:out,registry:out.registry||st.registry,context:out.context||st.context,projection:nextProjection,view:'settled'});status('Canonical Current state returned by the server');syncRoute();
    }catch(e){S.set({busy:false,lastError:errorShape(e)});toast(`Settlement rejected: ${e.message}`,'error')}
  }
  async function openReplay(id){S.set({selectedReplayId:id,view:'replay'});syncRoute();try{const out=await API.adapter().replay(id);if(out.as_of_date)await refreshProjection({asOfDate:out.as_of_date,preserveView:true});S.set({replayResponse:out,selectedReplayId:out.event?.event_id||id,selectedAsOfDate:out.as_of_date||S.get().selectedAsOfDate,view:'replay'});syncRoute()}catch(e){toast(`Replay unavailable: ${e.message}`,'error')}}
  async function openGraphVersion(id){if(!id)return;S.set({busy:true,operation:'GRAPH_VERSION'});try{const out=await API.adapter().getGraphVersion(id);S.set({busy:false,selectedGraphVersionId:id,graphVersionDetail:out,view:'replay'});syncRoute()}catch(e){S.set({busy:false});toast(`Graph version unavailable: ${e.message}`,'error')}}
  async function newDemoSession(){try{const out=await API.adapter().newSession(S.get().caseId,'partner');sessionStorage.setItem('panta-v20-session',out.session_id);S.set({sessionId:out.session_id,registry:[]});location.search=`?mode=${modeQuery()}&case=${encodeURIComponent(S.get().caseId)}&session=${encodeURIComponent(out.session_id)}`}catch(e){toast(e.message,'error')}}

  window.PantaActions={boot,applyProjection,refreshProjection,setAsOfDate,setAsOfState,refreshSources,refreshInbox,openCase,setView,setViewerProjection,selectSituation,selectQuestion,selectArtifact,selectScenario,setWorkstream,openObject,closeDrawer,setDrawerTab,toggleActionRail,toggleNav,toggleInspector,setReducedMotion,clearError,resetInterface,getWorkItems,prepareWork,command,closeCommand,openCommandResult,activeEvent,setSourceTab,setSourceSearch,setSourceFilter,setSourceSort,setSourcePage,getClaims,ingest,ingestFiles,pollIngestJob,pollIngestBatch,retryBatchJob,openEvidenceReview,closeEvidenceReview,admitEvidence,processAdmittedEvent,admitAllPending,removeSource,saveOpenDeal,saveICRecord,reviewClaim,addNote,setUnknownTab,setUnknownSearch,setUnknownSort,setUnknownPage,setRegistryFilter,copyText,deepLink,exportJSON,startReview,editTreatment,cancelEdit,setTreatmentDraft,rejectTreatment,admitTreatment,replayTransition,skipTransition,openActionFrontier,toggleChange,selectAllChanges,transitionChangeSets,scopedHumanStops,unresolvedHumanStops,authorityEligibility,canAttestStop,decisionGate,executionGate,prepareResponse,selectCourse,attestDecision,sendExecution,settleCurrent,openReplay,openGraphVersion,newDemoSession,showToast:toast,showChangeArrival,hasAuthority,authorityLevel};
})();
