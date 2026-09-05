# Codex Prompt Patterns for PANTA

## A. Small visual/composition change
> User problem: [plain-English investor problem]. On [room], [what feels wrong]. Preserve the underlying product logic, kernel/adapter contracts, PANTA visual system, and all unrelated interactions. Implement the smallest composition/interaction change that solves it. Do not add case facts or generic cards. Run `npm run check:all`. Summarize the user-visible change and diff.

## B. Interaction change
> In [room], I want the user to be able to [action]. First inspect the existing action/event/adapter contracts and tell me whether the backend boundary already supports it. If yes, implement it without changing the contract. If not, stop before changing ontology and propose the smallest explicit contract extension. Do not fake the behavior.

## C. Cross-product UX audit
> Review every PANTA room in the running lab. Do not change code. Find cross-product drift in shell, language, Object Lens, controls, status treatment, typography, spacing and motion. Separately identify places where screens are too visually similar despite different mental tasks. Rank issues by user impact and recommend the smallest fixes.

## D. Proactive companion improvement
> Identify one place where PANTA could reduce investor work by surfacing a meaningful already-computed result in context. Do not add an inbox, chatbot or agent console. Propose how the existing room can surface it naturally. Do not implement until the proposal respects authority and auditability.

## E. Outputs improvement
> Treat the artifact as a live writable projection of the case. The user must be able to write, sync, inspect, traverse, Trace/Simulate/Resolve, and see case-driven diffs. Do not turn this into an AI writing app or permanent assistant sidebar.

## F. Product simplification
> Find UI copy/components on [room] that explain the interface instead of helping the investor think. Remove or simplify them without losing needed state/authority information. Run visual/product checks afterward.
