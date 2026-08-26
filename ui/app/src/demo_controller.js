(function(){
  'use strict';
  const R=window.PantaRuntime;
  const caption=document.getElementById('demo-caption');
  const cursor=document.getElementById('demo-cursor');
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  let stopped=false;
  let speed=1;
  function say(text,ms=1600){caption.textContent=text||'';caption.classList.toggle('show',Boolean(text));return sleep(Math.max(20,ms*speed))}
  function move(x,y){cursor.style.transform=`translate(${x}px,${y}px)`;cursor.classList.add('show')}
  function clickPulse(){cursor.classList.add('click');setTimeout(()=>cursor.classList.remove('click'),260)}
  async function step(label,fn,wait=1400,point){if(stopped)return;await say(label,500);if(point){move(point[0],point[1]);clickPulse()}await fn();await sleep(Math.max(20,wait*speed))}
  async function run(options={}){
    if(R.getState().demoRunning)return;
    stopped=false;speed=options.fast?0.08:1;R.reset();await R.ready;R.setDemoRunning(true);R.setReducedMotion(Boolean(options.fast));await sleep(Math.max(20,500*speed));
    try{
      await step('Fund Command: one field of material situations',async()=>R.openFund(),1800,[115,112]);
      await step('Morning Delta identifies the change that matters first',async()=>R.setSituation('SIT-KEYSTONE'),1700,[490,290]);
      await step('Zoom into the same state — no new app, no lost context',async()=>R.openDeal(),1800,[720,312]);
      await step('Question spine: what we believe, why, and what remains open',async()=>R.setQuestion('UQ-REVENUE',false),1800,[525,400]);
      await step('Object Aperture: basis, dependents, action and history',async()=>R.openDrawer('question','UQ-REVENUE','basis'),1900,[1060,410]);
      await step('The deal rests on explicit minimal support sets',async()=>{R.closeDrawer();R.navigate('foundations')},1700,[180,360]);
      await step('Unknowns are ranked by decision value, not file order',async()=>R.navigate('unknowns'),1600,[182,405]);
      await step('A new source arrives: seven accounts resolve to one parent',async()=>R.openScene('concentration'),1700,[182,315]);
      await step('Professional review keeps the exact source and applicability visible',async()=>R.reviewSource(),1700,[1040,650]);
      await step('The system proposes a treatment; the professional admits it',async()=>R.prepareTreatment(),1500,[1050,650]);
      await step('One admitted fact now enters the deterministic transition runtime',async()=>R.confirmTreatment(),800,[1050,650]);
      await sleep(Math.max(60,4200*speed));R.skipTransition();await say('Every consequence receives an explicit disposition: recompute, survive or human',1700);
      await step('Action Frontier turns impact into coordinated work',async()=>R.continueFromImpact(),1500,[1048,650]);
      await step('Model, memo, offer and tracker are prepared from the same state change',async()=>{const t=R.getState().transitionResult;for(const c of t.artifact_change_sets)R.toggleChangeSet(c.artifact_id)},1400,[780,520]);
      await step('A material offer exception routes into a formal Decision Room',async()=>R.prepareResponse(),1700,[1040,650]);
      await step('Authority sees evidence, alternatives, conditions and economics together',async()=>R.selectCourse('COURSE-B'),1700,[730,500]);
      await step('Attestation is an institutional state change, not a chat response',async()=>R.attestDecision(),1500,[1040,650]);
      await step('Execution Room is the controlled externality boundary',async()=>R.executeExternal(),1800,[1040,650]);
      await step('The same Deal World returns settled, with history preserved',async()=>R.navigate('registry'),1500,[180,500]);
      await step('Causal Replay reconstructs what was known, believed, approved and open',async()=>{R.navigate('replay');R.setReplay('final-ic')},2200,[180,545]);
      await say('PANTA V17 · one state, one transition, one accountable decision history',2400);
    }finally{
      caption.classList.remove('show');cursor.classList.remove('show');R.setDemoRunning(false);
      window.PANTA_DEMO_COMPLETE=true;
    }
  }
  function stop(){stopped=true;caption.classList.remove('show');cursor.classList.remove('show');R.setDemoRunning(false)}
  window.PantaDemo={run,stop};
  window.addEventListener('load',()=>{const p=new URLSearchParams(location.search);if(p.get('autodemo')==='1')setTimeout(()=>run({fast:p.get('fast')==='1'}),900)});
})();
