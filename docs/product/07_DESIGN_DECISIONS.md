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
