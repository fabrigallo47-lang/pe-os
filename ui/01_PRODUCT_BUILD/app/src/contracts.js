(function(){
  'use strict';
  const isObject=value=>Boolean(value)&&typeof value==='object'&&!Array.isArray(value);
  function fail(code,path,message){const error=new Error(`${path}: ${message}`);error.code=code;error.path=path;throw error}
  function object(value,path){if(!isObject(value))fail('TYPE_ERROR',path,'must be an object');return value}
  function array(value,path){if(!Array.isArray(value))fail('TYPE_ERROR',path,'must be an array');return value}
  function string(value,path){if(typeof value!=='string'||!value)fail('TYPE_ERROR',path,'must be a non-empty string');return value}
  function requireKeys(value,keys,path){object(value,path);for(const key of keys)if(!(key in value))fail('MISSING_FIELD',`${path}.${key}`,'is required');return value}
  function bitemporal(value,path){string(value.effective_date,`${path}.effective_date`);string(value.known_at,`${path}.known_at`);return value}
  const transitionFields=['schema_version','engine_version','run_id','case_id','prior_state_id','policy_refs','affected_set','ordered_transitions','rule_switches','recomputed_values','unchanged_objects','human_stops','blocked_components','coverage_limits','invariant_checks','candidate_current_approved_delta','partial_settlement_status','replay_hash','source_event_id'];

  function validateProjection(projection){
    requireKeys(projection,['schema_version','package_version','disclosure','fund','deal','events','actor_directory'],'projection');
    requireKeys(projection.fund,['situations','morning_delta'],'projection.fund');array(projection.fund.situations,'projection.fund.situations');array(projection.fund.morning_delta,'projection.fund.morning_delta');
    requireKeys(projection.deal,['case_id','objective','as_of_state_id','as_of_date','temporal','question_spine','artifacts','claims','rooms','replay','source_center','archetype','lenses','participants','interactions','utterances','derivation_specs','derivations','discrepancy_rules','discrepancy_candidates','hypotheses','agent_missions','spine_change_proposals','condition_edges','validation_envelopes'],'projection.deal');
    for(const key of ['question_spine','artifacts','claims','lenses','participants','interactions','utterances','derivation_specs','derivations','discrepancy_rules','discrepancy_candidates','hypotheses','agent_missions','spine_change_proposals','condition_edges','validation_envelopes'])array(projection.deal[key],`projection.deal.${key}`);
    object(projection.deal.archetype,'projection.deal.archetype');
    requireKeys(projection.deal.rooms,['foundations','unknowns','shadowIC'],'projection.deal.rooms');requireKeys(projection.deal.replay,['source','hand_authored_snapshots','snapshots'],'projection.deal.replay');array(projection.deal.replay.snapshots,'projection.deal.replay.snapshots');
    if('graph_versions' in projection.deal)array(projection.deal.graph_versions,'projection.deal.graph_versions');
    if('current_graph' in projection.deal)object(projection.deal.current_graph,'projection.deal.current_graph');
    if('candidate_graph' in projection.deal)object(projection.deal.candidate_graph,'projection.deal.candidate_graph');
    if(projection.deal.replay.source!=='REGISTRY_EVENTS'||projection.deal.replay.hand_authored_snapshots!==false)fail('TEMPORAL_CONTRACT','projection.deal.replay','must be event-log derived');
    requireKeys(projection.deal.temporal,['basis','effective_axis','knowledge_axis','available_dates','replay_source'],'projection.deal.temporal');array(projection.deal.temporal.available_dates,'projection.deal.temporal.available_dates');
    projection.deal.claims.forEach((claim,index)=>bitemporal(claim,`projection.deal.claims[${index}]`));
    for(const key of ['lenses','interactions','utterances','derivation_specs','derivations','discrepancy_candidates','hypotheses','agent_missions','spine_change_proposals','condition_edges','validation_envelopes'])projection.deal[key].forEach((value,index)=>bitemporal(value,`projection.deal.${key}[${index}]`));
    const participantIds=new Set(projection.deal.participants.map(value=>value.participant_id||value.id));
    const interactionIds=new Set(projection.deal.interactions.map(value=>value.interaction_id||value.id));
    projection.deal.interactions.forEach((value,index)=>array(value.participant_ids,`projection.deal.interactions[${index}].participant_ids`).forEach(id=>{if(!participantIds.has(id))fail('BROKEN_REFERENCE',`projection.deal.interactions[${index}].participant_ids`,`${id} is not a participant`)}));
    projection.deal.utterances.forEach((value,index)=>{if(!interactionIds.has(value.interaction_id))fail('BROKEN_REFERENCE',`projection.deal.utterances[${index}].interaction_id`,`${value.interaction_id} is not an interaction`);if(!participantIds.has(value.speaker_id))fail('BROKEN_REFERENCE',`projection.deal.utterances[${index}].speaker_id`,`${value.speaker_id} is not a participant`)});
    projection.deal.claims.forEach((claim,index)=>{if(claim.observed_speech_act===true&&claim.epistemic_class!=='observed')fail('EPISTEMIC_CONTRACT',`projection.deal.claims[${index}]`,'an observed speech act must use observed');if(claim.utterance_id&&claim.observed_speech_act!==true&&claim.epistemic_class==='observed')fail('EPISTEMIC_CONTRACT',`projection.deal.claims[${index}]`,'content extracted from an utterance is not observed truth')});
    Object.values(projection.events||{}).forEach((event,index)=>bitemporal(event,`projection.events[${index}]`));
    object(projection.events,'projection.events');array(projection.actor_directory,'projection.actor_directory');return projection;
  }
  function validateContext(context){requireKeys(context,['mode','action_capability','case_id','projection_id','projection_hash','as_of_state_id','as_of_date','authenticated_actor','viewer_projection','authority_assignments','demo_session_id','synthetic','no_external_effects','contract_version','active_lens_id'],'context');array(context.authority_assignments,'context.authority_assignments');return context}
  function validateTransition(transition){requireKeys(transition,transitionFields,'transition');for(const key of ['affected_set','ordered_transitions','rule_switches','recomputed_values','unchanged_objects','human_stops','blocked_components','coverage_limits','invariant_checks'])array(transition[key],`transition.${key}`);object(transition.policy_refs,'transition.policy_refs');object(transition.candidate_current_approved_delta,'transition.candidate_current_approved_delta');object(transition.partial_settlement_status,'transition.partial_settlement_status');return transition}
  function validateAuthorityRecord(record){requireKeys(record,['authority_record_id','run_id','candidate_state_id','human_stop_id','course_id','actor_id','actor_role','timestamp','effective_date','known_at','artifact_hash','authority_verb','effect_type','status'],'authority_record');return bitemporal(record,'authority_record')}
  function validateExecutionPackage(pkg){requireKeys(pkg,['execution_package_id','run_id','candidate_state_id','course_id','authority_record_id','artifact_hash','status','created_at','effective_date','known_at','synthetic','no_external_effects'],'execution_package');return bitemporal(pkg,'execution_package')}
  function validateSettlement(result){requireKeys(result,['settlement_id','case_id','run_id','candidate_state_id','prior_state_id','current_state_id','selected_change_ids','partial','summary','replay_hash','timestamp','effective_date','known_at','as_of_state_id','as_of_date'],'settlement');array(result.selected_change_ids,'settlement.selected_change_ids');return bitemporal(result,'settlement')}
  function safe(fn,value){try{return{ok:true,value:fn(value),errors:[]}}catch(error){return{ok:false,value:null,errors:[{code:error.code||'VALIDATION_ERROR',path:error.path||'',message:error.message}]}}}
  window.PantaContracts={validateProjection,validateContext,validateTransition,validateAuthorityRecord,validateExecutionPackage,validateSettlement,safe,transitionFields};
})();
