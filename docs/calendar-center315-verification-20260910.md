# Centered custom-challenge date strip

Scope: `codex/calendar-center315`, based on `feature/315` at `3d1d0e796fd675a5c015dd097f59e47f6d43d41a`. The root review checkout was not edited or switched. No API, ParticipationPage, package, or global style changes.

## Approved behavior

- Today is initially centered, including before/after the challenge period and cancelled/history views. Visible date bounds include today and server occurrence bounds, without generating goal records.
- Native horizontal scroll-snap chooses the nearest center date during scrolling. The date heading, completion count, and all actual records for that day update together. Clicking, arrow keys, Home/End, and the existing record-card swipe navigate the same strip.
- Blank 32px rounded squares sit in 44px focusable buttons. Only a nonempty day whose actual occurrences are all completed gets the primary teal fill. Selection scales the inner square to 1.18, independently of completion. Reduced motion removes the 220ms transition and smooth programmatic scrolling.
- Leading/trailing spacers center the first and last dates exactly. Native vertical scrolling remains available. Same-status API refresh preserves the viewed day; viewport resize re-centers it without resetting selection.

## Verification

TDD baseline: the new initial-center acceptance test failed against the old component, with a measured 55.5px center error (required less than 1px), before production edits.

Runtime: WSL Node 22.23.1, Chromium, dedicated port 44429. `VITE_USE_MOCK=false`, `VITE_API_BASE_URL=/api`, proxy `http://127.0.0.1:9`. New fixture routing matches API URL pathnames only. This tests the real frontend API path against deterministic isolated responses, not a live backend or mock-mode fixtures. Existing regression fixtures emit harmless refused proxy requests for unstubbed badge media/background reads; the new calendar fixture rejects and asserts every unexpected API request.

Private ignored configuration: `frontend/test-results/calendar-center.config.ts` and `calendar-center.vite.config.ts`. Vite cache: `test-results/node_modules/.vite-calendar-center-e2e-real`, separated from production mode and other workers. Root dependencies are reused through the isolated worktree's node_modules symlink without root writes.

Commands run from the isolated frontend with the environment above:

```sh
node node_modules/playwright/cli.js test --config test-results/calendar-center.config.ts tests/e2e/315-date-strip.spec.ts --workers=1 --output=test-results/calendar-center-verified
node node_modules/playwright/cli.js test --config test-results/calendar-center.config.ts tests/e2e/315-custom-challenges-api.spec.ts tests/e2e/315-auto-refresh.spec.ts tests/e2e/315-challenge-layout.spec.ts --workers=2 --output=test-results/calendar-center-regression
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build --config test-results/calendar-center.vite.config.ts
```

Final date-strip acceptance suite: **21 passed**. Existing API/refresh/layout regression suite: **45 passed**, for **66 total passing tests**. TypeScript and production build passed; Vite retains the existing large-chunk warning. Independent read-only review found no actionable issues in scroll feedback, exact edge geometry, resize, refresh preservation, record ownership, or read-only navigation.

Acceptance coverage includes initial/edge geometry, keyboard focus, real CDP touch while the finger is still down, both horizontal directions, native vertical touch on cards and strip, zero/one/multiple/seven records, bedtime, variable day counts, cancelled/history, today outside bounds, completion-vs-selection fill, reduced motion, same-status server refresh, resize, long names at 320/390/1280px, and absence of navigation writes.

## Actual captures

Under `frontend/test-results/calendar-center-verified/315-date-strip-native-stri-2b618-s-before-release-then-snaps/`:

- `today-before-scroll.png`: centered today and two actual records.
- `during-scroll-records.png`: date and four actual records updated before touch release.
- `last-empty-day-centered.png`: last date centered with zero real records.
- `video.webm`: actual Chromium interaction recording, not a generated animation.

Width captures are in the same output root's `315-date-strip-date-strip-*` folders. Chromium touch emulation was verified; physical iOS/Safari and Android devices were not tested. All screenshots/videos and runner configuration stay ignored and are not included in the commit.
