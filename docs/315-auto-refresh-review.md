# #315 automatic detail refresh and simplified headings

Implemented in the isolated `codex/315-review-followups` checkout based on `88f5c15`. The root checkout used for #369 review was not edited.

## Changes

- Home retains every active official/custom card, type badge, accessible region, existing navigation and error/retry UI. Redundant group count headings are removed.
- Detail participation targets are always visible, with wrapping names and a static count. The normal manual refresh button is removed.
- Detail subscribes to shared custom-progress invalidation, window focus, and return to visible document state. Existing data stays on screen during refresh and recoverable background errors; errors expose a retry action.
- Identity resets are independent from background reads. Pending focus/visibility events reuse the active read; invalidations coalesce into one newer read, and invalidated responses cannot update the page.
- Read results require matching component/identity, request sequence and authentication generation. Cleanup removes all three listeners.
- Cancellation advances the read generation, suppresses automatic reads while pending, and discards queued reads from before cancellation. A failed cancellation can service invalidations deferred during the request. The cancellation dialog is not reset by refreshes.
- Existing calendar props and key remain unchanged. Calendar redesign belongs to the separate calendar change.

## Verification

Used WSL Node `v22.23.1`, bundled Chromium, port `44417`, and `VITE_API_PROXY_TARGET=http://127.0.0.1:9`. API fixtures match URL pathnames beginning `/api/`, so SPA navigation reaches Vite and no unhandled API can reach a live backend.

```bash
export PATH=/home/sdh080200/.nvm/versions/node/v22.23.1/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd /mnt/c/dev/AH_05_05/.codex-work/315-review-followups/frontend
VITE_API_PROXY_TARGET=http://127.0.0.1:9 VITE_USE_MOCK=false PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44417 node node_modules/playwright/cli.js test tests/e2e/315-auto-refresh.spec.ts --output=test-results-315-auto-refresh-final
```

Final result: **6 passed (1.1m), exit 0**. Coverage includes medication and supplement invalidation/focus/visibility updates; always-visible wrapped targets; no normal manual-refresh button; initial retry; background failure without skeleton/content loss; pending invalidation coalescing; cancellation with a stale GET and a pre-cancel queued invalidation; and all Home cards/badges without repeated headings.

The original six cases failed before implementation (`test-results-315-auto-refresh-red`). A stronger cancellation check subsequently reproduced a real race: a queued GET restored the ACTIVE state after successful cancellation (`test-results-315-auto-refresh-cancel-queue-red-retry`, with trace). The generation-bound queue fix made that test pass in the final run.

An intermediate run had five passes and one initial page-load timeout. Another single-case attempt timed out before content appeared. The final run used the suite's existing 60-second timeout convention and started after the calendar runner stopped. The final Vite output included two refused requests to the deliberately unreachable proxy during browser teardown; no live backend was contacted.

TypeScript `tsc --noEmit` and scoped `git diff --check` passed. No backend, schema, recording writes, polling, existing test files, root branch switch, commit or push was performed. Account-generation checks were reviewed in code; this new six-case file does not exercise a complete account-switch UI flow.

The TDD and verification skills guided the failing-regression/fix checks. Frontend design guidance was applied within the approved existing design: preserve cards and typography, remove repeated labels, and expose essential target content directly.
