# #315 date strip review

Implemented in `codex/315-review-followups`, based on `88f5c15`, isolated from the root checkout used to review #369. Calendar scope is `frontend/src/pages/challenges/CustomChallengeCalendar.tsx` and the new `frontend/tests/e2e/315-date-strip.spec.ts`.

## Design and behavior

- Replaced the month grid and collapsed record disclosure with a horizontally scrollable date strip and immediately visible occurrence cards.
- The selected month/day is prominent with an explicit today label. The selected pill is deep teal; the completion panel is mint. Existing semantic tokens supply white `#ffffff`, mint `#ddf4f1`, teal `#077a74`, text `#202525`, muted text `#596462`, and border `#e1e7e6`. Existing Noto Sans KR/system font stays consistent, with a 24px selected date, 14px record slot, and 13px supporting labels. No new fonts, dependency, or global CSS.
- Cards use actual server occurrence counts, including repeated slots across multiple targets, and wrap long names. Completed records have a filled check circle; pending records have an empty noninteractive circle with text state. There are no record mutation controls or API calls.
- A nonempty selected day whose records are all completed receives an inline circle-check celebration. Copy distinguishes medication/supplement and today/past date. Future and empty dates cannot produce completion celebrations.
- Dates cover Seoul joined date through `actualEndDate`, falling back to the final occurrence only when no actual end is returned. Empty dates inside the period remain selectable. Active records initially select today clamped to the period; terminal records initially select the actual end.
- Native scrolling is used for the date strip. Record-area touch/pen swipes navigate one day in either direction after a 48px horizontal movement with clear horizontal intent. Native vertical pan is preserved; cancellation and nonprimary touches clear the gesture. Buttons and ArrowLeft/ArrowRight/Home/End provide keyboard navigation with roving focus, pressed/current labels, and disabled boundary controls.
- Selecting a day scrolls only the strip, avoiding page movement away from the records. Completion stays inline and does not block controls.

## Verification

The new regression test was run before production edits and failed as expected because the old grid lacked the selected-date heading. Following implementation, the first 13 tests passed in 54.2 seconds. `tsc -b --pretty false` passed. Two additional checks then passed in 31.0 seconds: trusted browser touch events changed dates in both directions while a real vertical drag scrolled the page; active initial selection correctly clamped before/after the period. The final combined run passed all 15 tests in 50.1 seconds. `git diff --check` passed for the calendar. The runner exited and port 44416 was confirmed closed before handing browser verification to the other frontend agent.

Coverage includes 1/2/3/4/7 actual records, both medication and supplement, readonly request guards, complete/empty/future days, terminal and active initial selection, Seoul date rollover, gaps through the actual end, swipe directions and boundaries, ignored vertical/cancelled gestures, keyboard focus/scrolling, and 320/390/1280px native overflow containment. API fixtures intercept only actual `/api/` pathnames so source modules remain loadable; unmatched API requests are recorded and rejected. The backend proxy is set to `http://127.0.0.1:9` throughout.

The 320px screenshot was visually inspected: the selected date remains clear, long record names wrap within cards, status circles do not shrink, and the page has no horizontal overflow. Screenshot artifacts are generated under the isolated frontend `test-results` directory. The initial calendar subtask left existing suites untouched; the subsequent authorized integration updated their obsolete UI expectations and passed all 67 cases, as recorded in `315-followups-integration-review.md`.

Reproduction from the isolated frontend in WSL with existing Node 22 dependencies:

```sh
VITE_USE_MOCK=false VITE_API_PROXY_TARGET=http://127.0.0.1:9 PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44416 node node_modules/playwright/cli.js test tests/e2e/315-date-strip.spec.ts --workers=1
node node_modules/typescript/bin/tsc -b --pretty false
```
