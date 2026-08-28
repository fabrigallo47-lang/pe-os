(function(){
  'use strict';
  const clone=value=>value==null?value:JSON.parse(JSON.stringify(value));
  const arr=value=>Array.isArray(value)?value:(value&&typeof value==='object'?Object.values(value):[]);
  const required=(obj,path)=>path.split('.').reduce((value,key)=>value&&value[key],obj);
  const FROZEN_REQUIRED=['schema_version','engine_version','run_id','case_id','prior_state_id','policy_refs','affected_set','ordered_transitions','rule_switches','recomputed_values','unchanged_objects','human_stops','blocked_components','coverage_limits','invariant_checks','candidate_current_approved_delta','partial_settlement_status','replay_hash'];
  const INTEGRATION_REQUIRED=[...FROZEN_REQUIRED,'source_event_id'];

  function validateProjection(p){
    const errors=[];
    if(!p||typeof p!=='object'||Array.isArray(p))return{ok:false,errors:['Projection is not an object']};
    for(const path of ['schema_version','package_version','fund.situations','deal.case_id','deal.as_of_state_id','deal.as_of_date','deal.temporal','deal.question_spine','deal.claims','deal.rooms','deal.replay.snapshots','deal.source_center.sources','events','actor_directory']){
      const value=required(p,path);if(value===undefined||value===null)errors.push(`Missing ${path}`)
    }
    for(const path of ['fund.situations','deal.question_spine','deal.claims','deal.replay.snapshots','deal.source_center.sources','actor_directory'])if(required(p,path)!=null&&!Array.isArray(required(p,path)))errors.push(`${path} must be an array`);
    (p.deal?.claims||[]).forEach((claim,index)=>{if(!claim.effective_date||!claim.known_at)errors.push(`deal.claims[${index}] lacks effective_date/known_at`)});
    Object.values(p.events||{}).forEach((event,index)=>{if(!event.effective_date||!event.known_at)errors.push(`events[${index}] lacks effective_date/known_at`)});
    return{ok:errors.length===0,errors};
  }

  function validateTransition(t){
    const errors=[];
    if(!t||typeof t!=='object'||Array.isArray(t))return{ok:false,errors:['Transition is not an object']};
    for(const key of INTEGRATION_REQUIRED)if(t[key]===undefined||t[key]===null)errors.push(`Missing transition.${key}`);
    for(const key of ['affected_set','ordered_transitions','rule_switches','recomputed_values','unchanged_objects','human_stops','blocked_components','coverage_limits','invariant_checks'])if(t[key]!=null&&!Array.isArray(t[key]))errors.push(`${key} must be an array`);
    return{ok:errors.length===0,errors};
  }

  function mapFrozenEngineOutput(output){
    const check=validateTransition(output);if(!check.ok){const error=new Error(`Transition mapping rejected: ${check.errors.join('; ')}`);error.code='INVALID_ENGINE_OUTPUT';error.details=check.errors;throw error}
    const affected=arr(output.affected_set).map((item,index)=>({
      ...clone(item),order:item.order??index,object_id:item.object_id||item.target_ref||item.model_node_id||item.id,
      label:item.label||item.name||item.object_id||item.target_ref||item.model_node_id||item.id,
      disposition:item.disposition||item.behavior||item.transition_type||'RECOMPUTES',
      before:item.before??item.old_value??item.old??null,after:item.after??item.new_value??item.new??null,
      explanation:item.explanation||item.reason||item.detail||'',source_trace:item.source_trace||item.source_ref||null
    })).sort((a,b)=>(a.order-b.order)||String(a.object_id).localeCompare(String(b.object_id)));
    const candidate=output.candidate_current_approved_delta?.candidate||{},partial=output.partial_settlement_status||{};
    return{
      ...clone(output),affected_set:affected,candidate_state_id:output.candidate_state_id||candidate.state_id,
      as_of_state_id:output.as_of_state_id||output.prior_state_id,status:output.status||partial.candidate||candidate.status||'UNKNOWN',
      artifact_change_sets:arr(output.artifact_change_sets),policy_result:clone(output.policy_result||{}),
      mapping_contract:{name:'frozen-engine-output-to-frontend-transition',version:'20.0.0',frozen_required_field_count:FROZEN_REQUIRED.length,integration_required_field_count:INTEGRATION_REQUIRED.length,source_event_id:output.source_event_id,pure_function:true}
    };
  }
  const normalizeTransition=mapFrozenEngineOutput;
  window.PantaProjectionAdapter={validateProjection,validateTransition,mapFrozenEngineOutput,normalizeTransition,clone,FROZEN_REQUIRED,INTEGRATION_REQUIRED};
})();
