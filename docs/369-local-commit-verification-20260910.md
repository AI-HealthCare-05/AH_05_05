# Feature 369 local commit verification

This local commit packages the existing approved light-clay token, shared-control motion, home/chat surface, badge-award, and responsive layout changes together. The global token and consumer changes are coupled, so they are kept in one coherent commit. Packaging introduced no new product changes.

Fresh verification on 2026-09-10, Node 22.23.1 and Linux Chromium:

- TypeScript `tsc --noEmit` and `tsc -b`: passed.
- Vite production build: passed; the existing large bundle warning remains.
- Mock UI gate: 31 passed across the five `369-*` suites, including 320, 390, 768, 1280 and 1440px responsiveness, reduced motion, loading, focus return, and selection/completion state.
- HTTP fixture gate: 3 passed for newly awarded badge readiness/one-time rotation, water-only contour selection, and report-loading duplicate-request prevention.
- Staged whitespace check and absence of unstaged tracked dependencies: passed.

The initial mock run passed 30 tests and timed out in the first chat test's `page.goto` before any interaction. An unchanged complete rerun passed all 31. The original failed artifact is preserved and is not described as a passing run. The observed first-load-only pattern is consistent with the cold Vite startup delays already recorded in this worktree; no source or timeout adjustment was made.

Browser tests used port 44469 and `VITE_API_PROXY_TARGET=http://127.0.0.1:9`; unmatched requests could not reach the user's backend. The badge lifecycle test fulfilled the tracked original PNG. The CSS-only contour selection test emitted one refused media request because the backend proxy was disabled, so that test is not evidence of live media delivery. Historical media and visual comparison evidence remains in the earlier reports and local capture folders.

The commit includes reviewed source, all three new runtime CSS files, the two control-harness files, focused tests, and text reports. Generated builds, screenshots, test outputs, galleries, caches, environment files, and preview helpers remain outside the commit and are preserved. Earlier reports describe historical checkpoints; this report records the fresh packaging gate. The root checkout stays on `feature/315`. Only this feature worktree is detached at the resulting commit to make the branch available for manual switching. No push or merge is performed.
