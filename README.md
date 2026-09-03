# PANTA Product Lab

This is the canonical local frontend repository for evolving PANTA as a real product.

## What lives here
- `src/` — production frontend. Fixture-free. Never put real-deal/demo content here.
- `docs/` — technical/kernel/frontend contracts.
- `docs/product/` — product doctrine and UX guidance for humans and Codex.
- `tests/` — reproducible synthetic contract/behavior tests.
- `lab/` — development-only browser harness using synthetic data. It imports the real production UI but keeps fixtures outside `src/`.
- `product-notes/` — your screenshots, observations, and temporary product notes.

## First setup
Requires Node 22+ and Git.

```bash
npm ci
npm run check:all
```

## Run the real frontend with an empty backend
```bash
npm run dev
```

This is the production frontend and therefore shows honest empty/runtime states until a backend adapter supplies a case.

## Run the interactive synthetic product lab
```bash
npm run lab
```

Open the local URL Vite prints (normally `http://localhost:5174`).
The synthetic adapter lives outside production `src/` and is for product/UX development only.

## Recommended product loop
1. Run `npm run lab`.
2. Use PANTA like an investor rather than inspecting code.
3. Capture the exact friction/opportunity in `product-notes/` or attach a screenshot to a Codex task.
4. Ask Codex to implement one focused change in an isolated worktree.
5. Review the running result and the diff.
6. Run `npm run check:all`.
7. Merge only if the product is better and the doctrine/contracts remain intact.

Start with `CODEX_START_HERE.md`.
