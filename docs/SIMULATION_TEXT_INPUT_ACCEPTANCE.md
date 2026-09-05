# Text entry for graph simulation — 5 September 2026

The primary Simulate entry is now **Describe a change**. An investor writes a
hypothetical, previews a concrete interpretation, and explicitly chooses
**Simulate these changes**. The proposal stage does not run a transition or
change Current. Existing item/connection editing and event scenarios remain
available in the same room.

The interface and case-derived example wording are in English. **Insert a case
item (optional)** and **Examples (optional)** are shortcuts, not prerequisites
for typing a scenario. The language-availability helper paragraph has been
removed at the user's request; proposal interpretation and clarification remain
visible in the review step.

## Available without a model

The guided interpreter is working locally, with Italian and English command
forms, current names/IDs, a small disclosed financial vocabulary, case-derived
examples and insertion of exact case names at the cursor. Supported instructions:

- increase/decrease a model assumption by an explicit percentage;
- set an explicit model value;
- withdraw an evidence item or another permitted current item;
- mark an item usable/unusable, current/stale;
- connect/disconnect a current Claim to an existing support path;
- replace the supporting Claim in an existing path;
- combine instructions with semicolons or newlines.

Percentages are compiled with Decimal against the recorded Current value. No
formula or downstream effect is inferred in the interpreter. Ambiguous names,
missing amounts, negated commands outside the grammar, unsupported wording and
conflicting changes to one field return clarification questions. If only part of
a batch is understood, the proposal remains unready and cannot be run from the
preview. The UI labels guided interpretation explicitly; it is not advertised as
unrestricted natural language understanding.

## Optional open-ended interpretation

The production router connects `ProposalModel` when `OPENAI_API_KEY` is present.
`PANTA_SIMULATION_PROPOSER_MODEL` selects the model; the default follows this
repository's existing writing service (`gpt-5.6-sol`). Production loads ignored
local environment files through the existing server bootstrap. For the standalone
lab, pass configuration in the server process environment. Never commit keys.

When guided interpretation cannot account for the description, the model receives
only the complete catalog of current editable objects and the description. No
case sessions, credentials, authority policies, approved snapshots or attributed
human views are included. It proposes typed actions with exact source-text quotes
and clarification questions. IDs and operations are checked against the actual
case catalog, numbers must be present in the user's description, and all generated
mutations pass the same manual graph-mutation validator before display. The model
does not calculate effects or execute tools. Current and decision authority remain
with the existing runtime.

The API uses a strict JSON schema, bounded output, a 45-second timeout and
`store: false`, with explicit handling of incomplete/refused/malformed responses.
Transport errors do not silently turn into a fabricated local interpretation.
API contract reference: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

**Environment status at acceptance:** no model credentials were configured. The
live guided path was verified in the browser. The optional model request/schema,
response processing and semantic guards were tested with controlled responses;
a live-model quality evaluation remains dependent on model configuration.

## Runtime and transport

- `POST /api/v20/cases/{case_id}/simulations/propose` accepts exactly `text`,
  `caseVersion`, and `graphVersion`. Case authorization occurs before state/model
  loading. The full graph/state/policy basis is pinned as in ordinary simulation.
- Response `simulation-proposal/1.0`: original description, interpreter mode,
  READY/NEEDS_CLARIFICATION, inspectable proposed changes, before/after values,
  source wording, rationale and questions with canonical references.
- `PantaBackendAdapter.proposeSimulation` is optional and forwarded by both the
  connected simulation adapter and the shared source-document wrapper. No
  disconnected adapter is presented as capable of interpreting text.
- Editing the description, resetting, switching case or changing the graph basis
  invalidates old proposals; late responses are discarded. Simulation remains a
  separate explicit action after the reviewable proposal.
- The existing graph POST executes the reviewed mutations. Its canonical request
  preserves the user's description, and the immutable archive freezes that text
  with the actual mutations/engine result. Different descriptions cannot collide
  under one archive identity. Editing individual mutations clears an obsolete
  textual description.
- The frontend compares executed mutations independently of their order: the
  runtime sorts a batch canonically while the proposal preserves the user's
  wording order. Mutation contents and multiplicity must still match exactly.

## Validation

- 17 new Python tests cover bilingual requests, exact arithmetic, qualitative and
  structural changes, combined scenarios, no transition during interpretation,
  no input mutation, negation, ambiguous identities, partial/conflicting requests,
  bounds, stale basis, optional model selection, protected human/authority context,
  unknown identities, invented numbers/quotes, new hypothetical evidence, API
  completion/refusal guards, authenticated HTTP and archival text retention.
- The graph/numeric/query/proposal regression suite passes (80 tests).
- `tests/simulation-proposals.mjs` uses an actual HTTP-generated proposal and the
  real `withSourceDocuments` wrapper. It checks request routing/auth, immutable
  snapshots, exact text/version matching, unresolved status, duplicate items,
  canonical identities and quote validation. Included in `npm run check:all`.
- Graph transport acceptance includes a real combined text proposal whose
  mutations are reordered by the runtime. Altered, omitted or duplicated
  mutations and extra executed events remain rejected.
- `npm run check:all` passes, including TypeScript, all production contract and
  transport checks, production build and lab build.
- Browser acceptance: percentage description → preview 60 to 66 → explicit
  simulation → real graph consequences; an ambiguous customer event stays at
  clarification; a combined qualitative/quantitative scenario is reviewable
  and executable through the same frontend.
