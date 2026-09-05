# PAN-119 · Original source reader

## User problem and implemented behavior

An investor must be able to click a case information item, read its concise
context, and open the actual cited source at its recorded location. Showing a
locator string alone does not complete that journey.

Object Lens now adds the selected statement, supplied numeric dimensions,
formula and referenced inputs, or attributed human view to the existing causal
trace. Trace supports open the same inspection card. Source details preserve
origin, version and quoted span; **Open original** verifies the source before
switching the same drawer into a focused reader. Back navigation restores the
citation. Only one modal is mounted on mobile.

## Backend contract

All three read endpoints use the existing case and source-envelope references:

- `GET /api/v20/cases/{case_id}/source-document` returns the versioned
  `source-document/1.0` descriptor, filename, requested locator, resolved
  position, view URL and download URL.
- `GET /api/v20/cases/{case_id}/source-document/view` renders the focused original.
- `GET /api/v20/cases/{case_id}/source-document/file` serves the original bytes;
  `download=true` sets attachment disposition. Single byte ranges support native
  audio/video seeking.

Required query parameters are `source_id` and `source_version_id`; descriptor
and view additionally accept `locator` and `claim_id`. The source version must
be a full `sha256:` content hash from ingestion. A file is eligible only when a
same-case inbox manifest or evidence proposal contains a matching envelope.
The reader resolves only its registered inbox basename, rejects escapes and
out-of-inbox symlinks, and verifies the hash on every request. It never substitutes
the current file for a cited earlier version. Missing originals return 404,
changed bytes 409, and unresolvable versions or invalid document positions 422.

Responses use private/no-store and nosniff. Rendered HTML escapes source text,
has no script execution, and is restricted to same-origin embedding. This uses
the existing local V20 case access boundary; it adds no separate public file
store or authentication scheme.

## Location fidelity

| Source | Reader behavior |
| --- | --- |
| PDF | Opens the recorded page. A uniquely matching supplied verbatim quote is highlighted and anchored; otherwise explicitly shows the page without an exact passage highlight. |
| XLSX / XLSM | Selects the cited sheet and cell/row range, with adjacent context. Displays original formulas and cached values without recalculation. |
| UTF-8 text / CSV | Selects supplied line ranges. Unsupported locator syntax remains unresolved. |
| Markdown | Selects a uniquely matching complete heading; ambiguous/truncated headings remain unresolved. |
| DOCX | Selects blocks using the same docx2python block numbering as extraction. This is a text/table reading, not a reproduction of Word page layout. |
| SRT / VTT | Matches cue ordinal and start/end timestamps against the original transcript. It does not invent a link to a separate recording. |
| Audio / video | Opens the registered original with the native player's timestamp fragment and byte ranges. Playback depends on browser codec support; arbitrary media duration is not certified by the locator parser. |
| Other formats | Original download with an explicit unavailable focused-reader state. |

`LOCATED` means the address can be resolved at the precision shown (page, range,
block, cue, or requested media time). It does not certify the investment claim.
Missing or ambiguous locations use `UNRESOLVED`, never a guessed selection.

Vault claim notes now retain source/version/locator, knowledge date and a
supplied verbatim span. Existing frozen extraction fields and claim identities
are unchanged. No inferred quote is created from normalized statement text.

## Frontend integration

`PantaApp` supplies a same-origin HTTP reader through `withSourceDocuments`.
Existing stateful adapter methods retain their receiver. An adapter may provide
its own optional `loadSourceDocument` implementation. The HTTP decoder checks
descriptor identities and view/download origins, paths and cited versions.
Selection, case and replay changes discard pending reader results.

The production entry still uses the repository's existing empty adapter.
Embedding applications must supply their real case adapter and serve/proxy the
V20 reader on the same origin. This change does not replace the full production
case projection adapter.

## Verification

- `npm run check:all`: contract, fixture-free, behavior, source evidence,
  source-document HTTP regressions, TypeScript, production and both lab builds.
- `PYTHONPATH=backend/dynamics .venv/bin/python -m unittest backend.dynamics.tests.test_source_documents backend.dynamics.tests.test_pan56_source_capabilities backend.dynamics.tests.test_v20_live_evidence_loop backend.dynamics.tests.test_v20_capabilities backend.dynamics.tests.test_pan96_new_document_pipeline`: 22 tests.
- Browser checks at 1280×900 and 390×844: card → citation → native PDF,
  highlighted Excel range/formula, selected transcript, audio positioned at
  1 second of a 4-second fixture, back navigation and one modal with no page
  overflow on mobile.

Reproduce without touching the repository vault:

1. `.venv/bin/python tools/source_tracking_lab.py`
2. `npm run lab`
3. Open `/source-tracking.html` on the lab server. All data is explicitly synthetic.

## Remaining PAN-119 scope

Universal capture is not claimed complete: older claims without verifiable
source versions/locators still need provenance-preserving migration or
re-extraction. Truncated or nonstandard locators, scanned PDFs without an exact
text span, and further native formats need their own coverage. The reader makes
these gaps visible. PAN-119 and the PAN-109 tracking macro remain in progress.
