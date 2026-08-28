(function(){
  'use strict';
  const rooms=[
    {id:'fund-command',label:'Fund Command',section:'COMMAND',icon:'fund',scale:'fund',persistent:true},
    {id:'deal-command',label:'Deal Command',section:'COMMAND',icon:'deal',scale:'deal',persistent:true},
    {id:'sources',label:'Sources & Compiler',short:'Sources',section:'CASE ROOMS',icon:'source',scale:'deal',persistent:true,capability:'source_center'},
    {id:'work',label:'Work',section:'CASE ROOMS',icon:'work',scale:'deal',persistent:true},
    {id:'foundations',label:'What the Deal Rests On',short:'Foundations',section:'CASE ROOMS',icon:'foundation',scale:'deal',persistent:true},
    {id:'unknowns',label:'Everything We Still Do Not Know',short:'Unknowns',section:'CASE ROOMS',icon:'unknown',scale:'deal',persistent:true},
    {id:'shadow-ic',label:'Shadow IC',section:'CASE ROOMS',icon:'shadow',scale:'deal',persistent:true},
    {id:'scenario',label:'Scenario Lab',section:'CASE ROOMS',icon:'scenario',scale:'deal',persistent:true},
    {id:'artifacts',label:'Artifacts',section:'CASE ROOMS',icon:'artifact',scale:'deal',persistent:true},
    {id:'registry',label:'Registry',section:'CASE ROOMS',icon:'registry',scale:'deal',persistent:true},
    {id:'replay',label:'Causal Replay',short:'Replay',section:'CASE ROOMS',icon:'replay',scale:'deal',persistent:true},
    {id:'change-arrival',label:'Change Arrival',section:'CURRENT CHANGE',icon:'arrival',scale:'deal',transient:true},
    {id:'change-review',label:'Change Review',section:'CURRENT CHANGE',icon:'review',scale:'deal',transient:true},
    {id:'change-impact',label:'Change Impact',section:'CURRENT CHANGE',icon:'impact',scale:'deal',transient:true},
    {id:'action-frontier',label:'Action Frontier',section:'CURRENT CHANGE',icon:'action',scale:'deal',transient:true},
    {id:'decision',label:'Decision Room',section:'CURRENT CHANGE',icon:'decision',scale:'deal',gated:true},
    {id:'execution',label:'Execution Room',section:'CURRENT CHANGE',icon:'execution',scale:'deal',gated:true},
    {id:'settled',label:'Settled State',section:'CURRENT CHANGE',icon:'settled',scale:'deal',completion:true}
  ];
  const modes={
    connected:{label:'CONNECTED',detail:'Live projection · no fixture fallback',capability:'SERVER GATED'},
    mock:{label:'MOCK CONNECTED',detail:'Stateful synthetic API · no external effects',capability:'SIMULATED SERVER'},
    offline:{label:'OFFLINE DEMO',detail:'Explicit fixture · read/review only',capability:'READ ONLY'},
    empty:{label:'EMPTY SYSTEM',detail:'No case loaded',capability:'READ ONLY'}
  };
  const dispositions={RECOMPUTES:'Recomputes',SURVIVES:'Survives',FALLS:'Falls',RULE_SWITCH:'Rule switch',HUMAN:'Human',BLOCKED:'Blocked',NO_MAPPING:'No mapping'};
  window.PantaConstants={rooms,modes,dispositions,version:'20.0.0',claimPageSize:20,unknownPageSize:10};
})();
