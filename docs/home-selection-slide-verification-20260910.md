# Home selection indicator motion

Base: actual `feature/369` at `23f28e87c4c50a2ed9a88841828080b1b6c80214`.
Branch/worktree: `codex/home-selection369`, `.codex-work/home-selection369`.

## Approved behavior

Medication and supplement rows share `DoseSelectionIndicator`. An unselected row reserves no horizontal space for the hidden mark. Clicking its main text area selects the existing row button, reveals the same 24px selected circle, and opens a 36px mark/gutter area from the left. Text moves right with that area. Deselecting reverses the movement. The local width, opacity and translate transitions last 220ms without bounce; reduced-motion users get immediate state changes.

The existing button owns `aria-pressed`, keyboard activation, 44px-or-larger hit area and disabled state. The indicator is visual and `aria-hidden`, with no nested input or extra focus stop. Existing medication/supplement selection sets, completed badges, API calls, completion/undo, retry, pending state, collapsed-prescription actions, memo and scheduled-slot navigation are unchanged. Medication disclosure arrows remain separate sibling buttons and their implementation is untouched.

This is a small custom composition of the application's existing selectable-row control and layout motion. It is not claimed to be an exact imported Watermelon component or a verified matching source component.

## Verification

Final verification: the dedicated selection/motion suite passed all 12 tests. Existing API-fixture home coverage passed 33 applicable tests (12 medication compression, 10 slot navigation, 11 supplement dose cases); the mock-only account case skipped in API mode then passed in the separate mock run. All 15 mock clay/responsive/account checks passed. Fresh typecheck and production build passed, with only Vite's existing large-chunk warning. `git diff --check` passed.

The new behavior test first failed on the unchanged implementation: the unselected medication name started 36px to the right of its expected text origin because the always-visible mark occupied space.

The dedicated test file covers both types: hidden/selected/deselected layout, actual intermediate animation width and 200–250ms timing, keyboard toggling, no selection writes, pending save and failed retry, completion versus selection, undo, long names at 320/390/1280, immediate reduced motion, native Chromium horizontal touch starting on row text, native vertical scrolling, separate medication disclosure, and actual video/frame capture.

Existing home timeline tests also verify boundary swipes, keyboard time-slot tabs, pending saves across slots, collapsed prescriptions, all-complete behavior, and dose ownership. One old supplement geometry test was updated to wait for the indicator's exit transition to finish before comparing positions measured in separate browser frames. Its obsolete “always visible” title now describes the requested selected-only display.

All tests used the isolated API pathname boundary or existing mock fixtures, with `VITE_API_BASE_URL=/api` and a closed local proxy at `http://127.0.0.1:9`. Port 44423 was reserved for this task. API and mock runs used separate caches under `frontend/test-results/node_modules/.vite-home-selection-{e2e-real,e2e-mock}`. No live backend or database was used. Native Chromium touch emulation was tested; physical phones were not.

Local runner configurations are retained in the ignored `frontend/test-results/home-selection.{config,vite.config}.ts` files.

## Review artifacts

`frontend/test-results/selection-motion-final/home-selection-slide-selec-c70a3-supplement-selection-motion/` contains the actual browser `video.webm` and medication/supplement `before`, `selected`, and `deselected` PNG sequences.

The main selection test directories also contain full-screen before/selected/deselected screenshots. The broader home-slot suite produced both medication and supplement screenshots at 320/390/1280 under `frontend/test-results/selection-final-api/`.

No changes were made to the active root feature315 review, shared global button/card styles, packages, or arrow/disclosure ownership. This branch is for selective integration by the parent task; it does not merge or push a feature branch.
