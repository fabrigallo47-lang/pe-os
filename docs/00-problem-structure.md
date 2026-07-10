# PE OS — Structure of the Problem

*Founding systems-engineering document. Derived from the Manifesto, the OSPM draft, and the current-process map. Everything here is reasoning about structure, prior to any build decision.*

---

## 1. The problem is six problems

"AI Operating System for private equity" conflates six sub-problems that have different natures, different difficulty, and different owners. Naming them separately is the first act of engineering, because most failed products in this category failed by solving one of these while believing they were solving another.

| # | Layer | The question it answers | Nature |
|---|-------|------------------------|--------|
| A | **Ontology** | What kinds of things exist, and how do they relate? | Design / IP |
| B | **Perception** | How does the world enter the system without humans typing? | AI / ingestion |
| C | **State** | Where does the truth of a deal live? (the Obsidian/KG question) | Data engineering |
| D | **Inference** | What does the system notice, rank, and propose? | AI / graph reasoning |
| E | **Authority** | What may an agent do alone, and how is that audited? | Governance |
| F | **Interaction** | Where do humans see, correct, and decide? | Product / views |

Two structural observations:

1. **A is the product.** The Manifesto says it directly: "we own the container: the ontology through which free intelligence flows." B and D are increasingly commoditized by frontier models (they are Category-3 work — generated analysis, collapsing in value). E is a table plus discipline. C and F are substrate choices. Only A is both scarce and durable. Therefore the project's first deliverable is a formal ontology, and every substrate decision must be judged by whether it keeps the ontology explicit, inspectable, and portable.

2. **The layers are separable, and must be kept separable.** The Obsidian-vs-knowledge-graph question only concerns C (and partially F). The event-driven "OS that doesn't wait for the question" behavior lives in D. Conflating them leads to either "Obsidian can't do push, so Obsidian is wrong" or "a graph DB is powerful, so start there" — both category errors.

---

## 2. The ontology (Layer A) — the entity core

Extracted from the OSPM draft, made explicit. This is the type system the whole project rests on.

### Entities

- **Question** — the atomic unit of reasoning. Nests (thesis → sub-questions). Has a state: `open | reducing | resolved | accepted-unresolved`. The fourth state is the novel one: it is the state in which most capital is deployed, and it exists in no current system.
- **Claim / Evidence** — a statement bearing on a question, with an **epistemic type**: `asserted` (someone said it) | `derived` (follows from something, derivation inspectable) | `observed` (happened and was recorded) | `attested` (a third party stands behind it). Types compose: a conclusion built on derived-over-asserted is an assertion with arithmetic on top. **Evidence attaches to questions, not to deals** — this is the single most consequential modeling decision, because it is what makes evidence reusable across deals ("does this ramp hold?" retrieves the 2022 expert call even though that deal died).
- **Artifact** — the container a claim came from (deck, model, transcript, email). Artifacts stay where they are; the system holds *claims with provenance pointers into artifacts*, not copies. The unit of meaning is the claim, not the container.
- **Decision** — records both halves: what was resolved and with what strength; what was accepted as unresolved and why that was tolerable. Made by a named human.
- **Outcome** — attaches to a Decision, assumed-vs-realised. The one backward arrow in an otherwise linear process. This closes the loop the current-process map shows as permanently open.
- **Entity-world objects** — Company, Person, Fund, Deal. The Deal is not a folder; it is a *view over a question structure* plus lifecycle state.
- **Agent** — typed input, typed output, defined operations, an authority level. A procedure that can be held accountable, not "an AI that does things."
- **Policy** — the operation→authority table. Data, not code, so it can be audited before anything runs.
- **Event** — something changed (artifact arrived, assumption moved, term changed). Events are what trigger inference.

### Cross-check against the Manifesto's data taxonomy

The ontology must account for all five data categories, and it does:

| Category | Ontology home | Compounding behavior |
|---|---|---|
| 1. Inbound raw material | Artifacts | none (everyone has it) |
| 2. Methodology / templates | Question-decomposition templates, schema configs | weak, copyable — the 80/20 configurable layer |
| 3. Generated analysis | Derived claims | none — deliberately treated as exhaust |
| 4. Proprietary interaction data | Asserted/observed evidence from calls & meetings | compounds **if bound to questions** |
| 5. Judgment-and-outcome data | Decisions + Outcomes | compounds indefinitely, strengthens as models improve |

The system's moat is entirely in how well categories 4 and 5 are captured *as a byproduct of work* — which constrains Layer F: the capture surface must be where the work already happens, or it becomes a CRM (a field a human must maintain = death).

---

## 3. The substrate question (Layer C): Obsidian vs knowledge graph

**Resolution: this is not a choice between two options. It is one decision about semantics (the ontology is a typed graph — non-negotiable, from §2) and one decision about serialization (where the graph physically lives). Obsidian-flavored markdown is a serialization; a graph database is another. They can coexist, and at this stage they should.**

### Why markdown-as-canonical-store wins for phase 1

One file = one entity instance. YAML frontmatter = typed fields (entity type, state, epistemic type, authority). Wikilinks = typed edges. This gives, for free:

- **Human legibility** — a partner can open the decision record and read it. Trust in an audit trail requires legibility; a graph DB is opaque to the people whose judgment it records.
- **Provenance and temporality via git** — every assertion has an author, a timestamp, and a diff history. The audit requirement of Layer E falls out of the substrate instead of being built.
- **Local-first, nothing leaves the machine** — matches the confidentiality constraint absolutely. No SaaS, no sync, no third party.
- **Agent-native** — Claude/agents operate on files directly (read, grep, write). The contradiction agent needs no API layer to exist.
- **Ontology forced to stay explicit** — templates and frontmatter schemas *are* the ontology, versioned in the same repo. No schema hidden in a DB migration.
- **Obsidian the app becomes a free view layer** (Layer F): graph view, backlinks, dataview queries — projections for humans, at zero build cost.

### What markdown cannot do — and what to do about it

| Missing capability | Needed for | Resolution |
|---|---|---|
| Typed queries & traversal ("rank open questions by how much the structure depends on them") | Layer D inference | **Derived index**, rebuilt from the vault (SQLite or in-memory graph). Never authoritative — if it burns down, rebuild from files. |
| Event bus / push behavior | "The OS doesn't wait for the question" | Phase-1 substitute: agent runs *per session / per arrival* (new artifact lands → agent pass over the vault). A daemon is an optimization, not an architecture. |
| Multi-user concurrency | Firm-wide deployment | Git handles small-team async fine; real concurrency is a v2 problem, solved by promoting the index to authoritative *after* the ontology is validated. |
| Enforcement of the policy table | Layer E at scale | Phase 1: policy table as data + the agent harness's own permission system. Enforcement middleware comes with the daemon. |

**The migration path is the design:** vault-canonical now → vault + authoritative graph later, with markdown demoted to projection. The ontology (the actual IP) transfers unchanged because it was never entangled with the substrate. The worst mistake available today is the inverse path — building the graph DB first and discovering the ontology by migration.

### When to revisit

Trigger conditions, not dates: >1 concurrent editing user beyond you; >~10⁴ entities; inference passes that need sub-second traversal; or the first external deployment (which makes Layer E enforcement mandatory).

---

## 4. Perception and inference (Layers B & D) — the actual hard problems

- **Extraction is solved; binding is not.** Getting claims out of a deck or an Excel model is commodity LLM work. The hard problem is binding each claim to the question it bears on — that binding is what makes evidence retrievable "by what it bears on, not by keyword," and it is where the product either works or is a summarizer. Treat claim→question binding as the core AI problem of the project.
- **Contradiction is the first inference, deliberately.** It touches only internal artifacts (no external calls, no policy risk), it runs the day the structure exists, and it produces the demo moment: three irreconcilable numbers nobody had put side by side. It is also a pure test of the ontology — if the structure can't support contradiction detection, it can't support anything else.
- **Dependency ranking is the second.** "This verification decides the case; that expert call doesn't" requires holding all workstreams at once — the thing no human role can do and therefore the clearest value that isn't a faster analyst.
- **Push is a scheduling detail, not a capability.** Once inference runs on events, "push" is just running it when an event arrives. Do not build orchestration infrastructure before there is an inference worth orchestrating.

---

## 5. The one workflow demand (Layer F constraint)

The system asks for exactly **one structured input, ever**: twenty minutes at deal open, when the human states the thesis and corrects the proposed question decomposition. Everything else must enter by arriving somewhere the system was already watching.

This is the sharpest product constraint and it cuts both ways:

- It defines failure precisely: *if the system ever requires you to go update something, it has failed.*
- It concentrates all behavior-change risk into a single moment (deal open) and a single ritual (decision recording at IC). Design effort should be spent disproportionately on making those two moments obviously worth it, because they are the only two moments where the product asks instead of gives.

---

## 6. Build order

The OSPM draft's build order is correct, and it maps cleanly onto the vault-first substrate. Restated with substrate assignments:

1. **Ontology formalized** *(phase 0, implicit in the draft)* — entity schemas, frontmatter specs, question-state machine, evidence typology, templates. Pure design. This document's successor.
2. **Decision record** — no intelligence. Markdown template + capture ritual at the decision moment. "Ship it late and everything downstream starts late."
3. **Questions + typed evidence, one live deal** — the single-deal pilot from the Manifesto. The deal opens as a question structure; artifacts stay where they are; claims get extracted and bound.
4. **Contradiction agent** — internal artifacts only, autonomous under the policy table, runs over the vault.
5. **Policy table as data** — days of work, prerequisite for anything that answers to an LP.
6. **Retrieval across questions** — evidence reuse by question-type, the first compounding payoff.
7. **Same loop, other stages** — origination, ownership, exit are one mechanism pointed at different moments; not separate products.

Note what is absent from phases 1–6: event bus, daemon, web app, multi-user sync, external integrations. All real, all later, none load-bearing for validating the ontology on one live deal.

---

## 7. Open questions (the project's own question structure)

Held to the system's own standard — each will be `open` until evidence resolves it or it is explicitly `accepted-unresolved`:

- **Q1 — Binding accuracy:** can claim→question binding run reliably enough to be trusted unreviewed, or does it need a human-confirm step (and does that violate the no-maintenance principle)?
- **Q2 — Decomposition quality:** is a 20-minute human-corrected question decomposition actually sufficient structure for a whole deal, or does the tree need mid-deal restructuring (and who does it)?
- **Q3 — Ontology rigidity vs deal idiosyncrasy:** where exactly does the fixed core end and the per-firm Category-2 configurable layer begin?
- **Q4 — Excel round-trip:** reading models (cell→derived claim with derivation) is stated as a design principle; the write-back path is much harder and its necessity in phase 1 is unproven.
- **Q5 — Capture without friction for Category 4/5:** IC recordings and partner reasoning are the scarcest data; what capture surface gets them as byproduct rather than as homework?
