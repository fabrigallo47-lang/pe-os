// Synthetic contract-only adapter for reproducible behavior tests.
// Lives outside production src/. Contains no real deal data.

const now='2026-01-10T10:00:00Z';
const later='2026-01-11T10:00:00Z';
const actor={id:'ACT-1',type:'PERSON',displayName:'Test Reviewer'};
const claim1={id:'CL-1',sourceId:'SRC-1',sourceVersionId:'SV-1',locator:'L1',type:'customer',label:'Deployment confirmed',normalizedStatement:'Deployment confirmed'};
const claim2={id:'CL-2',sourceId:'SRC-2',sourceVersionId:'SV-2',locator:'L1',type:'company',label:'Performance claim',normalizedStatement:'Performance claim'};
const reading0={id:'CR-1',questionId:'Q-1',text:'Performance remains unproven.',epistemicStatus:'INSUFFICIENT',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:[claim2.id],independentSupportObjectIds:[],unknownIds:['U-1'],relatedObjectIds:['Q-2']};
const reading1={...reading0,computedAt:later,supportObjectIds:[claim1.id,claim2.id],independentSupportObjectIds:[claim1.id],text:'Deployment is confirmed; performance remains unproven.'};
const position={id:'HP-1',authorActorId:actor.id,recordedAt:now,text:'The team should verify performance before committing.',scopeObjectId:'Q-1',institutionalState:'CURRENT'};
const base={
  caseRef:{id:'CASE-1',name:'Synthetic Case'},caseVersion:'v1',asOf:now,
  decision:{id:'DECCTX-1',label:'Commit or decline',status:'OPEN',requiredEntitlement:'RECORD_DECISION'},
  actors:[actor],workstreams:[{id:'WS-1',name:'Technical Proof',currentCaseReadingId:'CR-1',activeWorkItemIds:['WI-1'],openUnknownIds:['U-1'],questionIds:['Q-1']}],
  questions:[{id:'Q-1',workstreamId:'WS-1',name:'Does the product work?',questionStatus:'OPEN',currentCaseReadingId:'CR-1',claimIds:['CL-1','CL-2'],workItemIds:['WI-1'],openUnknownIds:['U-1'],chronologyEventIds:['EV-1']}],
  caseReadings:[reading0],unknowns:[{id:'U-1',title:'Independent performance evidence',targetObjectIds:['Q-1'],status:'OPEN'}],
  sources:[{id:'SRC-1',type:'call',title:'Customer reference'},{id:'SRC-2',type:'document',title:'Company material'}],sourceVersions:[{id:'SV-1',sourceId:'SRC-1',contentHash:'h1',knownAt:now,permissionScope:'case'},{id:'SV-2',sourceId:'SRC-2',contentHash:'h2',knownAt:now,permissionScope:'case'}],claims:[claim1,claim2],
  metricDefinitions:[],metricObservations:[],assumptions:[],risks:[],modelNodes:[],outcomes:[],
  findings:[],humanPositions:[position],workItems:[{id:'WI-1',name:'Verify performance',status:'ACTIVE',kind:'VERIFICATION_ROUTE',canChangeObjectIds:['CR-1'],remainingUnknownIds:['U-1'],institutionalState:'CURRENT'}],
  quantities:[{id:'QTY-1',label:'Raise size',value:5,display:'€5m',unit:'EURm',perimeter:{scope:'current round'},sourceObjectIds:['CL-2'],assumptionObjectIds:[],downstreamObjectIds:['CR-1'],editable:false,institutionalState:'CURRENT',freshnessStatus:'CURRENT'}],
  artifacts:[{id:'ART-1',type:'IC_MEMO',title:'IC Memo',freshnessStatus:'STALE',pendingCaseChangeCount:1,syncStatus:'STALE',blockIds:['AB-1'],quantityIds:[]}],
  artifactBlocks:[{id:'AB-1',artifactId:'ART-1',text:'Performance remains unproven.',authorship:'CASE_BACKED',boundObjectIds:['CR-1']}],artifactDiffs:[],
  relations:[{id:'REL-1',caseId:'CASE-1',sourceObjectId:'CL-2',sourceObjectType:'claim',targetObjectId:'CR-1',targetObjectType:'caseReading',type:'SUPPORTS',institutionalState:'CURRENT',contractVersion:'0.1.0'},
             {id:'REL-2',caseId:'CASE-1',sourceObjectId:'CR-1',sourceObjectType:'caseReading',targetObjectId:'Q-2',targetObjectType:'question',type:'DRIVES',institutionalState:'CURRENT',contractVersion:'0.1.0'}],
  events:[{id:'EV-1',caseId:'CASE-1',eventType:'CASE_READING_RECOMPUTED',objectType:'caseReading',objectId:'CR-1',effectiveAt:now,knownAt:now,recordedAt:now,actorOrPolicyId:'SYSTEM',schemaVersion:'0.1.0',idempotencyKey:'ev1'}],
  pendingReviews:[],simulationOptions:[{id:'SIM-1',originObjectId:'CR-1',label:'What if performance fails?',assumption:'Representative test fails',enabled:true}],
  conditions:[{id:'COND-1',label:'Performance verification',targetObjectIds:['DECCTX-1'],status:'OPEN',unknownIds:['U-1'],relatedObjectIds:['CR-1']}],
  decisionPaths:[{id:'PATH-1',label:'DEFER',meaning:'Wait for evidence.'}],decisions:[]
};

function clone(x){return JSON.parse(JSON.stringify(x));}

export class SyntheticAdapter {
  constructor(){this.current=clone(base);}
  async getSession(){return {actor:{actorId:actor.id,entitlements:['READ_CASE','RECORD_DECISION','SYNC_ARTIFACT']},actors:[actor]};}
  async listCases(){return [{id:'CASE-1',name:'Synthetic Case'}];}
  async listCaseMoments(){return [{id:'M-1',asOf:now,label:'Day 1',eventId:'EV-1'},{id:'M-2',asOf:later,label:'Day 2',eventId:'EV-2'}];}
  async loadCase(_caseId,opts){
    if(opts?.asOf && opts.asOf < later){const s=clone(base);s.asOf=opts.asOf;return s;}
    const s=clone(this.current);s.asOf=opts?.asOf??later;s.caseReadings=[clone(reading1)];return s;
  }
  async inspectObject(_caseId,objectId,opts){
    const excluded=new Set(opts?.excludeObjectIds??[]);
    const supports=(objectId==='CR-1'?['CL-1','CL-2']:[]).filter(x=>!excluded.has(x));
    return {objectId,supportObjectIds:supports,independentSupportObjectIds:supports.filter(x=>x==='CL-1'),unknownIds:objectId==='CR-1'?['U-1']:[],dependentObjectIds:objectId==='CR-1'?['Q-2']:[],lastChangeEventId:'EV-1',relatedObjectIds:['ART-1'],sourceLocators:supports.map(x=>({sourceId:x==='CL-1'?'SRC-1':'SRC-2',claimId:x})),allowedActions:['TRACE','SIMULATE','RESOLVE','OPEN_SOURCE','VIEW_IN_CASE']};
  }
  async searchCase(_caseId,q){return q? [{objectId:'CR-1',label:'Performance remains unproven',kind:'caseReading'}]:[];}
  async runSimulation(){return {id:'SR-1',request:{optionId:'SIM-1',originObjectId:'CR-1',assumption:'Representative test fails'},effects:[{objectId:'CR-1',objectLabel:'Technical reading',state:'WEAKENS',before:'Unproven',after:'Negative evidence',reasonRelationIds:['REL-2']},{objectId:'WS-1',objectLabel:'Team',state:'HOLDS',before:'Unchanged',after:'Unchanged',reasonRelationIds:[]}],coverage:{examinedCount:2,changedCount:1,heldCount:1,unmappedCount:0}};}
  async execute(_caseId,command){
    if(command.action.type==='RECORD_DECISION'){
      this.current.decisions=[{id:'DEC-1',pathId:command.action.pathId,actorOrBodyId:command.actorId,rationale:command.action.rationale,recordedAt:command.submittedAt,caseVersion:this.current.caseVersion}];
      this.current.decision.status='RECORDED';this.current.decision.recordedDecisionId='DEC-1';
      return clone(this.current);
    }
    if(command.action.type==='SYNC_ARTIFACT'){
      const a=this.current.artifacts.find(x=>x.id===command.action.artifactId);if(a){a.pendingCaseChangeCount=0;a.syncStatus='CURRENT';a.freshnessStatus='CURRENT';a.lastSyncedCaseVersion=this.current.caseVersion;a.lastSyncedAt=command.submittedAt;}
      return clone(this.current);
    }
    return clone(this.current);
  }
}
