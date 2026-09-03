import fs from 'node:fs';

const domain = fs.readFileSync('src/types/domain.ts','utf8');
const adapter = fs.readFileSync('src/providers/PantaBackendAdapter.ts','utf8');
const selectors = fs.readFileSync('src/app/selectors.ts','utf8');
const screens = ['DealHome','WorkstreamFocus','Trace','Simulate','ReviewAdmit','Resolve','Formation','ReplayDecision','Outputs'].map(x=>fs.readFileSync(`src/screens/${x}.tsx`,'utf8')).join('\n');
const failures=[];
function requireText(name,text,needle){if(!text.includes(needle))failures.push(`${name}: missing ${needle}`)}
function forbid(name,text,rx){if(rx.test(text))failures.push(`${name}: forbidden ${rx}`)}

// Ledger/replay projection contract.
requireText('domain',domain,'export interface CaseEvent');
for (const f of ['effectiveAt?: string','knownAt: string','recordedAt: string']) requireText('domain',domain,f);
requireText('adapter',adapter,'loadCase(caseId?: Id, options?: LoadCaseOptions)');
requireText('adapter',adapter,'inspectObject(caseId: Id, objectId: Id, options?: InspectOptions)');

// Actor + authority.
requireText('domain',domain,'authorActorId: Id');
requireText('domain',domain,'requiredEntitlement: Entitlement');
requireText('domain',domain,'export interface PantaCommand');
requireText('domain',domain,'actorId: Id');

// No orphan lifecycle strings on workstreams.
requireText('domain',domain,'latestChangeEventId?: Id');
requireText('domain',domain,'activeWorkItemIds: Id[]');
requireText('domain',domain,'openUnknownIds: Id[]');
forbid('domain',domain,/latestChange\?\s*:\s*string/);
forbid('domain',domain,/activeWork\?\s*:\s*string/);
forbid('domain',domain,/stillOpen\?\s*:\s*string/);
forbid('domain',domain,/owner\?\s*:\s*string/);

// Object Lens backend returns graph facts, never explanatory prose.
for (const bad of [/whyWeBelieveThis\??\s*:/,/stillMissing\??\s*:/,/whyItMatters\??\s*:/,/whatChanged\??\s*:/]) forbid('InspectionPayload',domain,bad);
requireText('InspectionPayload',domain,'supportObjectIds: Id[]');
requireText('InspectionPayload',domain,'independentSupportObjectIds: Id[]');
requireText('InspectionPayload',domain,'dependentObjectIds: Id[]');
requireText('selectors',selectors,'composeLens');


// Independence is reading/support-route relative, never a global Claim property.
forbid('Claim',domain,/\bindependent\s*:\s*boolean/);
requireText('CaseReading',domain,'independentSupportObjectIds: Id[]');

// Relation projection keeps canonical endpoint types explicit.
requireText('Relation',domain,'sourceObjectType: KernelObjectKind');
requireText('Relation',domain,'targetObjectType: KernelObjectKind');

// Connected auditability can address canonical assumptions/risks/models/outcomes.
for (const t of ['MetricDefinition','MetricObservation','Assumption','Risk','ModelNode','Outcome']) requireText('domain',domain,`export interface ${t}`);
for (const c of ['metricDefinitions: MetricDefinition[]','metricObservations: MetricObservation[]','assumptions: Assumption[]','risks: Risk[]','modelNodes: ModelNode[]','outcomes: Outcome[]']) requireText('snapshot',domain,c);

// Recorded Decision conditions are refs; free text exists only as command input before canonicalization.
requireText('DecisionRecord',domain,'conditionIds?: Id[]');
forbid('DecisionRecord',domain,/export interface DecisionRecord[\s\S]*?conditions\?\s*:\s*string/);

// Numeric simulation trust boundary.
requireText('domain',domain,'export interface Coverage');
for (const n of ['examinedCount: number','changedCount: number','heldCount: number','unmappedCount: number']) requireText('coverage',domain,n);
forbid('Simulation',domain,/coverageLabel\??\s*:/);
forbid('Simulation',domain,/coverageLimit\??\s*:/);

// Product surface gates.
requireText('DealHome',screens,'no independent evidence');
requireText('Positions',screens,'HumanPositionNote');
requireText('Replay',screens,'setAsOf');
requireText('Trace',screens,'Test without this');
requireText('Outputs',screens,'Open source');

if(failures.length){console.error('Contract check FAILED:\n'+failures.join('\n'));process.exit(1)}
console.log('Contract check PASS');
