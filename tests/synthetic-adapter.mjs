// Synthetic contract-only adapter for reproducible behavior tests.
// Lives outside production src/. Contains no real deal data.

const now='2026-01-10T10:00:00Z';
const customerAdmittedAt='2026-01-10T14:00:00Z';
const later='2026-01-11T10:00:00Z';
const actor={id:'ACT-1',type:'PERSON',displayName:'Mara Bellini',role:'Case Owner'};
const contributor={id:'ACT-2',type:'PERSON',displayName:'Jonas Reed',role:'Investment Associate'};
const claim1={id:'CL-1',sourceId:'SRC-1',sourceVersionId:'SV-1',locator:'L1',type:'customer',label:'Deployment confirmed',normalizedStatement:'Deployment confirmed'};
const claim2={id:'CL-2',sourceId:'SRC-2',sourceVersionId:'SV-2',locator:'L1',type:'company',label:'Performance claim',normalizedStatement:'Performance claim'};
const reading0={id:'CR-1',questionId:'Q-1',text:'Performance remains unproven.',epistemicStatus:'INSUFFICIENT',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:[claim2.id],independentSupportObjectIds:[],unknownIds:['U-1'],relatedObjectIds:['Q-C']};
const reading1={...reading0,computedAt:later,supportObjectIds:[claim1.id,claim2.id],independentSupportObjectIds:[claim1.id],text:'Deployment is confirmed; performance remains unproven.'};
const currentReadingEvent={id:'EV-3',caseId:'CASE-1',eventType:'CASE_READING_RECOMPUTED',objectType:'caseReading',objectId:'CR-1',effectiveAt:later,knownAt:later,recordedAt:later,actorOrPolicyId:'SYSTEM',schemaVersion:'0.1.0',idempotencyKey:'ev3',sourceEventId:'EV-2',causationId:'EV-2'};
const teamReading={id:'CR-T',questionId:'Q-T',text:'The founders have strong domain access; the senior delivery bench is not yet proven.',epistemicStatus:'CONTESTED',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:['CL-3','CL-4'],independentSupportObjectIds:[],unknownIds:['U-T'],relatedObjectIds:['Q-T']};
const marketReading={id:'CR-M',questionId:'Q-M',text:'Buyers describe an urgent operational problem, but budget ownership is inconsistent.',epistemicStatus:'CONTESTED',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:['CL-1','CL-5'],independentSupportObjectIds:['CL-1'],unknownIds:['U-M'],relatedObjectIds:['Q-M']};
const commercialReading={id:'CR-C',questionId:'Q-C',text:'Founder-led access opens doors; a repeatable commercial route is not established.',epistemicStatus:'INSUFFICIENT',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:['CL-3','CL-6'],independentSupportObjectIds:[],unknownIds:['U-C'],relatedObjectIds:['Q-C']};
const defensibilityReading={id:'CR-D',questionId:'Q-D',text:'Workflow depth appears differentiated today; the durability of that edge is untested.',epistemicStatus:'CONTESTED',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:['CL-5','CL-7'],independentSupportObjectIds:['CL-5'],unknownIds:['U-D'],relatedObjectIds:['Q-D']};
const financingReading={id:'CR-F',questionId:'Q-F',text:'The round provides operating runway, while entry value depends on two unverified milestones.',epistemicStatus:'CONTESTED',freshnessStatus:'CURRENT',decisionLinkStatus:'NO_DECISION',computedAt:now,supportObjectIds:['CL-8','CL-9'],independentSupportObjectIds:[],unknownIds:['U-F'],relatedObjectIds:['Q-F']};
const position={id:'HP-1',authorActorId:actor.id,recordedAt:now,text:'The team should verify performance before committing.',scopeObjectId:'Q-1',institutionalState:'CURRENT'};
const finding={id:'F-1',title:'Performance evidence conflicts',proposition:'The customer deployment does not independently verify the company performance claim.',scopeObjectId:'Q-1',foundAtEventId:'EV-2',derivationObjectIds:['CL-1','CL-2'],affectedObjectIds:['Q-1','CR-1'],status:'NEW'};
const decision1={id:'DEC-1',pathId:'PATH-1',actorOrBodyId:actor.id,rationale:'Wait for independent verification.',recordedAt:'2026-01-10T16:00:00Z',caseVersion:'v1'};
const decision2={id:'DEC-2',pathId:'PATH-2',actorOrBodyId:actor.id,rationale:'A later unlinked committee note.',recordedAt:'2026-01-11T09:00:00Z',caseVersion:'v1'};
const base={
  caseRef:{id:'CASE-1',name:'Synthetic Case'},caseVersion:'v1',asOf:now,
  decision:{id:'DECCTX-1',label:'Commit or decline',dueAt:'2026-01-15T16:00:00Z',status:'OPEN',requiredEntitlement:'RECORD_DECISION'},
  actors:[actor,contributor],
  workstreams:[
    {id:'WS-T',name:'Team & Execution',currentCaseReadingId:'CR-T',ownerActorId:'ACT-1',activeWorkItemIds:['WI-T'],openUnknownIds:['U-T'],questionIds:['Q-T']},
    {id:'WS-1',name:'Product & Technical Proof',currentCaseReadingId:'CR-1',ownerActorId:'ACT-2',activeWorkItemIds:['WI-1'],openUnknownIds:['U-1'],questionIds:['Q-1']},
    {id:'WS-M',name:'Buyer & Market Importance',currentCaseReadingId:'CR-M',activeWorkItemIds:['WI-M'],openUnknownIds:['U-M'],questionIds:['Q-M']},
    {id:'WS-C',name:'Commercial Route',currentCaseReadingId:'CR-C',activeWorkItemIds:['WI-C'],openUnknownIds:['U-C'],questionIds:['Q-C']},
    {id:'WS-D',name:'Competition & Defensibility',currentCaseReadingId:'CR-D',activeWorkItemIds:['WI-D'],openUnknownIds:['U-D'],questionIds:['Q-D']},
    {id:'WS-F',name:'Financing & Entry Terms',currentCaseReadingId:'CR-F',ownerActorId:'ACT-1',activeWorkItemIds:['WI-F'],openUnknownIds:['U-F'],questionIds:['Q-F']}
  ],
  questions:[
    {id:'Q-T',workstreamId:'WS-T',name:'Can this team scale delivery beyond the founders?',questionStatus:'OPEN',currentCaseReadingId:'CR-T',claimIds:['CL-3','CL-4'],workItemIds:['WI-T'],openUnknownIds:['U-T'],chronologyEventIds:[]},
    {id:'Q-1',workstreamId:'WS-1',name:'Does the product perform reliably in production?',questionStatus:'OPEN',currentCaseReadingId:'CR-1',claimIds:['CL-1','CL-2'],workItemIds:['WI-1'],openUnknownIds:['U-1'],chronologyEventIds:['EV-1'],decisionRelevance:'The underwriting depends on the product delivering its claimed performance in representative production conditions.',decisionDimensions:{loadBearingness:{text:'The product thesis materially depends on reliable performance beyond a single deployment.',basisObjectIds:['CR-1']},severity:{text:'If performance fails, adoption, retention and expansion assumptions all weaken.',basisObjectIds:['U-1']},fragility:{text:'One independent benchmark across representative workloads could materially change the current view.',basisObjectIds:['CL-1','CL-2']},decisionCriticality:{text:'This must be resolved or carried as an explicit closing condition before committing.',basisObjectIds:['COND-1']},conditionId:'COND-1'}},
    {id:'Q-M',workstreamId:'WS-M',name:'Is this problem urgent enough to command budget?',questionStatus:'OPEN',currentCaseReadingId:'CR-M',claimIds:['CL-1','CL-5'],workItemIds:['WI-M'],openUnknownIds:['U-M'],chronologyEventIds:[],decisionRelevance:'The case requires a buyer problem important enough to survive budget scrutiny and renew.',decisionDimensions:{loadBearingness:{text:'The growth case depends on a durable budget owner, not urgency alone.',basisObjectIds:['CR-M']},severity:{text:'If budget ownership is weak, conversion and renewal can both fall below plan.',basisObjectIds:['U-M']},fragility:{text:'Two buyer conversations could move the view quickly because current budget evidence is thin.',basisObjectIds:['CL-1','U-M']},decisionCriticality:{text:'The budget path needs to be understood before the IC can underwrite repeatable demand.',basisObjectIds:['U-M']}}},
    {id:'Q-C',workstreamId:'WS-C',name:'Can customer acquisition become repeatable?',questionStatus:'OPEN',currentCaseReadingId:'CR-C',claimIds:['CL-3','CL-6'],workItemIds:['WI-C'],openUnknownIds:['U-C'],chronologyEventIds:[],decisionRelevance:'The operating plan assumes customer acquisition can move beyond founder relationships.',decisionDimensions:{loadBearingness:{text:'The return case materially depends on a repeatable route to deployed customers.',basisObjectIds:['CR-C']},severity:{text:'If acquisition remains founder-led, growth slows and the organization does not scale as planned.',basisObjectIds:['U-C']},fragility:{text:'A reconstruction of the last ten opportunities could materially strengthen or weaken the view.',basisObjectIds:['CL-6','U-C']},decisionCriticality:{text:'IC needs a credible repeatability view before committing to the growth plan.',basisObjectIds:['U-C']}}},
    {id:'Q-D',workstreamId:'WS-D',name:'Will the product remain distinct as incumbents respond?',questionStatus:'OPEN',currentCaseReadingId:'CR-D',claimIds:['CL-5','CL-7'],workItemIds:['WI-D'],openUnknownIds:['U-D'],chronologyEventIds:[]},
    {id:'Q-F',workstreamId:'WS-F',name:'Do the round and entry terms leave enough room for the plan?',questionStatus:'OPEN',currentCaseReadingId:'CR-F',claimIds:['CL-8','CL-9'],workItemIds:['WI-F'],openUnknownIds:['U-F'],chronologyEventIds:[],decisionRelevance:'Entry value depends on the round funding the plan without relying on unverified milestones.',decisionDimensions:{loadBearingness:{text:'The return profile depends on both entry price and sufficient runway to reach the next value inflection.',basisObjectIds:['CR-F']},severity:{text:'If milestones slip, dilution or an earlier financing could impair the underwritten return.',basisObjectIds:['U-F']},fragility:{text:'The current view can move materially when burn, terms and milestone timing are reconciled.',basisObjectIds:['CL-8','CL-9']},decisionCriticality:{text:'IC needs one reconciled financing plan before committing capital.',basisObjectIds:['U-F']}}}
  ],
  caseReadings:[reading0,teamReading,marketReading,commercialReading,defensibilityReading,financingReading],
  unknowns:[
    {id:'U-1',title:'Independent production benchmark across representative workloads',targetObjectIds:['Q-1'],materiality:'HIGH',resolutionPath:'Run an agreed benchmark with a customer dataset.',status:'OPEN',workItemIds:['WI-1']},
    {id:'U-T',title:'Evidence that delivery can scale beyond founder involvement',targetObjectIds:['Q-T'],resolutionPath:'Reference two implementations led by the wider team.',status:'OPEN',ownerActorId:'ACT-1',workItemIds:['WI-T']},
    {id:'U-M',title:'Named budget owner and renewal logic across the target buyer set',targetObjectIds:['Q-M'],resolutionPath:'Confirm budget path in the next two customer calls.',status:'OPEN',ownerActorId:'ACT-2',workItemIds:['WI-M']},
    {id:'U-C',title:'A repeatable route from qualified lead to deployed customer',targetObjectIds:['Q-C'],materiality:'HIGH',resolutionPath:'Rebuild the last ten opportunities by source, stage and cycle time.',status:'OPEN',workItemIds:['WI-C']},
    {id:'U-D',title:'Evidence that the workflow advantage survives incumbent bundling',targetObjectIds:['Q-D'],resolutionPath:'Test switching reasons and roadmap overlap with three buyers.',status:'OPEN',ownerActorId:'ACT-2',workItemIds:['WI-D']},
    {id:'U-F',title:'Terms and milestone assumptions behind the next financing need',targetObjectIds:['Q-F'],resolutionPath:'Reconcile the operating plan with the draft term sheet.',status:'OPEN',ownerActorId:'ACT-1',workItemIds:['WI-F']}
  ],
  sources:[
    {id:'SRC-2',type:'company_deck',title:'Company deck',origin:'Company',currentVersionId:'SV-2',excerpt:'Product architecture, reported performance, pipeline and operating plan.'},
    {id:'SRC-3',type:'founder_call',title:'Founder call',origin:'Founders',currentVersionId:'SV-3',excerpt:'Team history, product choices, customer access and hiring plan.'},
    {id:'SRC-1',type:'customer_reference',title:'Customer reference',origin:'Customer',currentVersionId:'SV-1',excerpt:'Deployment experience, urgency of the problem and buying path.'},
    {id:'SRC-4',type:'internal_notes',title:'Investment-team notes',origin:'Fund',currentVersionId:'SV-4',excerpt:'Partner reactions, diligence concerns and the initial underwriting frame.'},
    {id:'SRC-5',type:'market_work',title:'Market and competitor work',origin:'Fund research',currentVersionId:'SV-5',excerpt:'Buyer alternatives, incumbent roadmaps and market structure.'},
    {id:'SRC-6',type:'financing_terms',title:'Financing and term summary',origin:'Company and counsel',currentVersionId:'SV-6',excerpt:'Round size, runway, proposed price and milestone assumptions.'}
  ],
  sourceVersions:[
    {id:'SV-1',sourceId:'SRC-1',contentHash:'h1',knownAt:now,permissionScope:'case'},
    {id:'SV-2',sourceId:'SRC-2',contentHash:'h2',knownAt:now,permissionScope:'case'},
    {id:'SV-3',sourceId:'SRC-3',contentHash:'h3',knownAt:now,permissionScope:'case'},
    {id:'SV-4',sourceId:'SRC-4',contentHash:'h4',knownAt:now,permissionScope:'case'},
    {id:'SV-5',sourceId:'SRC-5',contentHash:'h5',knownAt:now,permissionScope:'case'},
    {id:'SV-6',sourceId:'SRC-6',contentHash:'h6',knownAt:now,permissionScope:'case'}
  ],
  claims:[claim1,claim2,
    {id:'CL-3',sourceId:'SRC-3',sourceVersionId:'SV-3',locator:'Call notes · team',type:'founder',label:'Founder-led delivery',normalizedStatement:'Founders lead the largest customer implementations.'},
    {id:'CL-4',sourceId:'SRC-4',sourceVersionId:'SV-4',locator:'Team note',type:'internal',label:'Execution bench concern',normalizedStatement:'The senior delivery bench has not been tested at the planned scale.'},
    {id:'CL-5',sourceId:'SRC-5',sourceVersionId:'SV-5',locator:'Buyer map',type:'market',label:'Operational urgency',normalizedStatement:'Target buyers treat the workflow as urgent when failure risk is visible.'},
    {id:'CL-6',sourceId:'SRC-4',sourceVersionId:'SV-4',locator:'Pipeline review',type:'internal',label:'Founder-led pipeline',normalizedStatement:'Most qualified opportunities originated through founder relationships.'},
    {id:'CL-7',sourceId:'SRC-5',sourceVersionId:'SV-5',locator:'Competitor matrix',type:'market',label:'Workflow differentiation',normalizedStatement:'The product covers workflow steps not present in current incumbent modules.'},
    {id:'CL-8',sourceId:'SRC-6',sourceVersionId:'SV-6',locator:'Term summary',type:'financing',label:'Proposed round',normalizedStatement:'The proposed financing funds the current operating plan.'},
    {id:'CL-9',sourceId:'SRC-2',sourceVersionId:'SV-2',locator:'Operating plan',type:'company',label:'Milestone-dependent plan',normalizedStatement:'The next financing assumption depends on two commercial milestones.'}
  ],
  metricDefinitions:[],metricObservations:[],assumptions:[],risks:[],modelNodes:[],outcomes:[],
  findings:[finding],humanPositions:[position],workItems:[
    {id:'WI-1',name:'Verify production performance',status:'BLOCKED',kind:'VERIFICATION_ROUTE',whatToObtain:'A benchmark across representative customer workloads.',canChangeObjectIds:['CR-1'],remainingUnknownIds:['U-1'],institutionalState:'CURRENT'},
    {id:'WI-T',name:'Check delivery depth',ownerActorId:'ACT-1',status:'ACTIVE',kind:'EVIDENCE_ROUTE',whatToObtain:'Two implementations led by non-founder team members.',canChangeObjectIds:['CR-T'],remainingUnknownIds:['U-T'],institutionalState:'CURRENT'},
    {id:'WI-M',name:'Confirm budget ownership',ownerActorId:'ACT-2',status:'PLANNED',kind:'EVIDENCE_ROUTE',whatToObtain:'Buyer evidence for budget source and renewal trigger.',canChangeObjectIds:['CR-M'],remainingUnknownIds:['U-M'],institutionalState:'CURRENT'},
    {id:'WI-C',name:'Reconstruct conversion path',status:'BLOCKED',kind:'EVIDENCE_ROUTE',whatToObtain:'Stage history for the last ten qualified opportunities.',canChangeObjectIds:['CR-C'],remainingUnknownIds:['U-C'],institutionalState:'CURRENT'},
    {id:'WI-D',name:'Test defensibility with buyers',ownerActorId:'ACT-2',status:'PLANNED',kind:'EVIDENCE_ROUTE',whatToObtain:'Switching reasons and incumbent overlap from three buyers.',canChangeObjectIds:['CR-D'],remainingUnknownIds:['U-D'],institutionalState:'CURRENT'},
    {id:'WI-F',name:'Reconcile runway and terms',ownerActorId:'ACT-1',status:'ACTIVE',kind:'CURRENT_WORK',whatToObtain:'One plan tying terms, burn and milestones to the next raise.',canChangeObjectIds:['CR-F'],remainingUnknownIds:['U-F'],institutionalState:'CURRENT'}
  ],
  quantities:[{id:'QTY-1',label:'Raise size',value:5,display:'€5m',unit:'EURm',perimeter:{scope:'current round'},sourceObjectIds:['CL-2'],assumptionObjectIds:[],downstreamObjectIds:['CR-1'],editable:false,institutionalState:'CURRENT',freshnessStatus:'CURRENT'}],
  artifacts:[{id:'ART-1',type:'IC_MEMO',title:'IC Memo',freshnessStatus:'STALE',pendingCaseChangeCount:1,syncStatus:'STALE',blockIds:['AB-1'],quantityIds:[]}],
  artifactBlocks:[{id:'AB-1',artifactId:'ART-1',text:'Performance remains unproven.',authorship:'CASE_BACKED',boundObjectIds:['CR-1']}],artifactDiffs:[{id:'DIFF-1',artifactId:'ART-1',blockId:'AB-1',before:'Performance remains unproven.',after:'Deployment is confirmed; performance remains unproven.',causeEventId:'EV-1',changeType:'CASE_BACKED_RERENDER'}],
  relations:[{id:'REL-1',caseId:'CASE-1',sourceObjectId:'CL-2',sourceObjectType:'claim',targetObjectId:'CR-1',targetObjectType:'caseReading',type:'SUPPORTS',rationale:'The company material states the claimed performance level.',institutionalState:'CURRENT',contractVersion:'0.1.0'},
             {id:'REL-2',caseId:'CASE-1',sourceObjectId:'CR-1',sourceObjectType:'caseReading',targetObjectId:'Q-C',targetObjectType:'question',type:'DRIVES',rationale:'The ability to prove production performance shapes whether the commercial route can become repeatable.',institutionalState:'CURRENT',contractVersion:'0.1.0'}],
  events:[{id:'EV-1',caseId:'CASE-1',eventType:'CASE_READING_RECOMPUTED',objectType:'caseReading',objectId:'CR-1',effectiveAt:now,knownAt:now,recordedAt:now,actorOrPolicyId:'SYSTEM',schemaVersion:'0.1.0',idempotencyKey:'ev1'},
          {id:'EV-2',caseId:'CASE-1',eventType:'RELATION_ESTABLISHED',objectType:'claim',objectId:'CL-1',effectiveAt:customerAdmittedAt,knownAt:customerAdmittedAt,recordedAt:customerAdmittedAt,actorOrPolicyId:'SYSTEM',schemaVersion:'0.1.0',idempotencyKey:'ev2'},
          {id:'EV-0',caseId:'CASE-1',eventType:'CASE_CREATED',objectType:'case',objectId:'CASE-1',effectiveAt:'2026-01-09T09:00:00Z',knownAt:'2026-01-09T09:00:00Z',recordedAt:'2026-01-09T09:00:00Z',actorOrPolicyId:'ACT-1',schemaVersion:'0.1.0',idempotencyKey:'ev0'}],
  pendingReviews:[{id:'REV-1',kind:'FINDING',title:'Narrow the product performance view',findingId:finding.id,proposedCaseReading:{...reading1,id:'CR-PROPOSED',text:'Deployment is confirmed, while performance still requires independent verification.'},effectPreview:[{objectId:'CR-1',objectLabel:'Product performance reading',state:'NARROWS',before:reading0.text,after:reading1.text,reasonRelationIds:['REL-1']},{objectId:'Q-C',objectLabel:'Can customer acquisition become repeatable?',state:'BECOMES_STALE',before:'Open on the current performance basis',after:'Requires revalidation on the proposed basis',reasonRelationIds:['REL-2']},{objectId:'WS-1',objectLabel:'Product & Technical Proof',state:'HOLDS',before:'Open',after:'Open',reasonRelationIds:[]}],status:'NEW'}],simulationOptions:[{id:'SIM-1',originObjectId:'CR-1',label:'What if performance fails?',assumption:'Representative test fails',enabled:true}],
  conditions:[{id:'COND-1',label:'Performance verification',targetObjectIds:['DECCTX-1'],status:'OPEN',unknownIds:['U-1'],relatedObjectIds:['CR-1']}],
  decisionPaths:[{id:'PATH-1',label:'DEFER',meaning:'Wait for evidence.'},{id:'PATH-2',label:'COMMIT_WITH_CONDITIONS',meaning:'Proceed only if the verification condition is satisfied.'},{id:'PATH-3',label:'DECLINE',meaning:'Do not proceed on the current case.'}],decisions:[decision1,decision2],
  formation:{premise:'Can this team turn a technically differentiated product into an important, repeatable business at an attractive entry?',materialIds:['SRC-2','SRC-3','SRC-1','SRC-4','SRC-5','SRC-6'],proposedWorkstreamIds:['WS-T','WS-1','WS-M','WS-C','WS-D','WS-F'],blindSpotUnknownIds:['U-T','U-1','U-M','U-C','U-D','U-F'],unplacedSourceIds:[],status:'PROPOSED_NOT_LIVE'},
  formationMaterials:[
    {id:'FM-2',sourceId:'SRC-2',understoodObjectIds:['CL-2','CL-9'],limitationUnknownIds:['U-1','U-F'],mappedWorkstreamIds:['WS-1','WS-C','WS-F'],status:'PARTIAL'},
    {id:'FM-3',sourceId:'SRC-3',understoodObjectIds:['CL-3'],limitationUnknownIds:['U-T','U-C'],mappedWorkstreamIds:['WS-T','WS-C'],status:'PARTIAL'},
    {id:'FM-1',sourceId:'SRC-1',understoodObjectIds:['CL-1'],limitationUnknownIds:['U-1','U-M'],mappedWorkstreamIds:['WS-1','WS-M','WS-C'],status:'PARTIAL'},
    {id:'FM-4',sourceId:'SRC-4',understoodObjectIds:['CL-4','CL-6'],limitationUnknownIds:['U-T','U-C'],mappedWorkstreamIds:['WS-T','WS-C','WS-F'],status:'PARTIAL'},
    {id:'FM-5',sourceId:'SRC-5',understoodObjectIds:['CL-5','CL-7'],limitationUnknownIds:['U-M','U-D'],mappedWorkstreamIds:['WS-M','WS-D'],status:'PARTIAL'},
    {id:'FM-6',sourceId:'SRC-6',understoodObjectIds:['CL-8'],limitationUnknownIds:['U-F'],mappedWorkstreamIds:['WS-F'],status:'PARTIAL'}
  ]
};

function clone(x){return JSON.parse(JSON.stringify(x));}

export class SyntheticAdapter {
  constructor({actorId=actor.id}={}){
    this.actorId=actorId;
    this.current=clone(base);
    this.current.asOf=later;
    this.current.caseReadings=this.current.caseReadings.map(reading=>reading.id==='CR-1'?{...reading1,lastChangeEventId:currentReadingEvent.id}:reading);
    const changedWorkstream=this.current.workstreams.find(workstream=>workstream.id==='WS-1');
    if(changedWorkstream)changedWorkstream.latestChangeEventId=currentReadingEvent.id;
    this.current.events.push(clone(currentReadingEvent));
  }
  async getSession(){
    const ownerEntitlements=['READ_CASE','ADD_MATERIAL','REVIEW_CASE_CHANGE','ADMIT_CASE_READING','ADOPT_WORK_ITEM','ASSIGN_WORK_ITEM','ADOPT_FORMATION','RECORD_DECISION','EDIT_ARTIFACT','SYNC_ARTIFACT'];
    const contributorEntitlements=['READ_CASE','ADD_MATERIAL'];
    return {actor:{actorId:this.actorId,entitlements:this.actorId===actor.id?ownerEntitlements:contributorEntitlements},actors:[actor,contributor]};
  }
  async listCases(){return [{id:'CASE-1',name:'Synthetic Case'}];}
  async listCaseMoments(){return [{id:'M-0',asOf:'2026-01-09T09:00:00Z',label:'Case created',eventId:'EV-0'},{id:'M-1',asOf:customerAdmittedAt,label:'Customer reference admitted',eventId:'EV-2'},{id:'M-2',asOf:later,label:'Technical reading changed',eventId:'EV-3'},...this.current.events.filter(event=>event.eventType==='DECISION_RECORDED').map((event,index)=>({id:`M-D${index+1}`,asOf:event.knownAt,label:'IC decision recorded',eventId:event.id}))];}
  async loadCase(_caseId,opts){
    if(opts?.asOf && opts.asOf < later){
      const s=clone(base);s.asOf=opts.asOf;s.events=s.events.filter(event=>event.knownAt<=opts.asOf);s.decisions=s.decisions.filter(decision=>decision.recordedAt<=opts.asOf);
      if(opts.asOf<now){s.caseVersion='v0';s.questions=[];s.unknowns=[];s.sources=[];s.sourceVersions=[];s.claims=[];s.humanPositions=[];s.workItems=[];s.conditions=[];s.findings=[];s.pendingReviews=[];s.artifacts=[];s.artifactBlocks=[];s.artifactDiffs=[];delete s.formation;s.formationMaterials=[];s.caseReadings=s.caseReadings.map(reading=>({...reading,questionId:undefined,text:'No case reading had been formed at this point.',epistemicStatus:'UNEXAMINED',supportObjectIds:[],independentSupportObjectIds:[],unknownIds:[],relatedObjectIds:[]}));s.workstreams=s.workstreams.map(workstream=>({...workstream,questionIds:[],activeWorkItemIds:[],openUnknownIds:[]}));}
      return s;
    }
    const s=clone(this.current);s.asOf=opts?.asOf??later;return s;
  }
  async inspectObject(_caseId,objectId,opts){
    const excluded=new Set(opts?.excludeObjectIds??[]);
    const selectedActor=this.current.actors.find(item=>item.id===objectId);
    if(selectedActor){
      const ownedUnknowns=this.current.unknowns.filter(item=>item.ownerActorId===selectedActor.id&&item.status==='OPEN').map(item=>item.id);
      const ownedWorkstreams=this.current.workstreams.filter(item=>item.ownerActorId===selectedActor.id).map(item=>item.id);
      const ownedWorkItems=this.current.workItems.filter(item=>item.ownerActorId===selectedActor.id&&item.status!=='COMPLETED'&&item.status!=='CANCELLED').map(item=>item.id);
      return {objectId,supportObjectIds:[],independentSupportObjectIds:[],unknownIds:ownedUnknowns,dependentObjectIds:ownedWorkstreams,relatedObjectIds:ownedWorkItems,sourceLocators:[],allowedActions:[]};
    }
    const source=this.current.sources.find(item=>item.id===objectId);
    if(source){
      const sourceClaims=this.current.claims.filter(claim=>claim.sourceId===source.id).map(claim=>claim.id);
      const material=this.current.formationMaterials?.find(item=>item.sourceId===source.id);
      return {objectId,supportObjectIds:sourceClaims,independentSupportObjectIds:[],unknownIds:material?.limitationUnknownIds??[],dependentObjectIds:material?.mappedWorkstreamIds??[],relatedObjectIds:[],sourceLocators:[{sourceId:source.id,sourceVersionId:source.currentVersionId}],allowedActions:['OPEN_SOURCE','VIEW_IN_CASE']};
    }
    const unknown=this.current.unknowns.find(item=>item.id===objectId);
    if(unknown){
      return {objectId,supportObjectIds:[],independentSupportObjectIds:[],unknownIds:[],dependentObjectIds:unknown.targetObjectIds,relatedObjectIds:unknown.workItemIds??[],sourceLocators:[],allowedActions:['RESOLVE','VIEW_IN_CASE']};
    }
    const workItem=this.current.workItems.find(item=>item.id===objectId);
    if(workItem){
      return {objectId,supportObjectIds:[],independentSupportObjectIds:[],unknownIds:workItem.remainingUnknownIds,dependentObjectIds:workItem.canChangeObjectIds,relatedObjectIds:workItem.ownerActorId?[workItem.ownerActorId]:[],sourceLocators:[],allowedActions:['VIEW_IN_CASE']};
    }
    const reading=this.current.caseReadings.find(item=>item.id===objectId);
    const supports=(reading?.supportObjectIds??[]).filter(id=>!excluded.has(id));
    const independent=(reading?.independentSupportObjectIds??[]).filter(id=>supports.includes(id));
    const sourceLocators=supports.map(claimId=>{const claim=this.current.claims.find(item=>item.id===claimId);return {sourceId:claim?.sourceId??'',sourceVersionId:claim?.sourceVersionId,claimId};}).filter(locator=>locator.sourceId);
    return {objectId,supportObjectIds:supports,independentSupportObjectIds:independent,unknownIds:reading?.unknownIds??[],dependentObjectIds:reading?.relatedObjectIds??[],lastChangeEventId:reading?.lastChangeEventId??'EV-1',relatedObjectIds:['ART-1'],sourceLocators,allowedActions:['TRACE','SIMULATE','RESOLVE','OPEN_SOURCE','VIEW_IN_CASE']};
  }
  async searchCase(_caseId,q){return q? [{objectId:'CR-1',label:'Performance remains unproven',kind:'caseReading'}]:[];}
  async runSimulation(){return {id:'SR-1',request:{optionId:'SIM-1',originObjectId:'CR-1',assumption:'Representative test fails'},effects:[{objectId:'CR-1',objectLabel:'Technical reading',state:'WEAKENS',before:'Unproven',after:'Negative evidence',reasonRelationIds:[]},{objectId:'Q-C',objectLabel:'Can customer acquisition become repeatable?',state:'BECOMES_STALE',before:'Open on the current performance basis',after:'Requires revalidation under the scenario',reasonRelationIds:['REL-2']},{objectId:'WS-1',objectLabel:'Product & Technical Proof',state:'HOLDS',before:'Open',after:'Open',reasonRelationIds:[]}],coverage:{examinedCount:3,changedCount:2,heldCount:1,unmappedCount:0}};}
  async execute(_caseId,command){
    if(command.action.type==='RECORD_DECISION'){
      const id=`DEC-${this.current.decisions.length+1}`;
      let conditionIds;
      if(command.action.conditionText){const conditionId=`COND-${this.current.conditions.length+1}`;this.current.conditions.push({id:conditionId,label:command.action.conditionText,targetObjectIds:[this.current.decision.id],status:'OPEN',unknownIds:[],relatedObjectIds:this.current.questions.filter(question=>question.decisionDimensions).map(question=>question.id)});conditionIds=[conditionId];}
      const basisObjectIds=this.current.questions.filter(question=>question.decisionDimensions).map(question=>question.id);
      this.current.decisions.push({id,pathId:command.action.pathId,actorOrBodyId:command.actorId,rationale:command.action.rationale,conditionIds,effectiveAt:command.submittedAt,recordedAt:command.submittedAt,basisObjectIds,caseVersion:this.current.caseVersion});
      this.current.decision.status='RECORDED';this.current.decision.recordedDecisionId=id;
      this.current.events.push({id:`EV-${id}`,caseId:this.current.caseRef.id,eventType:'DECISION_RECORDED',objectType:'decision',objectId:id,effectiveAt:command.submittedAt,knownAt:command.submittedAt,recordedAt:command.submittedAt,actorOrPolicyId:command.actorId,schemaVersion:'0.1.0',idempotencyKey:`decision-${id}`});
      return clone(this.current);
    }
    if(command.action.type==='ADD_MATERIAL'){
      for(const [index,file] of command.action.files.entries()){
        const sourceId=`SRC-${this.current.sources.length+1}`;const sourceVersionId=`SV-${this.current.sourceVersions.length+1}`;
        this.current.sources.push({id:sourceId,type:'document',title:file.name||`Added material ${index+1}`,currentVersionId:sourceVersionId});
        this.current.sourceVersions.push({id:sourceVersionId,sourceId,contentHash:`added-${sourceId}`,knownAt:command.submittedAt,permissionScope:'case'});
        this.current.formation?.materialIds.push(sourceId);this.current.formation?.unplacedSourceIds.push(sourceId);
        this.current.formationMaterials?.push({id:`FM-${this.current.formationMaterials.length+1}`,sourceId,understoodObjectIds:[],limitationUnknownIds:[],mappedWorkstreamIds:[],status:'READ'});
      }
      return clone(this.current);
    }
    if(command.action.type==='REVIEW_ITEM'){
      const review=this.current.pendingReviews.find(item=>item.id===command.action.reviewId);
      if(review){review.status=command.action.disposition==='ADMIT'?'ADMITTED':command.action.disposition==='CORRECT'?'CORRECTED':'REJECTED';if(command.action.disposition!=='REJECT'){const reading=this.current.caseReadings.find(item=>item.id==='CR-1');if(reading)reading.text=command.action.correctedText||review.proposedCaseReading.text;}}
      return clone(this.current);
    }
    if(command.action.type==='ADOPT_FORMATION'){
      if(command.actorId!==actor.id)throw new Error('Only the Case Owner can adopt the initial case structure.');
      if(this.current.formation)this.current.formation.status='ADOPTED';
      return clone(this.current);
    }
    if(command.action.type==='CORRECT_FORMATION'){
      if(command.actorId!==actor.id)throw new Error('Only the Case Owner can edit the initial case structure.');
      const names=command.action.patch?.workstreamNames||{};for(const workstream of this.current.workstreams){if(names[workstream.id])workstream.name=names[workstream.id];}
      if(command.action.patch?.premise&&this.current.formation)this.current.formation.premise=command.action.patch.premise;
      return clone(this.current);
    }
    if(command.action.type==='ADOPT_WORK_ITEM'){
      const item=this.current.workItems.find(value=>value.id===command.action.workItemId);if(item){item.kind='EVIDENCE_ROUTE';item.status='PLANNED';item.institutionalState='CURRENT';}
      return clone(this.current);
    }
    if(command.action.type==='UPDATE_WORK_ITEM_PROPOSAL'){
      const item=this.current.workItems.find(value=>value.id===command.action.workItemId);if(item)item.whatToObtain=command.action.whatToObtain;
      return clone(this.current);
    }
    if(command.action.type==='DISMISS_WORK_ITEM_PROPOSAL'){
      const item=this.current.workItems.find(value=>value.id===command.action.workItemId);if(item){item.status='CANCELLED';item.institutionalState='REJECTED';}
      return clone(this.current);
    }
    if(command.action.type==='ASSIGN_WORK_ITEM'){
      const item=this.current.workItems.find(value=>value.id===command.action.workItemId);if(item)item.ownerActorId=command.action.ownerActorId;
      return clone(this.current);
    }
    if(command.action.type==='CREATE_ARTIFACT'){
      const id=`ART-${this.current.artifacts.length+1}`;this.current.artifacts.push({id,type:command.action.artifactType,title:command.action.artifactType.replaceAll('_',' '),freshnessStatus:'CURRENT',pendingCaseChangeCount:0,syncStatus:'CURRENT',blockIds:[],quantityIds:[]});
      return clone(this.current);
    }
    if(command.action.type==='SYNC_ARTIFACT'){
      const a=this.current.artifacts.find(x=>x.id===command.action.artifactId);if(a){a.pendingCaseChangeCount=0;a.syncStatus='CURRENT';a.freshnessStatus='CURRENT';a.lastSyncedCaseVersion=this.current.caseVersion;a.lastSyncedAt=command.submittedAt;}
      return clone(this.current);
    }
    if(command.action.type==='SYNC_ALL_ARTIFACTS'){
      for(const artifact of this.current.artifacts){artifact.pendingCaseChangeCount=0;artifact.syncStatus='CURRENT';artifact.freshnessStatus='CURRENT';artifact.lastSyncedCaseVersion=this.current.caseVersion;artifact.lastSyncedAt=command.submittedAt;}
      return clone(this.current);
    }
    if(command.action.type==='UPDATE_ARTIFACT_BLOCK'){
      const block=this.current.artifactBlocks.find(value=>value.id===command.action.blockId);if(block){block.text=command.action.text;block.authorship='HUMAN_AUTHORED';block.authorActorId=command.actorId;block.recordedAt=command.submittedAt;}
      return clone(this.current);
    }
    if(command.action.type==='ACCEPT_ARTIFACT_SUGGESTION'||command.action.type==='DISMISS_ARTIFACT_SUGGESTION'){
      const block=this.current.artifactBlocks.find(value=>value.id===command.action.blockId);if(block){if(command.action.type==='ACCEPT_ARTIFACT_SUGGESTION'&&block.suggestion)block.text=block.suggestion.suggestedText;delete block.suggestion;}
      return clone(this.current);
    }
    return clone(this.current);
  }
}
