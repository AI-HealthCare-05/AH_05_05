# #315 review followups: integration verification

Date: 2026-09-10. Base: `88f5c15`. Branch: `codex/315-review-followups`. Root checkout and its #369 review state were not changed.

## Included changes

- Horizontal, native-scrolling calendar date strip; immediately visible server occurrence cards; actual dynamic counts and read-only check/pending circles.
- Inline completion feedback for nonempty completed medication/supplement days, with future dates excluded. Seoul participation boundaries, actual final date, and target-zero behavior retained.
- Record-area horizontal touch swipes, preserved vertical scrolling, keyboard date navigation and accessible button/state labels.
- Always-visible participation targets, removal of redundant Home group count headings and the normal manual refresh action.
- Detail refresh on record invalidation, focus and return to visible state, preserving content during background reads/errors. Identity, authentication and request-generation guards prevent stale responses, including the cancellation/queued-invalidation race.
- Existing #315 tests adapted from obsolete month-grid/record-accordion/target-accordion/Home-heading expectations to the approved UI. They still verify server-derived values, selected-day-only records, future/empty dates, boundary navigation, all Home cards, errors/retries, cancellation, badge snapshots, account/route changes, and medication/supplement recording integration. Join-page disclosure behavior remains tested.

## Combined verification

**67 passed (1.7 minutes), exit 0**, single worker, Chromium, Node 22.23.1:

| Suite | Cases |
| --- | ---: |
| `315-custom-challenges-api.spec.ts` | 36 |
| `315-challenge-layout.spec.ts` | 3 |
| `315-home-custom-progress.spec.ts` | 7 |
| `315-auto-refresh.spec.ts` | 6 |
| `315-date-strip.spec.ts` | 15 |

The 21 new cases include 1/2/3/4/7 occurrence counts, both challenge types, completion/empty/future days, cancelled and active date initialization, Seoul date rollover, long-name layouts at 320/390/1280px, keyboard focus and strip visibility, and real trusted browser touch events proving both horizontal date changes and actual vertical page scrolling. Refresh tests exercise pending-read invalidation, initial/background errors, retry, focus/visibility, and cancellation with a queued stale response.

TypeScript `tsc -b --pretty false` passed. Production Vite build passed: 2,333 modules, 37.87 seconds. The existing large-bundle advisory remains (main JS approximately 910.54 kB); it is not introduced by a new dependency. `git diff --check` passed.

The run used an ignored local config under `frontend/.codex-work/`, with a unique Vite cache and port 44416. Its single `webServer` object replaced the base configuration rather than concatenating server arrays. Test and build proxy targets were hardwired to `http://127.0.0.1:9`. API fixtures match URL pathnames, with unmatched requests rejected. Some fixture badge images and teardown refresh requests logged expected connection refusals to that unreachable proxy. No live backend or database was contacted. The cache outside `node_modules` also emitted a non-failing Babel large-file advisory; dependencies were not shared with another running Vite instance during this integration run.

Command, from the isolated frontend (temporary config supplies only the private cache/proxy/server/output overrides):

```sh
VITE_USE_MOCK=false VITE_API_PROXY_TARGET=http://127.0.0.1:9 PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44416 node node_modules/playwright/cli.js test --config .codex-work/315-integration.playwright.ts tests/e2e/315-custom-challenges-api.spec.ts tests/e2e/315-challenge-layout.spec.ts tests/e2e/315-home-custom-progress.spec.ts tests/e2e/315-auto-refresh.spec.ts tests/e2e/315-date-strip.spec.ts --workers=1
node node_modules/typescript/bin/tsc -b --pretty false
VITE_USE_MOCK=false VITE_API_PROXY_TARGET=http://127.0.0.1:9 node node_modules/vite/bin/vite.js build --config .codex-work/315-integration.vite.ts
```

The integration owner reviewed the combined production diff; the refresh author also rechecked identity/listener/cancellation guards and reported no concrete blocker. These checks cover the #315 frontend followups only. Backend, database, deployment and unrelated UI work are outside this package. The remaining handoff is user review of the completed feature branch; no implementation or test failure is left open here.
