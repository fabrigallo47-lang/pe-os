import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

const source = fs.readFileSync('src/providers/simulations.ts', 'utf8').replace("import { withSourceDocuments } from './sourceDocuments';", 'const withSourceDocuments = adapter => adapter;');
const code = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {createSimulationsAdapter} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const snapshot = {caseRef:{id:'CASE',name:'Simulation test'},caseVersion:'V1',modelNodes:[{id:'A'}],simulationScope:{schemaVersion:'simulation/1.0',version:'M1',caseId:'CASE',caseVersion:'V1',limits:[]},simulationOptions:[]};
const calls = [];
let failure, wrongCase, wrongValue, wrongCoverage;
const adapter = createSimulationsAdapter('CASE', async () => ({actorId:'ACTOR',sessionId:'SESSION'}), {fetchImpl:async (url, init) => {
  calls.push({url,init});
  if (failure) return new Response(JSON.stringify({detail:'The model changed. Refresh.'}),{status:409});
  if (init.method === 'POST') {
    const request = JSON.parse(init.body);
    return new Response(JSON.stringify({id:'RESULT',schemaVersion:'simulation/1.0',caseId:wrongCase?'OTHER':'CASE',caseVersion:'V1',scopeVersion:'M1',liveCaseUnchanged:true,
      request:{...request,value:wrongValue?'90.0000000000000001':'9E+1'},effects:[{objectId:'A',state:'CHANGES'}],limits:[],coverage:{examinedCount:wrongCoverage?99:1,changedCount:1,heldCount:0,unmappedCount:0}}));
  }
  return new Response(JSON.stringify({snapshot,actor:{actorId:'ACTOR',entitlements:['READ_CASE']}}));
}});
await adapter.getSession(); await adapter.loadCase('CASE');
const request = {optionId:'A',originObjectId:'A',value:'90.0',assumption:'Hypothetical',caseVersion:'V1',scopeVersion:'M1'};
const result = await adapter.runSimulation('CASE',request);
assert.equal(result.caseId,'CASE');
const sent=calls.at(-1);assert.equal(sent.url,'/api/v20/cases/CASE/simulations');assert.deepEqual(JSON.parse(sent.init.body),request);
assert.equal(sent.init.headers['X-Panta-Actor'],'ACTOR');assert.equal(sent.init.headers['X-Panta-Session'],'SESSION');assert.equal(sent.init.credentials,'same-origin');
await assert.rejects(()=>adapter.runSimulation('OTHER',request),/Load the case/);
await assert.rejects(()=>adapter.runSimulation('CASE',{...request,scopeVersion:'OLD'}),/stale/);
await assert.rejects(()=>adapter.loadCase('CASE',{asOf:'past'}),/current case/);
await assert.rejects(()=>adapter.execute('CASE',{}),/does not change/);
wrongCase=true;await assert.rejects(()=>adapter.runSimulation('CASE',request),/does not match/);wrongCase=false;
wrongValue=true;await assert.rejects(()=>adapter.runSimulation('CASE',request),/does not match/);wrongValue=false;
wrongCoverage=true;await assert.rejects(()=>adapter.runSimulation('CASE',request),/inconsistent coverage/);wrongCoverage=false;
failure=true;await assert.rejects(()=>adapter.runSimulation('CASE',request),/model changed/);
console.log('Simulation adapter PASS — authenticated transport, exact decimal input, case/model versions, coverage, no mutation');
