# #100 Home Renewal and Account Phone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect name and phone number in account flows and render multi-care-episode medication data on a compact, collapsible home and episode-based medication tab.

**Architecture:** Account fields remain behind `entities/account`; phone formatting and validation live in `shared/lib`. Medication screens consume an array-normalizing entity API, while each dose record is keyed by `recordId + date + slot` so the home can aggregate honestly and episode detail remains separable.

**Tech Stack:** React 19, TypeScript, React Router, Tailwind token classes, Playwright E2E, Vite.

**Spec:** `docs/superpowers/specs/2026-08-26-issue-100-home-account-design.md`

## Global Constraints

- Work on `feature/100`; do not modify user-owned `README.md`, `docs/API명세_프론트_최신.md`, or `docs/ui-reference/`.
- Use token classes only; add no hard-coded hex colors or arbitrary Tailwind pixel values.
- Minimum touch target remains 44px and body copy remains at least 14px.
- Keep `PokeFeatureCarousel` on both guest and authenticated home.
- Medication pages call only `entities/medication/api.ts`; account pages call only `entities/account/api.ts`.
- Do not remove OCR review's original-image preview; remove it only from the medication tab.

---

### Task 1: Name and phone account fields

**Files:**
- Create: `frontend/src/shared/lib/phoneNumber.ts`
- Modify: `frontend/src/entities/account/types.ts`
- Modify: `frontend/src/entities/account/api.mock.ts`
- Modify: `frontend/src/pages/auth/AuthPage.tsx`
- Modify: `frontend/src/pages/my/MyProfilePage.tsx`
- Modify: `frontend/src/pages/my/MyPage.tsx`
- Test: `frontend/tests/e2e/account-profile.spec.ts`
- Test: `frontend/tests/e2e/entry-home-auth.spec.ts`

**Interfaces:**
- Produces: `formatPhoneNumberInput(value: string): string`, `normalizePhoneNumber(value: string): string`, `validatePhoneNumber(value: string): string | null`.
- Produces: `AccountProfile { name, phoneNumber, birthDate, gender }` and matching create/update payloads.

- [ ] **Step 1: Write failing E2E tests** for required field order, hyphen formatting, invalid-number inline error, mock signup persistence, and profile edit persistence.
- [ ] **Step 2: Run `pnpm exec playwright test tests/e2e/account-profile.spec.ts tests/e2e/entry-home-auth.spec.ts`** and confirm failures are missing name/phone controls or values.
- [ ] **Step 3: Implement phone helpers, expand account contracts/mocks, and add controlled inputs**. Normalize only at the entity API boundary so screens keep readable formatting.
- [ ] **Step 4: Run the two E2E files again** and confirm all tests pass.

### Task 2: Multi-episode medication entity contract

**Files:**
- Modify: `frontend/src/entities/medication/types.ts`
- Modify: `frontend/src/entities/medication/api.ts`
- Modify: `frontend/src/entities/medication/api.mock.ts`
- Modify: `frontend/src/entities/medication/index.ts`
- Test: `frontend/tests/e2e/home-dose-record-grid.spec.ts`

**Interfaces:**
- Produces: `getMedicationOverviews(): Promise<MedicationOverview[]>`.
- Produces: `getMedicationOverview(recordId?: number): Promise<MedicationOverview>`.
- Produces: record-aware `DoseRecord`, `DoseRecordRange`, and `SaveDoseTakenPayload`.

- [ ] **Step 1: Add a failing multi-episode fixture test** that expects two care episodes to contribute distinct medication names and record-aware dose state.
- [ ] **Step 2: Run `pnpm exec playwright test tests/e2e/home-dose-record-grid.spec.ts`** and confirm the second episode is absent.
- [ ] **Step 3: Add the collection normalizer, two-episode mock, and record-aware mock store** while preserving the single-overview adapter.
- [ ] **Step 4: Run typecheck and the focused grid test** and confirm the new contract is green.

### Task 3: Compact aggregated home timeline and grid

**Files:**
- Modify: `frontend/src/pages/home/HomePage.tsx`
- Modify: `frontend/src/pages/home/MedicationRecordGrid.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/e2e/entry-home-auth.spec.ts`
- Test: `frontend/tests/e2e/home-dose-record-grid.spec.ts`
- Test: `frontend/tests/e2e/home-dose-record-animation.spec.ts`

**Interfaces:**
- Consumes: `getMedicationOverviews`, record-aware dose functions.
- Produces: collapsed `아침약 N개 · HH:mm` rows, independent detail toggles, all-episode dose save/undo, aggregate record grid.

- [ ] **Step 1: Write failing tests** for authenticated carousel visibility, two-episode slot aggregation, default collapsed content, expand/collapse, all-episode completion, and aggregate grid completion.
- [ ] **Step 2: Run the three focused E2E files** and confirm failures match single-overview/auto-expanded behavior.
- [ ] **Step 3: Refactor HomePage loading and dose mutation to arrays**, keeping optimistic rollback and entity boundaries.
- [ ] **Step 4: Refactor timeline rows to default-collapsed disclosure controls** with count/time always visible and medication/source detail only when expanded.
- [ ] **Step 5: Refactor MedicationRecordGrid to aggregate episode targets** and mark a cell taken only when all targets have records.
- [ ] **Step 6: Run the three focused E2E files and typecheck** and confirm green output.

### Task 4: Episode list and detail medication pages

**Files:**
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Create: `frontend/src/pages/medications/MedicationEpisodePage.tsx`
- Modify: `frontend/src/pages/medications/index.ts`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/e2e/remaining-pages.spec.ts`

**Interfaces:**
- Consumes: `getMedicationOverviews`, `getMedicationOverview(recordId)`.
- Produces: `/medications` episode list and `/medications/:recordId` episode detail.

- [ ] **Step 1: Write failing tests** that require no original-envelope control, two episode cards, detail navigation, alarm time, and only the selected episode's medication list.
- [ ] **Step 2: Run `pnpm exec playwright test tests/e2e/remaining-pages.spec.ts`** and confirm the old single episode/image UI fails expectations.
- [ ] **Step 3: Replace the medication landing content with episode cards** and keep the add button and bottom tab.
- [ ] **Step 4: Move current schedule/medication detail behavior into `MedicationEpisodePage`** without image viewer code.
- [ ] **Step 5: Register the parameter route and run the focused E2E file** until green.

### Task 5: Regression verification and commit

**Files:**
- Modify only files required by failures discovered in the verification run.

- [ ] **Step 1: Run `pnpm typecheck`.** Expected: exit 0.
- [ ] **Step 2: Run `pnpm build`.** Expected: exit 0.
- [ ] **Step 3: Run `pnpm test:e2e`.** Expected: all non-real-API tests pass; intentional real-API skips remain skipped.
- [ ] **Step 4: Run `rg -n "#[0-9a-fA-F]{6}" frontend/src -g "*.tsx"`.** Expected: no output.
- [ ] **Step 5: Inspect at 375px using Playwright screenshots** for signup, authenticated multi-episode home collapsed/expanded, medication episode list, and detail.
- [ ] **Step 6: Stage only #100 files and commit** with `[feature/100][신동훈]홈 리뉴얼 및 회원가입 전화번호 추가`.
