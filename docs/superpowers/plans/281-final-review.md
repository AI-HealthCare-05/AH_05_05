# #281 independent final frontend review

Scope: shared challenge fixtures/state, every challenge page, Home/My/router entry diffs, and challenge tests. Read the review package, the September 7 plan/global constraints, and all A/B/C reports. No source edits, git mutations, or duplicate test runs. Integrated browser/WSL verification and direct Figma visual comparison remain with the controller.

## Verdict

No remaining critical or important findings after the scoped correction review. Both original P2 findings below are closed by source inspection. Core official join/check-in/badge and successful/empty/error lookup paths are coherent by inspection. No challenge API/client imports or network implementation found. The latest no-filter, four local generated-art assets, Home navigation-only, automatic medication/supplement without record actions, and matched-challenge naming decisions are reflected in code.

## Closed findings

1. **P2 closed — Target selection is restored on revisit.** `frontend/src/pages/challenges/ChallengeTargetPage.tsx:36`–47 now initializes both target lists from the corresponding participation's `targetIds`, using the original defaults only when no saved selection exists. The added regression in `frontend/tests/e2e/challenges-tailored.spec.ts:43` follows same-session navigation after joining, then asserts the selected and deselected checkboxes for both supplement and medication targets. This addresses the original silent-overwrite path without introducing backend or durable persistence work.

2. **P2 closed — Production-visible example state is identified.** `frontend/src/pages/challenges/ChallengeLayout.tsx:21`–23 now displays “목업 미리보기 · 기준일 2026.09.13 · 새로고침 시 초기화” across both challenge route families. `frontend/src/pages/challenges/HomeChallengeSummary.tsx:27`–29 now displays “예시 데이터” beside the section title. The new regression in `frontend/tests/e2e/challenges-official.spec.ts:11` checks the shared notice on both development and production routes. These small labels meet the plan's explicit demo-state requirement.

## Limits and non-findings

- This is a source review; worker-reported passing tests were inspected but not rerun. Controller owns final integrated tests, image loading, mobile overflow, and Figma review.
- In-memory state resetting on full reload and fixed demonstration dates are intentional and are not defects.
- Available-only checklist denominators and automatic achievement after the final successful lookup are correctly implemented. Unavailable/error views do not mark a record checked.
- New official participation duration is derived from the joining date. Personal start date is retained and pre-start check-in is blocked.
- No additional UX, backend, durable persistence, or generalized state machinery is requested by this review.
