(function(){
  'use strict';
  const V16 = window.PANTA_CASE;
  const q = id => V16.question_spine.find(item => item.id === id);
  const scene = id => V16.scenes[id];

  const transitionFromScene = (id, overrides={}) => {
    const s = scene(id);
    return {
      schema_version: 'frontend-transition-projection/1.0',
      run_id: `RUN-${id.toUpperCase()}-V17`,
      case_id: 'PROJECT-KEYSTONE',
      prior_state_id: s.start_version,
      candidate_state_id: `candidate-${id}-v17`,
      source_event_id: `EVENT-${id.toUpperCase()}-V17`,
      status: 'PARTIAL_SETTLEMENT',
      affected_set: s.propagation.map((step,index)=>({
        order:index+1,
        object_id:step.trace_id,
        label:step.label,
        disposition:step.behavior === 'recompute' ? 'RECOMPUTES' : step.behavior === 'survives' ? 'SURVIVES' : step.behavior === 'human' ? 'HUMAN' : 'RULE_SWITCH',
        before:step.before,
        after:step.after,
        explanation:step.detail,
        source_trace:step.source_trace || null
      })),
      recomputed_values:s.propagation.filter(x=>x.behavior==='recompute').map(x=>({object_id:x.trace_id,label:x.label,before:x.before,after:x.after})),
      unchanged_objects:s.propagation.filter(x=>x.behavior==='survives').map(x=>({object_id:x.trace_id,label:x.label,reason:'Independent definition or support route remains valid.'})),
      human_stops:s.propagation.filter(x=>x.behavior==='human').map(x=>({
        stop_id:`HS-${x.id}`,
        subject_ref:x.trace_id,
        authority_verb:id==='concentration'?'approve_offer':'adopt_treatment',
        required_role:id==='concentration'?'Deal Partner':'Financial reviewer',
        reason:x.detail,
        status:'OPEN'
      })),
      policy_result:{materiality:'MATERIAL',authority_required:id==='concentration',policy_version:'keystone-policy-demo-v1'},
      artifact_change_sets:s.artifacts.map(a=>({
        artifact_id:a.id,
        title:a.title,
        version_before:a.version_before,
        version_after:a.version_after,
        changes:a.changes || [],
        passage_before:a.passage_before || null,
        passage_after:a.passage_after || null,
        status:'PREPARED'
      })),
      replay_hash:`sha256:demo-${id}-v17`,
      coverage_limits:id==='concentration' ? [{limit_id:'CL-CONTRACT-READ',label:'Seven customer contracts remain unread',effect:'Customer durability remains contested.'}] : [],
      ...overrides
    };
  };

  window.PANTA_V17_FIXTURE = {
    package_version:'17.0.0',
    mode:'INTEGRATION_DEMO',
    disclosure:'All company, person, policy and event data in the demo is synthetic. Backend reference files are included separately and are not silently treated as correct frontend state.',
    fund:{
      id:'FUND-HARBOR',
      name:'Harbor Private Capital',
      date:'26 Aug 2026',
      situations:[
        {
          id:'SIT-KEYSTONE', case_id:'PROJECT-KEYSTONE', company:'Alderstone', project:'Project Keystone', lifecycle:'Active pursuit',
          action_class:'authority_decision', title:'Offer basis must be renewed',
          why_now:'Customer parent exposure moved financing capacity and the current offer is no longer supported.',
          objective:'Determine whether the $108m offer remains defensible.',
          required_action:'Review the material exception and choose the offer treatment.', authority_verb:'approve_offer',
          owner:'A. Rossi', deadline:'Today · 14:00', capital:'$108.0m', evidence:'Derived + attested', status:'open',
          priority_reasons:['$108m capital at stake','Authority deadline today','Current offer is stale'],
          missions:[{label:'Recompute financing case',state:'complete',progress:100},{label:'Read seven contracts',state:'running',progress:42}],
          position:{x:59,y:42,size:88,halo:'contested'}
        },
        {
          id:'SIT-NORTHSTAR', case_id:'PROJECT-NORTHSTAR', company:'Northstar Systems', project:'Project Northstar', lifecycle:'Active pursuit',
          action_class:'professional_review', title:'ARR bridge needs reviewer sign-off',
          why_now:'The latest cohort file changes normalized retention but not the base valuation.',
          objective:'Sign the ARR and retention treatment.', required_action:'Review prepared treatment.', authority_verb:'advise',
          owner:'L. Chen', deadline:'Tomorrow', capital:'$36.0m', evidence:'Observed', status:'open',
          priority_reasons:['Evidence newly observed','Model branch waiting'], missions:[{label:'Cohort reconstruction',state:'waiting',progress:82}],
          position:{x:27,y:58,size:58,halo:'review'}
        },
        {
          id:'SIT-MERIDIAN', case_id:'PROJECT-MERIDIAN', company:'Meridian Health', project:'Project Meridian', lifecycle:'Owned investment',
          action_class:'notification', title:'Runway is below the approved intervention line',
          why_now:'Hiring remained ahead of plan while collections slipped by 19 days.',
          objective:'Prepare the next board intervention.', required_action:'Inspect variance diagnosis.', authority_verb:'recommend',
          owner:'J. Morgan', deadline:'Friday', capital:'$18.4m', evidence:'Observed', status:'active',
          priority_reasons:['Liquidity threshold crossed','Board in 4 days'], missions:[{label:'Variance diagnosis',state:'complete',progress:100}],
          position:{x:76,y:69,size:52,halo:'blocked'}
        },
        {
          id:'SIT-SCOUT', case_id:'PROJECT-SCOUT', company:'Scout Search', project:'Scout pilot', lifecycle:'Active pursuit',
          action_class:'professional_review', title:'Next-best work is customer references',
          why_now:'Commercial uncertainty dominates the remaining decision variance.',
          objective:'Close the highest-value unknown.', required_action:'Approve the reference-call plan.', authority_verb:'advise',
          owner:'Search lead', deadline:'This week', capital:'$6.5m', evidence:'Inferred', status:'open',
          priority_reasons:['Highest value of information','Low closure cost'], missions:[{label:'Reference list preparation',state:'running',progress:64}],
          position:{x:42,y:78,size:40,halo:'unknown'}
        }
      ],
      morning_delta:[
        {id:'DELTA-1',kind:'material',label:'Keystone offer basis became stale',detail:'18.2% parent exposure activated a financing exception.',case_id:'PROJECT-KEYSTONE'},
        {id:'DELTA-2',kind:'review',label:'Northstar cohort treatment is ready',detail:'Reviewer sign-off is the only remaining blocker.',case_id:'PROJECT-NORTHSTAR'},
        {id:'DELTA-3',kind:'monitor',label:'Meridian runway crossed the intervention line',detail:'Board action now ranks above routine monitoring.',case_id:'PROJECT-MERIDIAN'},
        {id:'DELTA-4',kind:'work',label:'Scout next-best work changed',detail:'Customer references now dominate decision value.',case_id:'PROJECT-SCOUT'}
      ]
    },
    deal:{
      case_id:'PROJECT-KEYSTONE',
      objective:{verb:'defend',target:'the $108m offer',statement:'Determine whether the $108m offer remains defensible on verified earnings and customer risk.',deadline:'10 Mar 2026 · 09:00',status:'active'},
      branches:{approved:'Final IC · 10 Mar 2026',current:'Concentration review · 5 Feb 2026',working:'Working Branch 17'},
      morning_delta:{label:'Customer concentration basis changed',from:'7.6% account view',to:'18.2% ultimate-parent view',source:'VDR customer master'},
      next_best_work:{id:'NBW-CONTRACTS',label:'Read the seven Riverton contracts',reason:'Highest decision value ÷ closure cost',owner:'A. Rossi',duration:'4h',unlocks:'Customer durability treatment and offer authority'},
      command_suggestions:['What changed since the last review?','What does the deal rest on?','Show every unresolved risk accepted by IC','Which artifact is stale?','What should we do next?'],
      rooms:{
        foundations:{
          title:'What the deal rests on',subtitle:'Minimal support sets for the current investment case.',
          sets:[
            {id:'FND-EARNINGS',label:'Underwritten earnings',strength:'contested',economic:'$5.4m ceiling sensitivity',members:['QoE EBITDA $11.9m','Firm reserve to $11.4m','$0.5m initiatives rejected'],question_id:'UQ-EARNINGS'},
            {id:'FND-REVENUE',label:'Revenue durability',strength:'weak',economic:'18.2% parent exposure',members:['Seven accounts aggregate to Riverton','No minimum-volume guarantee','Multi-site tenure supports partial durability'],question_id:'UQ-REVENUE'},
            {id:'FND-CASH',label:'Cash conversion',strength:'contested',economic:'$0.7m closing delta',members:['QoE NWC target $8.4m','Seller target $7.7m','Billing controls remain fragmented'],question_id:'UQ-CASH'},
            {id:'FND-INTEGRATION',label:'Integration execution',strength:'accepted-risk',economic:'$2.0m funded plan',members:['Commercial integration exists','Systems remain fragmented','IC accepted risk under conditions'],question_id:'UQ-INTEGRATION'}
          ]
        },
        unknowns:{
          title:'Everything we still do not know',subtitle:'Ordered by expected decision value, not document order.',
          items:[
            {id:'UNK-CONTRACTS',rank:1,label:'Can Riverton reduce volume without penalty?',value:'Very high',closure:'Read 7 contracts · 4h',owner:'A. Rossi',question_id:'UQ-REVENUE'},
            {id:'UNK-RETENTION',rank:2,label:'Would a 20% Riverton reduction be operationally absorbable?',value:'High',closure:'2 reference calls · 1 day',owner:'Commercial',question_id:'UQ-REVENUE'},
            {id:'UNK-INTEGRATION',rank:3,label:'Can Project Unify cut over without billing disruption?',value:'High',closure:'Operator review · 6h',owner:'J. Morgan',question_id:'UQ-INTEGRATION'},
            {id:'UNK-WIP',rank:4,label:'How much aged WIP is collectible?',value:'Medium',closure:'Invoice sample · 3h',owner:'L. Chen',question_id:'UQ-CASH'},
            {id:'UNK-LENDER',rank:5,label:'Will the lender accept the concentration-adjusted case?',value:'Medium',closure:'Lender call · 30m',owner:'R. Diaz',question_id:'UQ-FINANCING'}
          ]
        },
        shadowIC:{
          title:'Shadow IC',subtitle:'The strongest case for and against the investment, continuously maintained.',
          theses:[
            {id:'SIC-FOR',side:'FOR',label:'Durable compliance demand and multi-site relationships',strength:'strong',basis:['72% recurring/repeat activity','600+ billing accounts','Riverton spans years, facilities and service lines']},
            {id:'SIC-AGAINST',side:'AGAINST',label:'Concentration and integration risks are under-compensated',strength:'strong',basis:['18.2% ultimate-parent exposure','No minimum-volume guarantees','Systems fragmented across four acquisitions']},
            {id:'SIC-RETURNS',side:'FOR',label:'Base returns remain acceptable with disciplined entry and deleveraging',strength:'contested',basis:['2.00x MOIC','14.8% IRR','9.0x exit multiple']},
            {id:'SIC-DISSENT',side:'AGAINST',label:'9.5x entry multiple does not compensate unresolved risk',strength:'recorded-dissent',basis:['IC vote 4-1','Thirteen approval conditions','Risk accepted but unresolved']}
          ],
          verdict:'Proceed only under the stated conditions; customer concentration and integration remain contested-but-accepted.'
        }
      },
      scenarioLab:{
        selected:'base',
        scenarios:[
          {id:'base',label:'Standalone Base',state:'CURRENT',color:'cyan',drivers:['Revenue growth 7%','EBITDA margin 16%','DSO 64 days','Exit 9.0x'],moic:'2.00x',irr:'14.8%',debt:'$42.8m',markers:['IC basis','No acquisitions']},
          {id:'downside',label:'Standalone Downside',state:'SCENARIO',color:'violet',drivers:['Lower growth','Margin compression','Slower cash conversion','Exit 7.5x'],moic:'1.28x',irr:'5.1%',debt:'$42.8m',markers:['Covenant pressure','No promotion']},
          {id:'upside',label:'Standalone Upside',state:'SCENARIO',color:'violet',drivers:['Stronger utilization','Faster collections','Exit 10.0x'],moic:'2.43x',irr:'19.5%',debt:'$42.8m',markers:['Operating upside']},
          {id:'acquisition',label:'Acquisition Base',state:'SCENARIO',color:'violet',drivers:['Sentinel + second add-on','Integration spend','Exit 9.5x'],moic:'2.08x',irr:'16.0%',debt:'$42.8m',markers:['Funding required','Integration condition']}
        ]
      },
      decisionRoom:{
        request_id:'AR-OFFER-001',verb:'approve_offer',title:'Set the maximum offer treatment after the concentration exception',deadline:'Today · 14:00',holder:'M. Alvarez · Deal Partner',rule:'Offer changes above $1m require partner authority.',
        evidence_for:['Multi-site tenure and service breadth','Base case retains Riverton','No immediate covenant breach'],
        evidence_against:['18.2% ultimate-parent exposure','No minimum-volume guarantee','Financing step-down reduces debt capacity'],
        courses:[
          {id:'COURSE-A',label:'Hold $108.0m',economics:'17.7% IRR · higher sponsor equity',conditions:['Lender accepts exception','Contract review clean'],policy:'ESCALATION RISK',recommended:false},
          {id:'COURSE-B',label:'Reset ceiling to $105.15m',economics:'Restores financing discipline',conditions:['Update offer and IC memo'],policy:'WITHIN PARTNER AUTHORITY',recommended:false},
          {id:'COURSE-C',label:'Defer offer',economics:'Preserves optionality; timing risk',conditions:['Finish contracts and lender call'],policy:'PERMITTED',recommended:false}
        ]
      },
      executionRoom:{
        type:'Offer delivery',recipient:'Hawthorne Capital Markets',sender:'M. Alvarez',document:'Indicative Offer Letter · v8',subject:'Project Keystone — revised indicative offer',message:'Following completion of the customer concentration review, Harbor is prepared to proceed at an enterprise value of $105.15m, subject to the existing diligence and financing conditions.',attachments:['Offer Letter v8.pdf','Concentration analysis.pdf'],checks:['Authority record effective','Offer version checksum matched','Recipient permitted','Conditions attached'],externality:'No message leaves the system in demo mode.'
      },
      replay:{
        snapshots:[
          {id:'seller',date:'27 Oct 2025',label:'Seller materials',known:['Revenue $74.0m','Seller EBITDA $12.7m','Largest customer 7.6% by account'],believed:['Attractive recurring platform'],approved:[],open:['Earnings quality','Parent concentration','Integration']},
          {id:'firm-initial',date:'12 Jan 2026',label:'Firm initial case',known:['Reported EBITDA $10.2m','Systems fragmented'],believed:['Earnings lower quality than advertised','Integration risk material'],approved:[],open:['QoE treatment','Contract durability','NWC']},
          {id:'post-qoe',date:'22 Jan 2026',label:'Post-QoE case',known:['QoE EBITDA $11.9m','NWC target $8.4m'],believed:['Firm EBITDA should be $11.4m'],approved:[],open:['Customer parent mapping','Offer ceiling']},
          {id:'post-cdd',date:'5 Feb 2026',label:'Concentration review',known:['Riverton exposure 18.2%','No minimum-volume guarantee'],believed:['Risk real but base case retained'],approved:[],open:['Partner offer treatment','Seven contracts']},
          {id:'final-ic',date:'10 Mar 2026',label:'Final IC',known:['All core diligence findings'],believed:['Deal works only under conditions'],approved:['$108m EV','4-1 vote','13 conditions'],open:['Execution of conditions','Integration monitoring']},
          {id:'monitoring',date:'31 Dec 2026',label:'Monitoring signal',known:['Project Unify yellow','17 high-severity defects','WIP $6.4m'],believed:['Accepted integration risk is materializing'],approved:['Original IC remains historical'],open:['Intervention decision']}
        ]
      }
    },
    events:{
      earnings:{
        event_id:'EVENT-EARNINGS-V17',type:'SOURCE_TREATMENT',label:'QoE earnings basis requires firm treatment',source_title:'QoE Report v3',source_passage:'The QoE firm supports normalized EBITDA of $11.9m but does not accept $0.5m of forward pricing and utilization initiatives as historical earnings.',locator:'QoE Report · Earnings bridge · p.18',definition:'QoE-normalized EBITDA',period:'FY2025',perimeter:'Alderstone standalone',proposed_position:'The Firm underwrites EBITDA at $11.4m, excluding unrealized initiatives and applying reserves for customer and integration risk.',scene_id:'earnings',synthetic:false
      },
      concentration:{
        event_id:'EVENT-CONCENTRATION-V17',type:'MATERIAL_EXCEPTION',label:'Customer master resolves seven accounts to Riverton',source_title:'VDR Customer Master',source_passage:'Seven billing accounts across six facilities share the same ultimate parent: Riverton Industrial Group. Aggregated exposure is 18.2% of FY2025 revenue.',locator:'VDR · Customer Master · rows 118–124',definition:'Ultimate-parent revenue concentration',period:'FY2025',perimeter:'Riverton parent group',proposed_position:'Riverton is a major concentration risk; retain it in base case only with downside reduction and explicit offer/financing treatment.',scene_id:'concentration',synthetic:false
      }
    },
    transitions:{earnings:transitionFromScene('earnings'),concentration:transitionFromScene('concentration')},
    v16:V16
  };
  Object.assign(window.PANTA_V17_FIXTURE.deal, {
    name: V16.deal.project,
    company: V16.deal.company,
    question_spine: V16.question_spine,
    artifacts: V16.artifacts,
    versions: V16.versions,
    people: V16.people,
    journal: V16.journal
  });
})();
