# PANTA Design / Product Decision Log

Append only material decisions that should survive individual tasks.

## Format
### YYYY-MM-DD — Decision title
**Decision:**

**Why:**

**Applies to:**

**Do not infer:**

---

### 2026-09-03 — Code becomes the product design source of truth
**Decision:** After the golden Figma states, ongoing product evolution happens in the real frontend. Figma is reserved for genuinely new visual/interaction exploration.

**Why:** This prevents mock/code divergence and lets product decisions be validated in a working system.

**Applies to:** All rooms and Outputs.

**Do not infer:** Figma is banned; it remains useful for new interaction concepts when code-first exploration would be slower.

---

### 2026-09-03 — Governed lifecycle navigation stays in case context
**Decision:** Formation, Review & Admit, and Replay & Decision are reachable from a shared Case flow control and from the Decision Pack with their current state and human preconditions visible. Case events enter Replay at `knownAt`, preserving the distinction between when something happened and when it was known. Mobile retains the same routes and utilities through the Case flow menu.

**Why:** Governance steps and historical context must be discoverable without turning PANTA into a generic application menu or flattening the distinct job of each room.

**Applies to:** Global shell, Deal Home, Workstream Focus, Object Lens, Decision Pack, and mobile navigation.

**Do not infer:** The lifecycle is a linear workflow, or that navigating to a governed room grants authority to act there.

---

### 2026-09-03 — Case context is addressable and inspection preserves orientation
**Decision:** The current case, workstream, question, and historical cutoff live in the route URL. Context changes schedule one race-safe projection load; object search and source selection resolve into a visible Object Lens. On mobile, inspection uses a focus-managed bottom sheet, and contextual Back is a stable content-level destination rather than incidental browser history.

**Why:** Refresh, deep links, back/forward, asynchronous work, and small-screen inspection must preserve the investor's place without ever presenting an old projection as the newly selected case.

**Applies to:** Global shell navigation, case projection loading, Find in Case, Sources, Object Lens, Trace, Simulate, Resolve, Formation, Replay & Decision, and Outputs.

**Do not infer:** URL state is authoritative case data, a browser route may mutate the ledger, or a visible selection grants authority over the selected object.

---

### 2026-09-03 — The topbar distinguishes case, rooms, and decision context
**Decision:** The shell names the active case explicitly as “Current case” and keeps it in a persistent case selector. Navigation across working surfaces is labeled “Case rooms.” The Decision desk entry exposes the decision question, the available human paths, and its due date before navigation.

**Why:** Investors must be able to answer three different orientation questions at a glance: which case am I in, where can I work, and what accountable decision is approaching.

**Applies to:** Global shell, responsive navigation, case switching, and Replay & Decision entry points.

**Do not infer:** The topbar owns case state, that a listed decision path is a recommendation, or that opening the Decision desk grants authority to record a decision.

---

### 2026-09-03 — Formation exposes assembly and creator-derived ownership
**Decision:** Formation presents raw case materials as inputs to a visible assembly into proposed workstreams, questions, readings, and a single investor-facing “Still open” layer. Selecting material reveals its contribution to the proposed structure. The actor on the canonical case-creation event is the initial Case Owner; only that owner may edit or adopt the initial structure, and adoption makes it live.

**Why:** Formation must make PANTA's structuring value legible before the investor governs the result, while keeping authorship, authority, and unresolved evidence honest.

**Applies to:** Formation, synthetic lab coverage, formation correction, and initial-structure adoption.

**Do not infer:** Adding a source grants ownership or adoption authority, every open item requires Resolve, formation material mappings are a new source of truth, or the proposed structure is live before adoption.

---

### 2026-09-03 — Object Lens uses one calm inspection surface
**Decision:** Object Lens remains one continuous inspection panel. Its five explanatory sections use stronger semantic headings, deliberate vertical rhythm, restrained hairlines, and a distinct action footer; related objects continue to resolve through canonical investor-facing labels.

**Why:** An investor should be able to separate evidence, gaps, consequences, change history, reuse, and available actions within seconds without the Lens becoming a stack of cards or a competing room.

**Applies to:** Object Lens in floating, compact, embedded, and mobile-sheet contexts.

**Do not infer:** Section styling changes inspection logic, creates new object types, changes available actions, or permits unresolved internal IDs in user-facing copy.

---

### 2026-09-04 — Product Lab case modes swap adapters at the composition root
**Decision:** The local Product Lab exposes an explicit Empty case / Synthetic case switch above the product shell. Empty mode mounts the existing null-case adapter; Synthetic mode mounts the rich development adapter. A mode change remounts the product tree, persists in the lab URL, and removes synthetic case context while Empty is active.

**Why:** Product review needs an unmistakable way to compare the honest zero state with a representative populated case without introducing fixture branches into rooms or allowing state to leak between modes.

**Applies to:** Local Product Lab composition, responsive lab labeling, development adapter selection, and lab verification.

**Do not infer:** This is production navigation, that a created case may be ownerless, that rooms know about fixture modes, or that synthetic content may move into `src/`.

---

### 2026-09-04 — Zero state distinguishes selection from formation
**Decision:** “No case selected” is a workspace state with no case-room navigation and entry actions to start or open a case. A created case with no material is a different state: its canonical Case and creator-derived Case Owner are visible, Formation is the sole starting room, and adding material is the primary action. The Product Lab therefore exposes three adapter-backed states: No case, Empty case, and Synthetic case. This supersedes the earlier two-mode interpretation of Empty as the null-case projection.

**Why:** A missing selection and an unformed new case imply different truths, available actions, and navigation. Conflating them makes case-only governance appear before a Case exists and hides the first meaningful Formation step after creation.

**Applies to:** Global zero-state shell behavior, Formation entry, host-provided case entry actions, and local Product Lab modes.

**Do not infer:** A Case exists without a `CASE_CREATED` event or owner, the frontend may fabricate case creation, or any no-case/empty-case fixture content belongs in production `src/`.

---

### 2026-09-04 — The shell reads as one institutional context sequence
**Decision:** The shared top bar uses one compact visual sequence: PANTA, Current case, Current room, decision context, then case utilities. Every route has a stable investor-facing room name; deeper workstream and question context may compress before that room name. The selected case and no-case state use the same labeled context grammar, while Case rooms remains the responsive home for navigation and utilities.

**Why:** The shell should orient an investor immediately without competing boxed controls, ambiguous truncated room text, or a dominant brand mark. Its actual height must also match the shared shell-height token so sticky and overlay surfaces align predictably.

**Applies to:** Global shell composition, case selector, room breadcrumb, Decision desk entry, responsive case-room navigation, and shell-dependent offsets.

**Do not infer:** The visual sequence changes route behavior, makes breadcrumbs a source of case truth, removes any room or utility, or changes decision authority.

---

### 2026-09-04 — Deal Home workstreams are attention summaries, not evidence tables
**Decision:** Each Deal Home workstream is a compact band built from the canonical current CaseReading, the first backend-surfaced open Unknown, the first operative referenced WorkItem, the explicitly assigned Workstream owner—or a distinctly labelled next-step owner when no Workstream owner exists—and an optional explicitly linked CaseEvent. The route, reading, gap, work item, and owner use distinct visible controls. HumanPosition remains separately attributed when present; evidence mechanics remain in Object Lens and Trace.

**Why:** Deal Home must let an investor scan the current view, unresolved point, next diligence move, and accountability without exposing support-count mechanics or making static text behave like invisible navigation.

**Applies to:** Deal Home workstream composition, contextual actor profiles, workstream routing, Object Lens entry points, and responsive workstream bands.

**Do not infer:** Array order creates a new priority field, a WorkItem owner becomes the Workstream owner, a CaseReading is human-authored, missing actor data means no owner reference exists, or a change may be shown without an explicit event link.

---

### 2026-09-05 — Review is exceptional and organized by case impact
**Decision:** Review changes replaces the Review & Admit surface. Evidence ingestion and clear factual updates remain automatic; the review queue contains only backend-proposed material, ambiguous, or judgment-bearing changes, aggregated by impact on the institutional case. Each proposal presents what would change, why, the current and proposed reading, downstream changes, and the human actions Update case, Edit, or Dismiss.

**Why:** Investors should govern consequential changes to the investment case, not process every extracted fact or source claim. A large source may therefore produce many machine-level updates but only a few human review proposals.

**Applies to:** Review route naming, lifecycle navigation, exceptional-review composition, synthetic aggregation coverage, and investor-facing action language.

**Do not infer:** The UI may bypass authority, remove audit lineage, merge canonical objects, fabricate HumanPositions, or reinterpret ADMIT/CORRECT/REJECT command dispositions; those remain internal governed contract semantics behind the simplified actions.

---

### 2026-09-05 — Replay and Decision are two different cognitive modes
**Decision:** Replay is a temporal reconstruction driven only by meaningful ledger-backed CaseMoments and reloads the same case at the selected `asOf` cutoff. Decision is a current-state IC desk organized around backend-selected decision-critical Questions. Their qualitative load-bearingness, severity, fragility, criticality, condition, and canonical basis refs are projection data from the live underwriting graph. Decision paths appear only inside the recording form after every current critical Question has been reviewed. A recorded Decision replaces the undecided desk and exposes actor, timestamp, conditions, case version, and supporting Question refs.

**Why:** Historical understanding and current institutional judgment are different investor acts. Combining them makes Replay leak current choices and makes Decision begin with generic outcomes instead of the few unresolved issues that actually carry the underwriting.

**Applies to:** Replay & Decision composition, meaningful moment fixtures, Question decision projections, deep navigation, decision recording, recorded-decision state, Deal Home and shell decision summaries.

**Do not infer:** The frontend selects, ranks, scores, or authors decision-critical Questions; invents decision dimensions; recommends a path; mutates historical state; or weakens the authority and frozen-snapshot requirements of `RECORD_DECISION`.

---

### 2026-09-05 — Causal tracking uses progressive focus plus a complete audit view
**Decision:** Object Lens exposes a one-hop directional trace with “Why?” and “Where it matters”; opening a mapped object continues the trace from that object. Review changes and Simulate use the same impact-reading grammar: a backend-ordered flow for comprehension and a complete audit table that keeps changed and held objects visible. Relationship explanations come only from mapped relations, while freshness, evidence, decision, institutional, and work states remain visibly separate.

**Why:** Investors need the practical equivalent of spreadsheet precedents and consequences across evidence, readings, models, questions, conditions, decisions, and work—without a global graph becoming unreadable or the frontend guessing a causal path.

**Applies to:** Object Lens, Review changes, Simulate, synthetic behavior coverage, and shared impact-trace presentation.

**Do not infer:** Visual order creates a new causal relation; affected means changed; an accepted human position is current evidence; the frontend may infer missing edges, merge state axes, rewrite HumanPosition, or mutate the live case during simulation.

---

### 2026-09-05 — Case changes separates historical movement from temporal replay
**Decision:** Case changes is a dedicated read-only room. It combines the canonical institutional event timeline with backend-computed differences between two immutable Current states. Effective, knowledge, and recording time are shown separately with actor attribution. Baseline, Current, and closing states are explicit adapter inputs; post-close movement appears only when a closing state is selected. Contract or integrity failures show no partial history.

**Why:** Replay answers what the case looked like at one prior cutoff; Case changes answers what moved between two states and which institutional events accompanied that movement. Keeping those jobs separate makes the audit trail legible without asking the frontend to compare case objects or infer direction.

**Applies to:** Case changes navigation, Journal filters, immutable state selectors, event timeline, state-difference summary, post-close movement, adapter codec, empty and synthetic Product Lab adapters, and fail-closed error states.

**Do not infer:** The frontend computes differences, decides whether movement is positive, treats disappearance as resolution, collapses temporal axes, invents actor attribution, mutates the live case, or labels ordinary Current movement as post-close drift.


---

### 2026-09-05 — Statement inspection preserves the cited source version and passage
**Decision:** Trace and Object Lens carry the full existing SourceLocator into the source drawer. The drawer separates the statement in the case from its original passage, displays the exact address and cited version, and exposes other statements from that version. Conflicting or unresolvable source lineage shows an explicit unavailable state. General source browsing keeps its document overview.

**Why:** An investor opening a statement needs its actual evidence, including an earlier cited version, without losing the address or seeing newer document content substituted for the original passage.

**Applies to:** Trace, Object Lens source references, source drawer, internal source navigation, synthetic fixtures and source-evidence regressions.

**Boundary:** Source addresses and quoted spans come from the existing backend projection. This change introduces no ontology, extraction logic, inferred provenance, document URL, native file viewer, or canonical mutation.

---

### 2026-09-05 — Information cards open the verified original at the cited location
**Decision:** Object Lens presents concise content and supplied context before its existing causal trace. Source details open a focused original reader in the same drawer, with a return to the citation and a download of the verified bytes. The backend resolves existing case-scoped source envelopes and verifies the cited content hash on each read. A page, range, block, cue or media time retains its actual precision; missing or ambiguous locations are explicit.

**Why:** The investor needs both an immediate explanation and an auditable route to the source. An address alone is insufficient, and a current file cannot silently replace the cited version.

**Applies to:** Shared information summary, Trace supports, source drawer, same-origin source reader, durable claim provenance, isolated native-document lab and regression tests.

**Boundary:** This extends the earlier citation-only UI with original-file access. It adds no ontology, inferred calculation input, quoted text synthesized from a statement, canonical mutation, or full production case adapter. PDF highlighting requires a unique exact source quote. Legacy missing references and unsupported locations remain visible gaps, not successful precise opens.

---

### 2026-09-05 — Tracking can be verified on supplied test graphs and native originals
**Decision:** A read-only repository lab connects the existing Keystone execution graph and canonical statements to their actual test documents through the shared information card and source reader. It preserves declared input edges and exposes unresolved text addresses in a dedicated filter. Multiple explicit cells or headings can open together; Word sections, PowerPoint slide content, email parts and image/PDF regions retain their actual source precision.

**Why:** Testing the complete click-to-source journey should use the documents and graphs already available. Missing real cases do not prevent validation, while generic references must remain distinguishable from precise source locations.

**Applies to:** Isolated repository tracking lab, original-document readers, source-address audit report and native-document regression coverage. The supplied corpus contains 19 originals, 14,318 model nodes and 30,996 declared links; 30 of 75 canonical textual references still lack a resolved passage.

**Boundary:** Test-import hashes identify copied original bytes, not retroactive ingestion history. The lab does not adopt Current, fabricate HumanPositions, infer missing graph edges, rewrite original gold data, or claim extraction accuracy from gold reference addresses. PowerPoint and Word content readers do not promise native page layout. Address resolution verifies where to look, not whether a claim is true.

---

### 2026-09-05 — Explicit simulations can complete source-navigation acceptance
**Decision:** The tracking lab offers a separately identified simulated case whose 30 previously generic references have audited, hash-locked source ranges. The same case can run inside the production PantaApp shell and Trace screen through a read-only test adapter. Multiple disjoint lines stay within one citation and are all highlighted; the original reference is retained. Source inspection exposes the statements citing that source.

**Why:** The user asked to simulate the remaining conditions and proceed if the complete journey worked. A verified test case can establish that the reader and app integration work before live cases exist.

**Applies to:** V1 source-navigation acceptance, test-reference mappings, multi-range text reader, repository test adapter and application preview. All 75 canonical test references resolve in the simulated case, including the 30 previously unresolved ones.

**Boundary:** This is explicit test normalization, not an automatic extraction score, real ingestion history, or institutional adoption. The original corpus and raw audit are preserved. The simulation's question and system reading exist only to exercise the room. It creates no attributed HumanPosition or investment Decision and does not close unrelated macro-task requirements.

---

### 2026-09-05 — Typed statements retain context through the complete recorded trace
**Decision:** Statement cards expose the existing extractor's kind, typed value, original value, precision, definition, period, scope, basis, unit and currency. Missing dimensions and validation notes remain visible. Durable notes retain this context and the actual derivation. Recorded connections let an investor navigate explicit source/version, input, reading, attributed view, decision-basis and output-section references in both directions; longer branches can be expanded.

**Why:** A precise source address is insufficient if a number loses its units in transport or if the investor cannot continue from a calculation to its recorded use. The same card should preserve the content and the chain without claiming that navigation computes investment consequences.

**Applies to:** V1 tracking acceptance, shared Object Lens, source versions, extraction metadata, durable indexing, and the isolated source-tracking application lab.

**Boundary:** Canonical CAP-003 fields and stored identities remain unchanged. The projection uses existing normalization and declared references; it creates no graph edges, causal conclusions, adoption or human judgment. The identity drift gate also restores three existing extractor metric names missing from the normalizer (Customer Churn, Total Net Leverage Ratio, Minimum Liquidity); new extractions use their proper metric identity, with no automatic migration of stored unresolved claims. Candidate and other-case relations do not become Current links. A decision's older basis is unavailable in a newer case projection instead of silently opening newer content. An existing visible object may have a basic inspection without backend analysis; only its existing source reference enables source reading. A separate, visibly simulated lab fixture supplies fictional analyst and decision records to test this complete chain. Model responses are simulated; this acceptance does not score live extraction on unseen documents.

---

### 2026-09-05 — Outputs retain their basis, require review, and export an approved revision
**Decision:** IC memo, model snapshot, decision pack, presentation draft and diligence tracker use one versioned output service. Creation renders admitted case content mechanically. Every passage opens its own information card, including saved citations and the current case connections. Case updates prepare before/after proposals; they do not overwrite editorial text. Saving is explicit, and unsaved edits block switching modes, synchronizing or approving. An attributed case view or decision is edited in the case, never in the output. AI suggestions retain their model origin and the identity of the accepting reviewer.

**Why:** An IC memo must remain reviewable when the case changes. A downloaded file without its evidence or an apparent sync that only clears a badge cannot establish which case, text and reviewer the committee actually saw.

**Applies to:** Outputs room, authenticated output adapter and HTTP service, immutable output revisions, passage freshness/missing-basis states, optional writing assistant, approved HTML/JSON and model/tracker CSV, and isolated IC memo acceptance lab. Unconnected adapters expose a reason for disabled editing controls.

**Boundary:** Output revisions and approvals are work-product records, not adoption of Current or investment decisions. The server resolves both case content and actor authority; caller-supplied snapshots, roles and timestamps cannot approve a version. Source citations frozen in a passage can open earlier originals even after the statement leaves Current; the source reader still verifies the exact bytes and location. The writing model is optional GPT-5.6 Sol through the Responses API. Numeric checks and schema validation do not establish semantic truth; reviewer acceptance remains required. HTML is a portable, printable export; this slice does not generate native Office files or deploy the product. The production entry's host/case bootstrap integration remains a separate integration boundary.
