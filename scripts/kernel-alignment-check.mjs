// Static semantic-alignment gate against the target design contracts:
// panta.universal_investment_kernel@0.1.0 + panta.relation_and_update_contract@0.1.0.
// It proves vocabulary/axes are aligned. It does NOT prove runtime behaviour.
import fs from 'node:fs';
const domain = fs.readFileSync('src/types/domain.ts','utf8');
const src = ['app/selectors.ts','app/PantaContext.tsx','screens/DealHome.tsx','screens/WorkstreamFocus.tsx','screens/Trace.tsx',
  'screens/Simulate.tsx','screens/ReviewAdmit.tsx','screens/Resolve.tsx','screens/Formation.tsx','screens/ReplayDecision.tsx','screens/Outputs.tsx']
  .map(f=>fs.readFileSync(`src/${f}`,'utf8')).join('\n');
const failures=[];
const req=(name,text,needle)=>{ if(!text.includes(needle)) failures.push(`${name}: missing ${needle}`); };
const forbid=(name,text,rx,why)=>{ const m=text.match(rx); if(m) failures.push(`${name}: forbidden ${m[0]} — ${why}`); };

// Canonical kernel types used by the frontend projection.
for (const t of ['Actor','Question','CaseReading','Claim','HumanPosition','Unknown','WorkItem','Source','SourceVersion','Condition','Decision']) {
  req('kernel-object', domain, `export interface ${t}`);
}
// Workstream/Finding/Quantity are explicitly projections, not ontology inventions.
req('projection',domain,"export type ProjectionKind");
req('projection',domain,"'workstream'");
req('projection',domain,"'finding'");
req('projection',domain,"'quantity'");

// Separate state axes from latest kernel handoff.
for (const axis of ['InstitutionalState','EpistemicStatus','FreshnessStatus','QuestionStatus','WorkStatus','ConditionStatus','DecisionLinkStatus']) req('state-axis',domain,`export type ${axis}`);
for (const s of ['UNEXAMINED','INSUFFICIENT','SUPPORTED','CONTESTED','INVALIDATED','STALE']) req('epistemic', domain, `'${s}'`);
forbid('epistemic', domain, /'OPEN'\s*\/\/.*epistemic|export type EpistemicStatus[^;]*'OPEN'/s, 'OPEN is a Question/Condition status, not the target epistemic status');
forbid('epistemic', domain, /\bAssessmentState\b/, 'legacy eleven-state vocabulary');

// HumanPosition is attributed and never epistemically graded.
const hp = domain.match(/export interface HumanPosition \{[\s\S]*?\n\}/)?.[0] ?? '';
req('human-position', hp, 'authorActorId: Id');
req('human-position', hp, 'institutionalState: InstitutionalState');
forbid('human-position', hp, /epistemicStatus\s*:/, 'HumanPosition must not carry system epistemic status');

// Exact 13-relation canonical vocabulary from relation contract.
const relations=['ABOUT','BEARS_ON','SUPPORTS','CHALLENGES','CONTRADICTS','CORROBORATES','DERIVES_FROM','DRIVES','CONDITIONS','RESOLVES','ADOPTS','SUPERSEDES','PRODUCES'];
for (const r of relations) req('relation', domain, `'${r}'`);
for (const bad of ['LIMITS','INFORMS','DERIVED_FROM','ANSWERS','FROM_SOURCE','ATTRIBUTED_TO','LOCATED_IN','ASSIGNED_TO','ABOUT_ENTITY']) forbid('relation', domain, new RegExp(`'${bad}'`), 'not in the target 13-relation contract');

// Actor, not Person, is the canonical authority identity.
forbid('actor',domain,/export interface Person\b/,'kernel identity object is Actor');
forbid('actor',src,/\bpersonId\b|\bownerPersonId\b|\bauthorPersonId\b|\bactorPersonId\b/,'use Actor ids');

// Exact event vocabulary must be represented and bitemporal fields must be separate.
for (const ev of ['CASE_CREATED','SOURCE_REGISTERED','SOURCE_VERSION_RECORDED','CLAIM_RECORDED','METRIC_OBSERVATION_RECORDED','QUESTION_PROPOSED','QUESTION_SPINE_CHANGED','UNKNOWN_RECORDED','HUMAN_POSITION_RECORDED','CASE_READING_RECOMPUTED','ASSUMPTION_PROPOSED','ASSUMPTION_ADOPTED','ASSUMPTION_CHALLENGED','RISK_RECORDED','MODEL_NODE_BOUND','RELATION_ESTABLISHED','CONDITION_RECORDED','CONDITION_STATE_RECORDED','DECISION_RECORDED','WORK_ITEM_RECORDED','WORK_ITEM_STATE_RECORDED','ARTIFACT_VERSION_RECORDED','OUTCOME_RECORDED','PROPOSAL_REJECTED','OBJECT_SUPERSEDED','OBJECT_RETIRED']) req('event',domain,`'${ev}'`);
for (const f of ['effectiveAt?: string','knownAt: string','recordedAt: string','actorOrPolicyId: Id','idempotencyKey: string']) req('event-envelope', domain, f);

// Projection source-of-truth wording must be explicit.
req('authority',domain,'This file is a UI projection');
req('authority',domain,'never the ontology/source of truth');

if (failures.length) { console.error('Kernel alignment FAILED:\n' + failures.join('\n')); process.exit(1); }
console.log('Kernel alignment PASS');
