# IC memo / live outputs acceptance — 5 September 2026

Implemented and verified under the requested simulated-case acceptance workflow. This is functional acceptance before real cases exist, not a production rollout or a live-model quality benchmark.

## Delivered

| Slice | Behavior |
| --- | --- |
| PAN-126 | Mechanical compilation from the server-owned current case: question readings, attributed admitted views, supplied financial values, open diligence and conditions. Missing information stays open; candidates do not become recommendations. |
| PAN-127 | Every passage has explicit case object IDs and a frozen basis. Its card opens the saved source version at its original locator, including after the cited claim leaves Current; current-case links are separately identified. JSON preserves the complete basis, not just display text. |
| PAN-129 | Content/dependency fingerprints and membership comparisons detect changes, removed sections and new sections. Missing or unversioned claim references block approval. A case change invalidates the old approval/export; dismissing a proposal does not make old content fresh. |
| PAN-130 | Human text is preserved until an explicit save or accepted proposal. Optional AI redraft is reviewable, bounded and checked for passage IDs and numeric changes. Approval records actor, timestamp, case version and content digest. Only the exact latest approved revision can export. |
| PAN-131 | The same create/review/approve/export cycle supports model snapshots, decision packs, HTML presentation drafts and diligence trackers. Model/tracker also export CSV with spreadsheet-formula escaping. |

## Implementation and boundaries

- `app/live_outputs.py`: immutable SQLite revision history with prior-revision links, idempotency keys, optimistic concurrency, frozen declared dependencies and attributed work-product approval. Failed actions roll back. Remote writing runs outside the database write lock; a competing edit prevents the draft from overwriting it.
- `app/output_routes.py` and `app/output_case.py`: mounted by `app/server.py` at `/api/v20/cases/{case_id}/outputs`, `/commands`, and `/{artifact_id}/export`. Reads, writes and export require `X-Panta-Session` plus its matching `X-Panta-Actor`. Authority comes from server assignments: reviewers can edit/sync; partner roles can approve. The production loader uses the current runtime projection, not an HTTP-uploaded snapshot or candidate graph.
- The conservative runtime input projection supports current semantic claims/readings, operative attributed StatedPositions with a known actor, supplied model values, questions and current unknowns. Missing provenance remains missing. Legacy investment decisions lacking a provable frozen basis are omitted; the service does not infer or recreate them. Other explicitly supplied V4 case objects are supported by the compiler. Upstream projection completeness remains necessary for a complete real-case memo.
- `src/providers/liveOutputs.ts`: focused output adapter receiving the host's authenticated case-bootstrap credentials. Its revisions and case versions are submitted with each command. The existing `src/main.tsx` still uses the empty adapter; a real product host must compose the authenticated adapter. This change does not silently connect or publish a real case.
- `src/screens/Outputs.tsx`, `src/design/live-outputs.css`: explicit save/cancel, passage inspection, before/after proposals, review controls, approval and export. Unsaved passages disable leaving Edit mode and governed output actions. Unconnected adapters are visibly read-only.
- Shared source evidence supports citations frozen in saved output passages without replacing the current case. Every supplied identity field must match the saved reference. Original-file access still verifies the cited hash and locator server-side.
- Exports: printable standalone HTML, complete JSON revision/basis record, and CSV for model/tracker. HTML deck sections print as individual pages. No native DOCX, PPTX, XLSX or spreadsheet recalculation is claimed. Downloads are local; no external publication is performed. Original links require access to the PANTA server.

## Model and deployment configuration

The optional writer uses `OPENAI_API_KEY`, `PANTA_MEMO_MODEL=gpt-5.6-sol` by default, the Responses API with strict structured output and `store:false`. Only bounded case-backed passage text and IDs are sent. Recorded human views/decisions are excluded. Provider refusal, partial output, duplicate/unknown IDs, altered numbers and transport failures leave the saved revision unchanged. Model origin and accepting reviewer remain recorded. Numeric preservation is not a proof of factual entailment, units, scope, negation or uncertainty; these remain part of human review.

No OpenAI key was configured in the current shell or local environment files during acceptance, so no live Sol request was made. The lab explicitly uses a simulated writing response. Extraction configuration is unchanged.

The local production store defaults to `vault/output-revisions.sqlite3`; `PANTA_OUTPUT_DB` can select an operator-managed persistent path. A serverless deployment without an explicitly configured output store fails closed. Multi-host shared storage/backup and production bootstrap integration are deployment work, not certified by the temporary lab.

## Reproduce

```sh
npm run check:all
PYTHONPATH=backend/dynamics .venv/bin/python -m unittest \
  backend.dynamics.tests.test_live_outputs \
  backend.dynamics.tests.test_statement_tracking \
  backend.dynamics.tests.test_source_documents \
  backend.dynamics.tests.test_repository_source_tracking \
  tools.test_pan102_xlsx_semantic_context \
  tools.test_qualitative_claims \
  backend.dynamics.tests.test_extraction_adapter -q
```

20 output tests plus 48 tracking/extraction regressions. Frontend gates include authenticated output transport, exact case/revision fields, conflict propagation, export and frozen source identity. `check:all` includes TypeScript, production and lab builds.

Start `.venv/bin/python tools/source_tracking_lab.py` and `npm run lab`, then open `/ic-memo.html#/outputs?caseId=MEMO-TEST`. All documents, graph variants, actors, approvals and output records in this lab are fictional and isolated in a temporary directory. A server restart resets the lab. Store reopening and router re-creation against the same persistent database are covered separately in automated tests.

Manual acceptance exercised:

1. Create the EUR 5m memo; inspect passage → saved basis → original Euro raise section at the verified document hash.
2. Edit a passage. Unsaved edits block switching/approval; save it, return to Read, approve and export HTML.
3. Change the simulated case to EUR 6m. Old text remains, five affected passages need review, approval and export are blocked.
4. Open the old memo citation and verify it still reaches the EUR 5m original, while the case has EUR 6m.
5. Prepare updates, inspect old/new prose, accept changes; prepare simulated editorial redraft, review/accept it, approve the new revision and export full JSON.
6. Reload the browser and observe the saved approval/content; create the model, deck and tracker using the same service and controls.

Canonical corpus files and the user's pre-existing `vault/manifest.md` changes are untouched.
