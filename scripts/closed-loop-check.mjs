// STATIC wiring gate only. Runtime behavior is separately tested by behavior-test.mjs.
import fs from 'node:fs';
const read=p=>fs.readFileSync(p,'utf8');
const domain=read('src/types/domain.ts');
const adapter=read('src/providers/PantaBackendAdapter.ts');
const ctx=read('src/app/PantaContext.tsx');
const outputs=read('src/screens/Outputs.tsx');
const replay=read('src/screens/ReplayDecision.tsx');
const sim=read('src/screens/Simulate.tsx');
const review=read('src/screens/ReviewAdmit.tsx');
const trace=read('src/screens/Trace.tsx');
const resolve=read('src/screens/Resolve.tsx');
const formation=read('src/screens/Formation.tsx');
const deal=read('src/screens/DealHome.tsx');
const workstream=read('src/screens/WorkstreamFocus.tsx');
const failures=[];
const req=(name,text,needle)=>{if(!text.includes(needle))failures.push(`${name}: missing ${needle}`)};

req('adapter',adapter,'loadCase(caseId?: Id, options?: LoadCaseOptions)');
req('adapter',adapter,'listCaseMoments(caseId: Id)');
req('domain',domain,'export interface CaseEvent');
req('context',ctx,'asOf');
req('replay',replay,'setAsOf');
req('replay',replay,'returnToCurrent');

req('domain',domain,'export interface ActorContext');
req('domain',domain,'export type Entitlement');
req('domain',domain,'actorId: Id');
req('context',ctx,'actorId: session.actor.actorId');

req('deal',deal,'HumanPositionNote');
req('workstream',workstream,'HumanPositionNote');
req('trace',trace,'HumanPositionNote');

req('trace',trace,'Test without this');
req('trace',trace,'openSource');
req('outputs',outputs,'ObjectLens');
req('outputs',outputs,"type:'SYNC_ARTIFACT'");
req('outputs',outputs,"type:'SYNC_ALL_ARTIFACTS'");

req('review',review,"type:'REVIEW_ITEM'");
req('resolve',resolve,"type:'ADOPT_WORK_ITEM'");
req('formation',formation,"type:'ADOPT_FORMATION'");
req('replay',replay,"type:'RECORD_DECISION'");
req('sim',sim,'runSimulation');
req('deal',deal,'no independent evidence');

if(failures.length){console.error('Closed-loop static gate FAILED:\n'+failures.join('\n'));process.exit(1)}
console.log('Closed-loop static gate PASS');
