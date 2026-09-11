# Feature 369 ready UI integration

Base: `feature/369` at `386c22257277da0acbcf67273016ec1c62bf2b46`.
Isolated branch: `codex/369-ready-review` in `.codex-work/369-ready-review`.

Included only the completed home time-slot navigation (`5c5fabe`), OCR information disclosure (`5b10b71`), upcoming-visit cleanup (`f6ddadb`), auth surface/entrances (`738c3b3`), and feedback back navigation (`2227267`). Full functional feature 390/391/315 branches are not included.

## Conflict and integration decisions

- OCR source and three existing tests conflicted because feature 369 retains missing-extraction warnings while the source commit's newer main base does not. Kept feature 369's warning predicate, counts, and pre-save confirmation. Applied only the disclosure and separate-edit UI. The existing two-missing-fields test first failed with zero warnings, then passed after preserving that predicate. The new read-only disclosure test retains feature 369's warning for missing fields.
- Home's new navigator changes the card nesting. The three existing clay header selectors now use `data-home-dose-card`; the colors, tint, rounded body, and shadow values are unchanged. A regression first observed the foreground color instead of the expected brand color, then passed after the hook change.
- Four dose rollback/retry tests used page-wide article selectors. They now select the morning group explicitly, including inspection while an error dialog makes the background inaccessible to role queries. No dose implementation was changed.
- Visit, auth, feedback-back, and the remaining home changes applied cleanly. Existing 369 style files were otherwise retained.

## Verification results

All verification used WSL Node 22.23.1 and Chromium. API fixtures used `VITE_USE_MOCK=false`, port 44418, and `/tmp/369-ready-review-vite-e2e-real`. Mock-only 369 suites used `VITE_USE_MOCK=true`, port 44419, and `/tmp/369-ready-review-vite-e2e-mock`. Both forced `VITE_API_BASE_URL=/api` and proxy `http://127.0.0.1:9`; no real backend or database was used. Local runner overrides are preserved under the isolated worktree's `frontend/test-results/369-review-{playwright,vite}.config.ts`.

The broad API run contained 110 cases: 105 passed, four old unscoped dose selectors failed, and one mock-only account test skipped. After correction, all four dose-error cases passed together. All 10 home navigation tests also passed on the final styled implementation. This supplies passing coverage for all 109 applicable API-fixture cases.

The broad mock run contained 35 cases: 34 passed, and the old direct-child home-card locator failed. After the style-hook and locator correction, all 14 home-clay/responsive cases passed together, including that case. This supplies passing coverage for all 35 mock cases. The other mock coverage includes common controls/motion, visual regressions, chat feedback flows, and feature 369's low-confidence OCR edit warning policy.

Fresh final `npm run typecheck` and `npm run build` passed. Vite emitted its existing large-chunk warning. `git diff --check` passed. Expected refused proxy requests in broad legacy fixtures were limited to the intentionally closed local proxy. The runs do not claim physical mobile-device or live-backend validation.

## Actual rendered screenshots

Screenshots remain as local review artifacts under this isolated worktree's `frontend/test-results`:

- `369-final-home/home-slot-swipe-four-sched-1e976-ve-the-current-time-default/`: medication and supplement at 320, 390, 1280.
- `369-final-clay/`: 369 home clay surfaces and responsive pages.
- `369-ocr-disclosure/`: collapsed and expanded OCR at 320/390.
- `369-ocr-strength-{375,1280}.png`: OCR detailed strength rows.
- `369-integrated-api/follow-up-visit-card-*/`: actual upcoming-visit cards.
- `369-integrated-api/369-auth-stagger-*/`: login and signup at 320/390/1280.
- `369-integrated-api/chat-feedback-api-*/`: feedback back-navigation and error states.

Generated changes to two tracked OCR screenshots were copied to the ignored review-results directory and restored; they are not part of the integration commit.

The root worktree was not switched, written, or merged by this integration task. The parent task may fast-forward feature 369 to the verified integration SHA.
