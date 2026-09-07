# Challenge #281 — Task C report

## Outcome

- Added the badge catalog, badge detail, reusable badge artwork, earned/unearned presentation, and an actionable empty state.
- Added Home challenge summaries for active linked routines, including an independent summary when no medication exists and a dedicated empty-state preview. Home exposes navigation only; it has no challenge `했어요` action.
- Added a subtle visible `예시 데이터` label to both populated and empty Home challenge summaries so the local mock state is not mistaken for live data.
- Added the MyPage `챌린지 기록` entry without changing the existing medication, supplement, visit, notification, or account settings behavior.
- Registered all production and `/dev/challenges` routes under one local `ChallengeMockProvider`; challenge routes are authentication-free and contain no API wiring.
- Added DevGallery links and dedicated dev previews for empty badges, empty tailored recommendations, and empty Home challenge state.

## Figma design contexts read

- File `3qUR2z0rh6aYJfeJSxiUmg`
- `725:32` — I-11 내 배지
- `725:35` — I-12 배지 / 상세
- `757:1188` — I-02 홈 / 참여 중
- `757:1128` — I-01 홈 / 참여 전
- `769:1116` — I-16 마이페이지 / 진입
- `771:1106` — GO/challenges / 챌린지 기록

The implementation reuses the existing RxVita Tailwind tokens, shared mobile shell, and local challenge state. The generated PNG badge artwork supplied by the controller is rendered through `ChallengeBadgeArt`; no remote or expiring Figma asset URL is used.

## Exact Task C modified paths

- `frontend/src/pages/challenges/ChallengeBadgeArt.tsx`
- `frontend/src/pages/challenges/ChallengeBadgesPage.tsx`
- `frontend/src/pages/challenges/ChallengeBadgePage.tsx`
- `frontend/src/pages/challenges/HomeChallengeSummary.tsx`
- `frontend/src/app/router.tsx`
- `frontend/src/pages/home/HomePage.tsx`
- `frontend/src/pages/my/MyPage.tsx`
- `frontend/src/app/DevGallery.tsx`
- `frontend/tests/e2e/challenges-entry-badges.spec.ts`
- `frontend/tests/e2e/home-figma-overhaul.spec.ts` (only the obsolete challenge placeholder assertion was replaced)
- `docs/superpowers/plans/281-C-report.md`

Controller-owned artwork consumed by Task C, but not created/modified by this worker:

- `frontend/public/images/challenges/badge-walk.png`
- `frontend/public/images/challenges/badge-medication.png`
- `frontend/public/images/challenges/badge-supplement.png`
- `frontend/public/images/challenges/badge-review.png`

## TDD and verification

All commands ran only in WSL with Node `v22.23.1` and `pnpm`; no Windows test/build and no dependency install/reinstall was performed.

RED evidence:

- Initial route/badge/Home/My tests failed because challenge routes and UI did not exist.
- Home-without-medication test failed because the prior render condition required medication and dose records.
- Official unearned badge detail test failed because official classification did not yet derive from the linked definition.
- Badge artwork test failed with `Expected: 6, Received: 0` images before `ChallengeBadgeArt` was implemented.

Fresh GREEN verification:

```text
pnpm exec tsc --noEmit
PASS (exit 0)

PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44283 \
  pnpm exec playwright test tests/e2e/challenges-entry-badges.spec.ts \
  --workers=1 --output=test-results-281-C --reporter=line
PASS: 7 passed (22.0s)

pnpm exec vite build
PASS: 2045 modules transformed, built in 30.36s (exit 0)
```

Final review follow-up after adding the Home mock indicator:

```text
pnpm exec tsc --noEmit
PASS (exit 0)

PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44283 \
  pnpm exec playwright test tests/e2e/home-figma-overhaul.spec.ts \
  -g "챌린지 요약 이동" --workers=1 --timeout=20000
PASS: 1 passed (16.2s, exit 0)
```

## Concerns / follow-up

- Vite reports the existing advisory that the main JS chunk is larger than 500 kB; the build succeeds. Code splitting was outside this scoped task.
- Cold, isolated Playwright runs using the repository-wide 10-second timeout can spend the full timeout in the first Vite transform. The Task C spec uses 20 seconds; its final seven-test run is green. A prior two-test regression invocation hit this cold-start timeout before assertions, while the same MyPage regression passed when it reached the page.
- The latest product decision is to show all badges without filters. The static `전체 / 기본 / 공식` filter-like caption from Figma was intentionally omitted.
- No challenge page imports an entity API, HTTP client, `fetch`, or `axios`.
