# Chat UI #390

The existing chat flow now renders completed assistant messages with the installed `react-markdown` and `remark-gfm` dependencies. User messages remain plain text. Raw HTML and images are excluded; only absolute HTTP(S) links are actionable, and external links use `noopener noreferrer`. Tables and code blocks scroll within the message bubble at 320 px, 375 px and desktop widths. The existing `/images/rxvita-mark-128.png` chat profile image is unchanged.

The composer displays `이 답변은 AI가 생성한 답변입니다` below the input after an assistant answer exists, including restored history. Pending progress, final SSE completion, sources, feedback, history and account isolation retain their existing flow. Chat screens retain the navigation bar with no falsely selected tab; its former chat entry is now the challenge tab at `/challenges`.

`ChatLauncher` wraps routes globally, including registration, schedule, report, profile, legal and challenge detail routes that do not all use the tab bar. It uses the existing app width, primary color and dialog component. Bottom scroll space keeps final actions reachable above the floating button; tab-bar and safe-area offsets are included. The button is temporarily hidden while a dialog/sheet or an input is active.

Deliberate route exceptions are `/chat` and its development previews (already in chat), `/` and `/tutorial` (first-run entry), `/login` (authentication entry), and `/dev/gallery` (component gallery). All other application routes receive the launcher. Authenticated sessions open `/chat`; guests receive the existing login prompt and login flow. Development previews do not give the launcher an authentication bypass. The router's existing authentication guard remains in place.

Validation uses WSL Node 22.23.1 and direct Node CLIs because the environment's pnpm script hook retried dependency installation after DrvFS rename errors. No package or lockfile changes were needed. New behavior tests were observed failing before implementation; the baseline start-guide suite passed. Test-only official-challenge responses prevent a live API 401 from invalidating mock chat sessions, and external fonts are blocked in the focused fixture to keep network availability out of the assertions.

Useful commands (from `frontend`, Node 22 on PATH):

```sh
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build
PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44190 node node_modules/playwright/cli.js test tests/e2e/chat-feature-390.spec.ts tests/e2e/chat-session-flow.spec.ts --workers=1 --timeout=120000
VITE_USE_MOCK=false PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44190 node node_modules/playwright/cli.js test tests/e2e/chat-sse-flow.spec.ts --workers=1 --timeout=120000
```

All four new behavior cases and sixteen existing chat-session cases passed across the final focused runs; the first Markdown case required a separate rerun after a cold Vite start exceeded 60 seconds. The existing start guide (4), source/feedback UI (6), feedback (3), and account-isolation (2) cases also passed. The intercepted SSE completion regression passed in real-API frontend mode. Final `tsc -b`, Vite build and `git diff --check` passed.

Immediately before the local commit, `tsc -b` and Vite build passed again. The four new behavior cases and sixteen chat-session regressions passed together (20 passed, 2.8m) with `VITE_USE_MOCK=true`, port `44490`, Chromium and one worker. Local results are preserved under `frontend/test-results-390-commit-verification/` and excluded from the commit.

The broader `entry-home-auth.spec.ts` run had two unrelated failures at lines 327 and 371 (expanded medication details missing). Both were reproduced with the same assertions against an untouched archive of `8aedd440c64ca6c97b5296e763a8bdb258d24aab`; the diagnostic harness only blocked remote fonts and allowed time for a cold compilation. Medication behavior was not changed for this task.

Screenshots are retained locally under `frontend/test-results/issue390/`: `chat-markdown-320.png`, `chat-markdown-375.png`, `chat-markdown-1280.png`, `floating-home-375.png`, `floating-home-1280.png`, and `floating-upload-mobile.png`. They show the existing narrow app frame on desktop as well as mobile layouts; #369 owns the separate responsiveness change.

The production build reports a large JavaScript chunk warning. Actual backend answer quality and physical-device keyboard/safe-area behavior are outside the local mocked browser checks.

Integration with the separate #369 responsiveness branch needs deliberate review of `router.tsx`, `styles/index.css`, `BottomTabbar.tsx`, `ChatPage.tsx`, `ChatSessionList.tsx` and `ChallengeLayout.tsx`, especially app-width, safe-area and scroll-space rules. No #369 changes were merged here.
