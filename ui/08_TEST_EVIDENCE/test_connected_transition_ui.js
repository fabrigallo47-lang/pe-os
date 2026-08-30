'use strict';

const assert=require('assert');
const fs=require('fs');
const vm=require('vm');
const path=require('path');

const APP=path.resolve(__dirname,'../01_PRODUCT_BUILD/app/src');
global.window=global;
vm.runInThisContext(fs.readFileSync(path.join(APP,'projection_adapter.js'),'utf8'));

const raw={
  schema_version:'transition-output-1.0',engine_version:'test',run_id:'RUN-1',case_id:'CASE-1',prior_state_id:'STATE-0',source_event_id:'EVENT-1',policy_refs:{},
  affected_set:[{object_type:'CLAIM',object_id:'CL-1'}],ordered_transitions:[{component_id:'COMP-1',member_ids:['CL-1']}],rule_switches:[],recomputed_values:[],unchanged_objects:[],
  human_stops:[
    {stop_id:'STOP-1',object_or_component_id:'candidate-change-set',reason_code:'DECISION_REQUIRES_HUMAN',requested_action:'Review Current.',required_role:'REVIEWER',policy_rule_id:'AUTH-1',downstream_scope:['CL-1']},
    {stop_id:'STOP-2',object_or_component_id:'approved-snapshot',reason_code:'APPROVED_FROZEN',requested_action:'Authorize Approved.',required_role:'AUTHORITY_HOLDER',policy_rule_id:'AUTH-2',downstream_scope:['CL-1']},
    {stop_id:'STOP-BLOCKED',object_or_component_id:'CL-X',reason_code:'NO_ADMISSIBLE_SOLUTION',requested_action:'Correct blocked equations.',required_role:'PREPARER',policy_rule_id:'KERNEL-NUMERIC',downstream_scope:['CL-X']}
  ],
  blocked_components:[],coverage_limits:[],invariant_checks:[{invariant_id:'INV-1',status:'PASS'}],
  candidate_current_approved_delta:{candidate:[{object_type:'CLAIM',object_id:'CL-1',field:'value',from:1,to:2,reason_code:'DIRECT_EVENT_MUTATION'}],current:[],approved:[]},
  partial_settlement_status:{candidate:'PARTIAL',current:'REVIEW_PENDING',approved:'AUTHORITY_PENDING',settled_component_ids:['COMP-1'],unsettled_component_ids:['COMP-PENDING']},
  replay_hash:'sha256:test',candidate_state_id:'CANDIDATE-1'
};
const mapped=PantaProjectionAdapter.mapFrozenEngineOutput(raw);
assert.equal(mapped.change_sets[0].change_set_id,'CL-1');
assert.equal(mapped.human_stops[0].reason,'Review Current.');
assert.equal(mapped.human_stops[0].status,'OPEN');

global.location={pathname:'/ui',search:'',hash:'',origin:'http://panta.test'};
global.history={replaceState(){}};
global.document={getElementById(){return{textContent:''}}};
if(!global.navigator)Object.defineProperty(global,'navigator',{value:{},configurable:true});
global.setTimeout=()=>0;
let settlementPayload=null;
let state={
  context:{as_of_state_id:'STATE-0',as_of_date:'2026-08-30',authenticated_actor:{actor_id:'ACTOR-1',role:'REVIEWER'},authority_assignments:[]},
  activeRun:{run_id:'RUN-1'},transition:mapped,selectedChangeIds:['CL-1'],selectedCourseId:null,activeHumanStopId:'STOP-1',
  authorityRecord:null,authorityRecordsByStopId:{'STOP-1':{authority_record_id:'AUTH-1'}},executionPackage:null,
  executionPackagesByRecordId:{'AUTH-1':{execution_package_id:'EXEC-1',authority_record_id:'AUTH-1',status:'ACCEPTED'}},
  projection:{},registry:[],viewerProjection:'partner',mobileReadOnly:false
};
global.PantaStore={get:()=>state,set:patch=>{state=Object.assign({},state,typeof patch==='function'?patch(state):patch)},clone:value=>JSON.parse(JSON.stringify(value))};
global.PantaContracts={safe:()=>({ok:true}),validateProjection:value=>value,validateTransition:value=>value,validateAuthorityRecord:value=>value};
global.PantaConstants={rooms:[]};
global.PantaApi={
  uid:prefix=>`${prefix}-1`,
  adapter:()=>({
    settle:async(_runId,payload)=>{
      settlementPayload=payload;
      return{summary:'Settled',prior_state_id:'STATE-0',current_state_id:'STATE-1',candidate_state_id:'CANDIDATE-1',selected_change_ids:['CL-1'],replay_hash:'sha256:settled'};
    }
  })
};
vm.runInThisContext(fs.readFileSync(path.join(APP,'engine.js'),'utf8'));

assert.equal(PantaActions.decisionGate().human_stop.stop_id,'STOP-2');
state.authorityRecordsByStopId['STOP-2']={authority_record_id:'AUTH-2'};
state.executionPackagesByRecordId['AUTH-2']={execution_package_id:'EXEC-2',authority_record_id:'AUTH-2',status:'ACCEPTED'};

PantaActions.settleCurrent().then(()=>{
  assert.deepEqual(new Set(settlementPayload.authority_record_ids),new Set(['AUTH-1','AUTH-2']));
  assert.deepEqual(new Set(settlementPayload.execution_package_ids),new Set(['EXEC-1','EXEC-2']));
  assert.deepEqual(new Set(settlementPayload.human_stop_ids),new Set(['STOP-1','STOP-2']));
  assert.equal(settlementPayload.allow_partial_settlement,true);
  assert.equal(PantaActions.unresolvedHumanStops().length,0);
  assert.equal(PantaStore.get().view,'settled');
  console.log('connected transition UI tests passed');
}).catch(error=>{
  console.error(error);
  process.exitCode=1;
});
