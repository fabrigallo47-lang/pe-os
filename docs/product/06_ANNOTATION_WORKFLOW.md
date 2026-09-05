# Screenshot / Annotation Workflow

When something feels wrong while using the lab:

1. Capture the screen.
2. Put the screenshot in `product-notes/screenshots/` with a simple name such as:
   `2026-09-03-deal-home-attention-hierarchy.png`
3. Create a note in `product-notes/` using `NOTE_TEMPLATE.md`.
4. Tell Codex the user problem, not the CSS solution.
5. Point Codex to the screenshot/note and ask it to inspect the running room and source.
6. Ask for an isolated worktree and `npm run check:all`.
7. Review the running result before accepting the diff.

Screenshots are evidence of a UX problem; they are not the design source of truth.
