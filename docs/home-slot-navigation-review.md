# Home time-slot navigation

The medication and supplement home sections now offer tabs for their actual scheduled time slots. A horizontal swipe across the card changes the selected slot. A single scheduled slot has no redundant navigation, and empty-state behavior is unchanged.

The existing initial selection is retained: the closest scheduled time at or before the current time, falling back to the first scheduled slot. Slots retain the existing schedule-time ordering. Only the selected card is visible or accessible. Inactive cards stay mounted so their selections and pending saves remain attached to the original records and slot.

The shared `TimeSlotNavigator` handles navigation only. It has no API calls and adds no animation dependency or transition. A horizontal gesture needs at least 48 CSS pixels and must exceed vertical movement by a factor of 1.5. Native vertical scrolling remains available through `touch-action: pan-y`. A drag beginning on a dose action cannot trigger that action's click. Tabs support left/right arrows, Home/End, visible focus, and a focusable associated panel.

Medication selection, memo, completion, undo, collapsed prescriptions, and inner medication expansion retain their existing implementation. In particular, recording all medications still includes prescriptions outside the two visible rows. Supplement selection, completion, undo, failure/retry, and API ownership retain their existing implementation.

## Verification

Final local verification on 2026-09-10: 33 browser tests passed and one mock-only account-isolation test was skipped in real-fixture mode. All 10 new navigation tests passed. `npm run build` passed with Vite's existing large-chunk warning. `git diff --check` passed.

`frontend/tests/e2e/home-slot-swipe.spec.ts` covers both categories: scheduled-only tabs, skipped slots, single-slot navigation, keyboard access, swipe boundaries, ignored vertical gestures, zero API calls on navigation, per-slot selection/completion/undo, collapsed medication inclusion, pending saves during navigation, native Chromium touch and vertical scrolling, and screenshots at 320, 390, and 1280 pixels.

Run with the existing Node 22 runtime and dependencies:

```sh
VITE_USE_MOCK=false VITE_API_PROXY_TARGET=http://127.0.0.1:9 \
PLAYWRIGHT_TEST_PORT=44418 PLAYWRIGHT_CHANNEL=chromium \
node node_modules/playwright/cli.js test \
  tests/e2e/home-slot-swipe.spec.ts \
  tests/e2e/home-medication-compression.spec.ts \
  tests/e2e/home-supplement-doses.spec.ts --workers=1
npm run build
```

The new tests intercept only `/api/` pathnames, leaving application modules intact. All writes use isolated browser fixtures; the proxy points to a closed local port. This verifies frontend behavior, not live backend persistence or a physical mobile browser. Chromium's native touch-event emulation verifies scrolling and click suppression. Existing broad regression fixtures may log refused requests for unrelated challenge data against the intentionally closed proxy.

Integration note: this branch starts from main `8aedd44`. It adds wrappers around the two home cards and the shared navigator; it does not remove the inner medication expansion being changed separately in feature 391, or alter feature 369's visual work.
