# V1 tracking acceptance — 5 September 2026

The remaining tracking slices (PAN-116, PAN-121, PAN-120) are implemented and accepted under the user's requested simulated-case workflow. PAN-118/PAN-119 cover original-source navigation, documented separately in `PAN-119_ORIGINAL_SOURCE_READER.md`.

## Delivered behavior

- Extraction retains quantitative, qualitative, negative and attributed statements. Numerical values, approximations and text intervals remain distinct. Non-finite numbers and unknown kind/precision tokens are rejected. The original value is retained in adjacent extraction metadata, without changing the frozen CAP-003 payload or claim identity.
- `app/statement_tracking.py` projects the existing identity normalizer's dimensions into a card context. Notes and the V20 read projection preserve units, definition, scope, basis, period, source version, raw value and actual derivation. Missing dimensions remain explicit; a EUR figure and an otherwise equal USD figure remain distinct.
- `src/app/trackingLinks.ts` exposes only declared reference navigation. Source and cited version, statement, calculation inputs, reading supports, human-view scope, current typed relations, recorded decision basis and output sections can be traversed in both directions. These links do not recompute support or propagate state. Missing targets are unavailable, not guessed.
- The shared card shows decision author, date, rationale and frozen case version. A basis from an older case version cannot silently open newer current content, including through a second relation. All recorded connections and causal branches can be expanded beyond the initial five/three items.
- A visible snapshot object remains inspectable when the backend has no additional analysis. Existing valid source references enable the original reader; no mutation permission or causal support is inferred.

## Reproducible checks

```sh
npm run check:all
PYTHONPATH=backend/dynamics .venv/bin/python -m unittest \
  backend.dynamics.tests.test_statement_tracking \
  backend.dynamics.tests.test_source_documents \
  backend.dynamics.tests.test_repository_source_tracking \
  tools.test_pan102_xlsx_semantic_context \
  tools.test_qualitative_claims \
  backend.dynamics.tests.test_extraction_adapter
```

Result: all frontend gates, typecheck, production build and lab build pass; 48 Python tests pass. The frontend gate includes the bidirectional chain, candidate/other-case isolation, exact source versions, frozen decision basis, missing references, challenge direction, more than five links and non-mutation tests.

An additional 36 derivation, claim-identity migration and operative-claim tests cover the shared extraction/identity boundary. That check exposed existing vocabulary drift: Customer Churn, Total Net Leverage Ratio and Minimum Liquidity were accepted by the extractor but normalized to an empty metric. The existing canonical names are now recognized. Stored IDs are not rewritten; new extractions of those three formerly unresolved metrics now receive their proper canonical metric identity. Existing claims with legacy unresolved identities need an explicit re-extraction/migration before reconciliation; navigation continues to use their supplied IDs.

The seven-statement synthetic document runs through the real Markdown parser, simulated schema-shaped model responses, deterministic validator/assembler, unchanged E3 payload, metadata transport, note persistence and card projection. Each original section resolves at the verified document hash. This tests transport and deterministic behavior, not the recall or accuracy of a live model.

## Application check

Start `.venv/bin/python tools/source_tracking_lab.py` and `npm run lab`; open `/source-tracking.html`. The lab banner identifies simulated extraction, analyst and decision records in an isolated temporary vault. Find “primary cash proceeds of EUR” in the case search.

Verified manually in the running PantaApp:

1. The EUR 5 million statement shows type, precision, definition, period, scope, basis and currency.
2. Open source → Open original selects and highlights only the Euro raise section in `typed-tracking.md`.
3. Statement → twice-primary-raise formula (EUR 10 million, explicit input) → attributed test view → recorded test decision.
4. Decision → view → formula → statement → source works in reverse.
5. Expand source connections to reach all seven statements. The 30–60 days statement remains a range and explicitly lists missing definition, period, scope and basis.

## Runtime boundary and next work

This completes tracking acceptance on simulated cases, not a production launch certificate. A production case adapter must still deliver the typed claim projection and declared runtime references to PantaApp. The existing production entry uses the empty adapter; the acceptance app uses the isolated test adapter. Original corpus files and the user's vault manifest are not modified.

Next macro: PAN-106, IC memo. Its remaining slices are compilation from admitted case state, per-passage basis, stale indicators, reviewable redraft/approved export, and extending the maintenance cycle to other artifacts. Tracking now supplies the navigation primitive; those output behaviors require their own implementation and acceptance.
