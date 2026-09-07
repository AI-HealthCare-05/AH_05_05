# Challenge #281 — Task B report

## Implemented files

- `frontend/src/pages/challenges/ChallengeTailoredPage.tsx`
  - Normal and empty 맞춤 챌린지 states.
  - Links to medication, supplement, weekly review, visit preparation, custom creation, record registration, and browse flows.
- `frontend/src/pages/challenges/ChallengeTargetPage.tsx`
  - Medication and supplement multi-selection.
  - Review and visit target summaries.
  - One participation is reused/created with local selected target IDs and summary only.
- `frontend/src/pages/challenges/ChallengeCreatePage.tsx`
  - Required title/task validation, selectable start date, daily presets/custom days, weekly count controls and week presets/custom weeks.
  - Uses the shared local mock provider only.
- `frontend/src/pages/challenges/ChallengeChecklistView.tsx`
  - Embedded review/visit summaries and record links.
  - Available-only completion denominator; unavailable records remain informational and unchecked.
  - No separate final confirmation action.
- `frontend/src/pages/challenges/ChallengeRecordPage.tsx`
  - Challenge-local medication, supplement, note-empty, visit, and invalid/error views.
  - Period context and return link preserved.
  - Successful content marks an available checklist item once; empty/error views do not mark it.
- `frontend/tests/e2e/challenges-tailored.spec.ts`
  - Eight flow tests covering latest naming, empty state, target selection persistence and re-entry restoration, weekly inputs, personal creation/validation, idempotent successful lookup, and empty/error lookup.

Shared contract refinements were coordinated with Task A: optional `PersonalChallengeInput.startDate`; optional participation `targetIds`/`targetSummary`; optional join selection argument; available-only checklist target calculation.

## Figma design context read

File `3qUR2z0rh6aYJfeJSxiUmg`:

- Tailored: `725:5`, empty `725:44`
- Medication target: `725:23`
- Supplement target: `725:26`
- Personal daily: `725:29`
- Personal weekly: `802:2`
- Review: `725:41`
- Visit: `725:38`
- Checklist placeholders: `840:6458`, `840:24`
- Record-style references: medication `647:239`, supplement `650:268`, notes `683:877`, visit `665:742`

## Preview routes

- `/dev/challenges/tailored`
- `/dev/challenges/tailored-empty`
- `/dev/challenges/tailored/medication`
- `/dev/challenges/tailored/supplement`
- `/dev/challenges/tailored/review`
- `/dev/challenges/tailored/visit`
- `/dev/challenges/create` (toggle 매일 / 주 몇 회)
- `/dev/challenges/participations/part-review-active`
- `/dev/challenges/participations/part-visit-active`
- `/dev/challenges/participations/part-review-active/records/review-medications`
- `/dev/challenges/participations/part-review-active/records/review-supplements`
- `/dev/challenges/participations/part-review-active/records/review-note`
- `/dev/challenges/participations/part-visit-active/records/visit-followup`

## Verification (WSL only, pnpm only)

- RED observed: `PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44282 pnpm exec playwright test tests/e2e/challenges-tailored.spec.ts --workers=1 --max-failures=1 --timeout=30000`
  - Failed on missing 맞춤 챌린지 heading before implementation.
- Typecheck: `pnpm exec tsc --noEmit` — PASS.
- Task B E2E: `PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44282 pnpm exec playwright test tests/e2e/challenges-tailored.spec.ts --workers=1 --timeout=30000 --output=test-results-281-B` — 8 PASS.

## Follow-up regression: stored target selection

- Reproduced the remount defect before the fix: after saving only 유산균, reopening the supplement target page restored the original hardcoded 오메가3/종합비타민 selection.
- Root cause: `ChallengeTargetPage` initialized both checkbox groups exclusively from hardcoded defaults even though `joinChallenge` persisted `participation.targetIds`.
- Fix: initial checkbox state now copies existing medication/supplement participation `targetIds` when present, falling back to design defaults only before any selection has been saved.
- Focused red/green verification covered both supplement and medication navigation re-entry; the final full suite is 8 PASS and WSL typecheck remains PASS.

## Concerns / review notes

- Figma checklist component nodes `840:6458` and `840:24` are blank placeholders. The implementation follows the approved lookup behavior and the card/token language of the surrounding review/visit frames; controller visual review remains important.
- Record pages deliberately reuse the existing record-screen visual language with clearly labeled challenge-local mock data. They import no entity APIs and perform no network requests.
- Figma does not expose a separate personal-challenge description field although the shared contract requires one, so the submitted task label is also used as the local description instead of adding an unapproved form field.
