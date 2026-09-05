# PAN-118 — Statement to cited source

## Investor problem

Opening a source from Trace or Object Lens previously discarded the statement's
location and SourceVersion. The drawer showed the document overview, even when
the investor was inspecting one specific statement.

## Delivered behavior

- Trace opens the selected Claim's SourceVersion, exact locator and original
  passage in one click. Source identity can be resolved through SourceVersion
  when the optional Claim.sourceId is absent.
- Object Lens preserves all backend-supplied source addresses, including distinct
  passages from the same source. Direct Claim inspection retains its own citation.
- The source drawer separates the normalized statement from the cited passage,
  preserves earlier versions, and offers navigation to statements from the cited
  version. General source browsing retains its source overview.
- Missing locations, passage text, statements and source/version conflicts are
  explicit. A normalized statement or current document overview never replaces
  the original quotation. Unresolvable or inconsistent lineage shows no passage.
- Changing case or replay cutoff clears the open citation. Trace selection is
  scoped to the selected question and case state.

## Contract boundary

No kernel or backend adapter contract changed. The existing SourceLocator,
Claim, Source and SourceVersion projections carry the evidence. openSource now
accepts either the existing source id or a full SourceLocator as internal UI
navigation state. The UI displays only passage text actually supplied by the
adapter; it does not fetch or fabricate file content, parse a locator into a
guessed document URL, or switch to the latest source version.

Production integration must supply canonical source/version ids, exact locator
strings and verbatimOrLosslessSpan or excerpt when available. Native PDF/Excel/
audio viewers and extraction-quality work remain separate from this UI slice.

## Verification

- npm run check:all, including focused source-evidence regressions for document
  addresses, spreadsheet ranges, transcript timestamps, historical versions,
  multiple passages, broken references, and immutable source state.
- Product Lab checks of Trace → source, passage selection, source browsing,
  Object Lens citations and responsive drawer presentation.
