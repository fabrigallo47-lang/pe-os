# Action → Event / State Matrix

| User action | Frontend command | Expected backend consequence |
|---|---|---|
| Add material | ADD_MATERIAL | source arrival / ingestion events; refreshed case |
| Admit review | REVIEW_ITEM / ADMIT | attributed reading-admission event + real propagation |
| Correct review | REVIEW_ITEM / CORRECT | correction + admission event with actor |
| Reject reading | REVIEW_ITEM / REJECT | review event; source/finding retained |
| Test without support | inspectObject(excludeObjectIds) | temporary inspection only; no ledger mutation |
| Run simulation | runSimulation | sandbox result only; no ledger mutation |
| Adopt work item | ADOPT_WORK_ITEM | actor-attributed work-item-adoption event |
| Edit proposal | UPDATE_WORK_ITEM_PROPOSAL | proposal-change event/state |
| Dismiss proposal | DISMISS_WORK_ITEM_PROPOSAL | proposal disposition |
| Assign work item | ASSIGN_WORK_ITEM | owner Actor ref + event |
| Adopt formation | ADOPT_FORMATION | reviewed case structure becomes live |
| Correct formation | CORRECT_FORMATION | attributed structure patch/event |
| Record decision | RECORD_DECISION | decision record + actor + frozen caseVersion |
| Create artifact | CREATE_ARTIFACT | projection initialized from current case |
| Sync artifact | SYNC_ARTIFACT | projection diff + version + sync event |
| Sync all | SYNC_ALL_ARTIFACTS | bounded projection updates for all artifacts |
| Edit artifact block | UPDATE_ARTIFACT_BLOCK | attributed human edit event/version |
| Accept suggestion | ACCEPT_ARTIFACT_SUGGESTION | accepted edit with provenance |
| Dismiss suggestion | DISMISS_ARTIFACT_SUGGESTION | suggestion disposition |
| Open source | frontend source drawer | no mutation; resolved source object |
| Filter Case changes | loadJournal | read-only filtered journal; no ledger mutation |
| Select comparison or closing state | loadJournal | read-only backend comparison of immutable Current states; no ledger mutation |
