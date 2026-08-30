(function(){
  'use strict';
  const clone=value=>value==null?value:JSON.parse(JSON.stringify(value));
  const arr=value=>Array.isArray(value)?value:(value&&typeof value==='object'?Object.values(value):[]);
  const required=(obj,path)=>path.split('.').reduce((value,key)=>value&&value[key],obj);
  const FROZEN_REQUIRED=['schema_version','engine_version','run_id','case_id','prior_state_id','policy_refs','affected_set','ordered_transitions','rule_switches','recomputed_values','unchanged_objects','human_stops','blocked_components','coverage_limits','invariant_checks','candidate_current_approved_delta','partial_settlement_status','replay_hash'];
  const INTEGRATION_REQUIRED=[...FROZEN_REQUIRED,'source_event_id'];
  const NON_ATTESTABLE_REASONS=new Set(['BATCH_VALUE_CONFLICT','CIRCULAR_SUPPORT','MISSING_RULE_PROVENANCE','NON_WAIVABLE_AXIOM','UPSTREAM_INPUT_BLOCKED']);

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
    const candidate=t.candidate_current_approved_delta?.candidate;
    if(candidate!=null&&!Array.isArray(candidate)&&(typeof candidate!=='object'||candidate===null))errors.push('candidate_current_approved_delta.candidate must be an object or array');
    return{ok:errors.length===0,errors};
  }

  function normalizeHumanStop(item){
    const reasonCode=String(item.reason_code||'HUMAN_REVIEW_REQUIRED'),requiredRole=String(item.required_role||'UNSPECIFIED_REVIEWER');
    const requestedAction=String(item.requested_action||item.reason||reasonCode),explicitAttestable=typeof item.attestable==='boolean'?item.attestable:null;
    const attestable=explicitAttestable??(requiredRole!=='PREPARER'&&!NON_ATTESTABLE_REASONS.has(reasonCode));
    const resolutionKind=item.resolution_kind||(reasonCode==='NON_WAIVABLE_AXIOM'?'NON_WAIVABLE_BLOCK':attestable?'AUTHORITY_ATTESTATION':'INPUT_OR_MODEL_CORRECTION');
    return{
      ...clone(item),stop_id:String(item.stop_id||''),object_id:String(item.object_id||item.object_or_component_id||item.component_id||''),
      reason_code:reasonCode,requested_action:requestedAction,reason:String(item.reason||requestedAction||reasonCode),required_role:requiredRole,
      required_authority_level:String(item.required_authority_level||requiredRole),authority_verb:String(item.authority_verb||'RESOLVE_HUMAN_STOP'),
      downstream_scope:arr(item.downstream_scope),status:String(item.status||'OPEN'),resolution_kind:resolutionKind,attestable
    };
  }

  function normalizeBlockedComponent(item){
    const reasonCode=String(item.reason_code||'BLOCKED'),resolution=item.resolvable_by??item.missing_assumption_or_condition??null;
    return{
      ...clone(item),component_id:String(item.component_id||''),member_ids:arr(item.member_ids),reason_code:reasonCode,
      reason:String(item.reason||resolution||reasonCode),downstream_scope:arr(item.downstream_scope||item.dependent_ids),
      resolvable_by:resolution==null?null:String(resolution),status:String(item.status||'BLOCKED')
    };
  }

  function normalizeSuppliedChangeSet(item){
    const id=String(item.change_set_id||item.artifact_id||item.change_id||item.id||'');
    return{
      ...clone(item),change_set_id:id,artifact_id:id,title:String(item.title||item.label||id),status:String(item.status||'PREPARED'),
      changes:arr(item.changes),object_ids:arr(item.object_ids),component_ids:arr(item.component_ids),
      blocking_stop_ids:arr(item.blocking_stop_ids),blocked_component_ids:arr(item.blocked_component_ids)
    };
  }

  function deriveChangeSets(output,candidateDeltas,humanStops,blockedComponents){
    const supplied=arr(output.change_sets?.length?output.change_sets:output.artifact_change_sets);
    if(supplied.length)return supplied.map(normalizeSuppliedChangeSet).filter(item=>item.change_set_id);
    return candidateDeltas.map(delta=>{
      const objectId=String(delta.object_id||'');if(!objectId)return null;
      const componentIds=arr(output.ordered_transitions).filter(item=>arr(item.member_ids).includes(objectId)).map(item=>item.component_id).filter(Boolean);
      const blockedIds=blockedComponents.filter(item=>item.member_ids.includes(objectId)||item.downstream_scope.includes(objectId)).map(item=>item.component_id);
      const stopIds=humanStops.filter(item=>item.object_id===objectId||item.downstream_scope.includes(objectId)).map(item=>item.stop_id);
      const before=delta.before??delta.from??delta.old_value??null,after=delta.after??delta.to??delta.new_value??null;
      return{
        change_set_id:objectId,artifact_id:objectId,title:`${delta.object_type||'OBJECT'} ${objectId}`,status:blockedIds.length?'BLOCKED':'PREPARED',
        object_ids:[objectId],component_ids:componentIds,blocking_stop_ids:stopIds,blocked_component_ids:blockedIds,
        changes:[{change_id:String(delta.change_id||objectId),object_id:objectId,field:delta.field||null,label:String(delta.label||delta.field||objectId),before:clone(before),after:clone(after),reason_code:delta.reason_code||null}]
      };
    }).filter(Boolean);
  }

  function mapFrozenEngineOutput(output){
    const check=validateTransition(output);if(!check.ok){const error=new Error(`Transition mapping rejected: ${check.errors.join('; ')}`);error.code='INVALID_ENGINE_OUTPUT';error.details=check.errors;throw error}
    const delta=output.candidate_current_approved_delta||{},candidateValue=delta.candidate,candidateMetadata=Array.isArray(candidateValue)?{}:(candidateValue||{}),candidateDeltas=Array.isArray(candidateValue)?candidateValue:[];
    const valueById=new Map(candidateDeltas.filter(item=>item?.object_id).map(item=>[String(item.object_id),item]));
    for(const value of arr(output.recomputed_values))if(value?.object_id&&!valueById.has(String(value.object_id)))valueById.set(String(value.object_id),value);
    const affected=arr(output.affected_set).map((item,index)=>{
      const objectId=item.object_id||item.target_ref||item.model_node_id||item.id,deltaValue=valueById.get(String(objectId))||{};
      return{
        ...clone(item),order:item.order??index,object_id:objectId,label:item.label||item.name||objectId,
        disposition:item.disposition||item.behavior||item.transition_type||'RECOMPUTES',
        before:item.before??item.old_value??item.old??deltaValue.before??deltaValue.from??deltaValue.old_value??null,
        after:item.after??item.new_value??item.new??deltaValue.after??deltaValue.to??deltaValue.candidate_value??deltaValue.new_value??null,
        explanation:item.explanation||item.reason||item.detail||deltaValue.reason||deltaValue.reason_code||'',source_trace:item.source_trace||item.source_ref||null
      };
    }).sort((a,b)=>(a.order-b.order)||String(a.object_id).localeCompare(String(b.object_id)));
    const humanStops=arr(output.human_stops).map(normalizeHumanStop),blockedComponents=arr(output.blocked_components).map(normalizeBlockedComponent);
    const changeSets=deriveChangeSets(output,candidateDeltas,humanStops,blockedComponents),partial=output.partial_settlement_status||{};
    const mapped={
      ...clone(output),affected_set:affected,human_stops:humanStops,blocked_components:blockedComponents,
      invariant_checks:arr(output.invariant_checks).map(item=>({...clone(item),check_id:item.check_id||item.invariant_id||''})),
      as_of_state_id:output.as_of_state_id||output.prior_state_id,status:output.status||partial.candidate||candidateMetadata.status||'UNKNOWN',
      change_sets:changeSets,artifact_change_sets:clone(changeSets),policy_result:clone(output.policy_result||{}),
      mapping_contract:{name:'frozen-engine-output-to-frontend-transition',version:'20.1.0',frozen_required_field_count:FROZEN_REQUIRED.length,integration_required_field_count:INTEGRATION_REQUIRED.length,source_event_id:output.source_event_id,pure_function:true}
    };
    const candidateStateId=output.candidate_state_id||candidateMetadata.state_id;if(candidateStateId)mapped.candidate_state_id=candidateStateId;else delete mapped.candidate_state_id;
    return mapped;
  }
  const normalizeTransition=mapFrozenEngineOutput;
  window.PantaProjectionAdapter={validateProjection,validateTransition,mapFrozenEngineOutput,normalizeTransition,normalizeHumanStop,normalizeBlockedComponent,deriveChangeSets,clone,FROZEN_REQUIRED,INTEGRATION_REQUIRED};
})();
