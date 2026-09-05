# PAN-148 — Fund-specific IC memo editorial profiles

The editorial brief is configurable per fund, reusable across its cases, and
frozen in each memo revision. This acceptance covers the feature and simulated
workflow. It does not close PAN-149 (complete memo with a live writing model).

## Delivered behavior

- Outputs → IC Memo → **Customize fund profile** edits profile name, audience,
  decision purpose, investment context, language, tone, length/depth, analysis,
  recommendations, numeric conventions, scenarios, risks, evidence, citations,
  presentation/appendices and quality criteria.
- All eight supported case content categories retain a stable identity. Their
  titles and order are configurable; empty categories do not invent content.
- **Save new profile version** creates an append-only fund record with version,
  prior version, actor and time. Concurrent edits conflict rather than overwrite.
- New memos use the latest saved profile. An existing memo preserves its exact
  profile and approval after another case edits the fund configuration.
- **Apply profile to this memo** requires the displayed fund version and exact
  output revision. It preserves passage text, IDs, citations and attribution,
  changes headings/order, and returns the memo to draft for review. Pending
  passage proposals must first be resolved.
- **Suggest redraft** sends the memo's frozen profile to the writer. Protected
  attributed views/decisions are excluded. Fixed instructions, numeric/ID
  validation, before/after review and explicit approval remain in force.
- Approved HTML and JSON contain the frozen editorial brief. Custom titles and
  preference text are escaped in HTML. Source tracking continues through the
  existing passage IDs and frozen document references.

## Production association and authority

The production case loader reads `editorial_fund.json` beside a case's `deal.md`:

```json
{"id":"FUND-STABLE-ID","name":"Fund display name"}
```

This is trusted administrator configuration, not a browser-selected fund ID.
Cases with the same stable ID share the profile in the configured durable
`PANTA_OUTPUT_DB` (or the existing local output store). Different IDs are
isolated. A fund strategy/archetype lens is intentionally not treated as tenant
identity. No real case associations were invented or modified for acceptance.

Existing authenticated case access is required to read. The current authority
mapping grants `EDIT_EDITORIAL_PROFILE` to `PARTNER`/`DEAL_PARTNER` assigned to
the case; reviewers retain passage editing without fund profile editing. An
unassociated case can compile using a frozen default but displays a reason why
shared profile saving is unavailable. Host/bootstrap integration remains the
existing Outputs adapter boundary.

## Verification

- **79 Python tests pass**: 11 new editorial acceptance tests plus the existing
  68 output, source tracking and extraction regression tests.
- Coverage includes shared reuse, different-fund isolation, database reopen,
  server-resolved production association/roles, missing association, invalid
  configuration, profile/version conflicts, idempotency, concurrent writers,
  explicit application, case sync preserving custom order/titles, approved
  output stability, exported brief escaping and exact frozen profile delivery
  in a mocked Responses API request.
- **`npm run check:all` passes**, including authenticated adapter command tests,
  TypeScript, product gates, production build and synthetic lab build.
- Browser acceptance on `/ic-memo.html`: save Alpha version 1 with Italian
  guidance and financial section first; create/redraft/review/approve; navigate
  to Alpha case B and confirm shared profile; navigate to Beta and confirm its
  separate English default; save Alpha version 2 from case B; return to case A
  and confirm the memo is still approved on version 1; explicitly apply version
  2 and confirm changed heading, unchanged text and draft/reapproval state.

## Limits of this acceptance

The lab writer is explicitly simulated; its Italian prefix only verifies
profile delivery. It does not demonstrate Italian editorial quality. No live
OpenAI request was made. The production writer still edits supplied passages:
it does not invent absent analysis, render native charts/Office documents,
enforce pagination, or generate unsupported recommendations. Freeform length,
presentation and quality preferences are writing guidance. Complete-memo
quality against a fund's real brief remains the live-model test in PAN-149.

The lab uses temporary synthetic cases and resets on server restart. Durable
persistence is verified independently by reopening the same output database.
