# Challenge #281 — Task A implementation report

## Outcome

Implemented the challenge-local state contract and the My, Browse, official detail, participation, layout, and progress-card surfaces. All state is synchronous React-local mock state. Task A does not import entity APIs, the shared API client, or issue network requests.

The shared contract was refined in coordination with Tasks B/C for two designed behaviors that were absent from the initial plan excerpt:

- `PersonalChallengeInput.startDate?: string`, honored when deriving a personal participation period; check-in is disabled before the start date.
- `ChallengeParticipation.targetIds?: string[]`, `targetSummary?: string`, plus optional selection on `joinChallenge`, so a single medication/supplement participation retains the locally selected targets.
- `ChallengeBadge.imageUrl?: string`, used by the shared `ChallengeBadgeArt` renderer for generated artwork while retaining the existing icon union as a fallback.

## Files owned and changed

- `frontend/src/features/challenges/types.ts`
- `frontend/src/features/challenges/mockData.ts`
- `frontend/src/features/challenges/ChallengeMockContext.tsx`
- `frontend/src/features/challenges/index.ts`
- `frontend/src/pages/challenges/ChallengeLayout.tsx`
- `frontend/src/pages/challenges/ChallengeProgressCard.tsx`
- `frontend/src/pages/challenges/ChallengeMyPage.tsx`
- `frontend/src/pages/challenges/ChallengeBrowsePage.tsx`
- `frontend/src/pages/challenges/OfficialChallengePage.tsx`
- `frontend/src/pages/challenges/ChallengeParticipationPage.tsx`
- `frontend/tests/e2e/challenges-official.spec.ts`
- `docs/superpowers/plans/281-A-report.md`

No files were staged, committed, or branch-switched.

## Deterministic fixture IDs

Demo date: `2026-09-13`.

Definitions:

- `official-walk-7d` — active daily official example
- `official-water-7d` — unjoined daily official example
- `official-stretch-weekly` — unjoined weekly official example (3 times/week for 2 weeks)
- `official-ended` — ended-enrollment example
- `official-walk-achieved-demo` — achieved history definition
- `official-walk-missed-demo` — missed history definition
- `official-first-finish-demo` — last-step badge-award behavior fixture
- `medication-routine`, `supplement-routine`, `review-records`, `visit-records`

Participations:

- `part-official-active`, `part-official-achieved`, `part-official-missed`
- `part-official-first-finish`
- newly joined fixed IDs: `part-official-water`, `part-official-stretch`
- `part-medication-active`, `part-supplement-active`
- `part-review-active`, `part-visit-active`

Checklist items:

- Available: `review-medications`, `review-supplements`, `visit-followup`
- Unavailable and excluded from the required-item denominator: `review-note`

Badges (six-item Figma catalog):

- Earned: `badge-walk`, `badge-pill`, `badge-sprout`
- Initially unearned: `badge-first`, `badge-review` (water), `badge-visit` (stretching)

## State behavior

- Existing joins return the existing participation ID; local medication/supplement selection can update that participation.
- New official joins derive their end date from the join date and frequency duration.
- Daily check-in is idempotent for the demo date.
- Weekly check-in caps each calendar participation week at its configured weekly target; completion still requires the total across all configured weeks.
- Check-in rejects inactive, automatic, checklist, pre-start, and post-end participations.
- A final valid check-in transitions to achieved and awards an unearned badge in the same user action.
- Checklist completion ignores missing, unavailable, already checked, and inactive items. Its denominator counts available items only.
- Reset restores deep-copied deterministic fixtures.

## Figma design contexts read

All calls used file `3qUR2z0rh6aYJfeJSxiUmg`, `get_design_context`, React/TypeScript/CSS client metadata, and the `figma-design-to-code` skill marker.

- `725:11` — My: 390px frame, 20px page inset, 350px cards, My/Browse segmented control, pale-green 3-badge summary, automatic routine cards, direct official `했어요`, past-record entry.
- `725:14` — Browse: segmented control, outlined tailored CTA, pale-green featured official card, official cards with recruitment/duration metadata, lightweight custom-challenge entry.
- `725:20` — Official prejoin: title, official/badge highlight, recruitment and join-relative duration guidance, certification disclaimer, single bottom participation CTA.
- `725:17` — Active official: participation period, pale-green “오늘도 한 걸음” progress area, date record grid, today goal, certification disclaimer, `했어요` CTA.
- `742:6480` — Checked official: recorded-today confirmation, duplicate-day explanation, updated grid/progress, completed CTA state.

The implementation uses the existing RxVita semantic Tailwind tokens and existing `Button` and `BottomTabbar`; Lucide glyphs follow the existing project icon convention. Fixed Figma widths were translated into the existing responsive 390px shell with 20px page padding rather than copied as overflow-prone absolute sizing.

## TDD and verification

The official suite was written before production code. The first valid browser red run in WSL failed because the challenge routes and UI did not yet exist. A prior attempt also documented the environment-only absence of system Chrome; no dependencies were installed, and the existing cached Playwright Chromium was then selected through `PLAYWRIGHT_CHANNEL=chromium`.

Final commands, all run in WSL with Node 22.23.1 and `pnpm`:

```text
pnpm exec tsc --noEmit
```

Result: pass, no output.

```text
PLAYWRIGHT_TEST_PORT=44281 PLAYWRIGHT_CHANNEL=chromium \
pnpm exec playwright test tests/e2e/challenges-official.spec.ts \
  --output=test-results-281-A
```

Initial Task A result: 6 passed in 17.9s.

Covered behaviors: Browse → detail → join, direct My check-in, same-day idempotence and detail consistency, achieved history/result/badge, newly awarded badge state, ended enrollment disabled, and zero XHR/fetch requests through browse/join.

## Concerns / controller review notes

- Figma provides a daily official detail example, not a distinct weekly official detail frame. Weekly text and units reuse the same component while explicitly stating “every week” targets; this is the smallest coherent adaptation and was not treated as a new visual redesign.
- The initial shared contract omitted custom start date and selected target persistence although those controls exist in the referenced flows. Those type refinements were communicated before cross-worker consumption and implemented without any backend/API model.
- `ChallengeLayout` owns only the scroll shell and bottom navigation. Each page owns its single `main` landmark and 20px padding, preventing nested landmarks and double 40px insets across Tasks A/B/C.
- The controller should still perform the requested final 320/375/390/430px visual/overflow audit and full challenge-suite/build run after all worker changes settle.

## Follow-up: generated badge artwork and mock disclosure

After the initial implementation, the user explicitly requested generated badge artwork. The shared badge fixtures now point to the generated local assets:

- `/images/challenges/badge-walk.png`
- `/images/challenges/badge-medication.png`
- `/images/challenges/badge-supplement.png`
- `/images/challenges/badge-review.png`

My recent badges, the official prejoin reward, and the achieved-participation reward all reuse Task C's `ChallengeBadgeArt` component; Task A does not draw a substitute reward glyph. Water, stretching, and first-challenge rewards use the generic review artwork because four generated categories were provided for the six-item catalog.

ChallengeLayout also shows the visible disclosure `목업 미리보기 · 기준일 2026.09.13 · 새로고침 시 초기화` on both `/dev/challenges` and `/challenges`, so automatic-looking records are not presented as live health data.

The added behavior was tested red-first in WSL: the badge-art test initially failed on the official reward image, and the mock-disclosure test initially failed because the notice was absent. Final WSL-only verification after both changes:

- `pnpm exec tsc --noEmit` — pass.
- `PLAYWRIGHT_TEST_PORT=44281 PLAYWRIGHT_CHANNEL=chromium pnpm exec playwright test tests/e2e/challenges-official.spec.ts --output=test-results-281-A` — 8 passed in 18.1s.
