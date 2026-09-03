# Start PANTA in Codex — exact workflow

## 1. Create the local repo
Unzip this package into a folder named, for example:

`PANTA_PRODUCT_LAB`

Open a terminal in that folder and run:

```bash
git init
git add .
git commit -m "Initialize PANTA product lab"
npm ci
npm run check:all
```

If all checks pass, the repo is ready.

## 2. Open the folder in the Codex desktop app
Open Codex and select this local repository/folder.
Codex should automatically read the root `AGENTS.md` instructions.

### First Codex message
Paste this exactly:

> Read `AGENTS.md`, `docs/15_TARGET_CONTRACT_MANIFEST.md`, `docs/14_KERNEL_ALIGNMENT.md`, and all files in `docs/product/`. Do not change any code yet. Run `npm run check:all`, explain the product architecture to me in plain English, confirm the fixture-free production boundary, and tell me the exact command to launch the synthetic product lab.

Do not ask Codex to redesign anything in the first task.

## 3. Launch the product lab
In a terminal:

```bash
npm run lab
```

Open the URL Vite prints. Use the browser product as the design environment.

Useful routes:
- `#/deal`
- `#/workstream`
- `#/trace`
- `#/simulate`
- `#/review`
- `#/resolve`
- `#/formation`
- `#/replay`
- `#/outputs`

## 4. Give product feedback, not implementation instructions
Good request:

> On Deal Home, I do not understand quickly enough what has changed since my last review. Keep the room's job and the PANTA visual system. Explore the smallest interaction/composition change that solves this. Do not alter kernel contracts or add case facts. Implement it in an isolated worktree, run `npm run check:all`, and show me the user-visible change and diff.

Bad request:

> Make this prettier and add some cards.

Always explain the investor problem first.

## 5. One meaningful change per task/worktree
Use Codex worktrees for alternatives or risky changes. Review the diff before merging.

For visual changes, attach a screenshot if useful and point to the exact region. Example:

> The selected reading has too much visual weight and the evidence area feels mechanically boxed. Preserve the underlying interaction and rebalance composition only.

## 6. Review every change in two ways
### Product review
Run the product and ask:
- Is the investor's next action obvious?
- Is the important truth visually dominant?
- Does this room feel different because its job is different?
- Does any copy sound like backend/ontology language?
- Did we add complexity without increasing clarity?

### Engineering review
Run:

```bash
npm run check:all
```

Codex must tell you what it changed, tests run, and backend dependencies.

## 7. Accept or reject
If accepted:

```bash
git add .
git commit -m "Describe the product improvement"
```

If rejected, discard the worktree/branch. Do not keep half-accepted visual experiments in `main`.

## 8. Larger checkpoint reviews
After several accepted changes, ask Codex for:

> Review the complete product across all rooms for cross-product UX drift, duplicated primitives, inconsistent investor language, visual-system violations, dead interactions, and deviations from the kernel/frontend contracts. Do not change code yet. Rank issues by product impact.

Then fix the highest-impact issues one at a time.
