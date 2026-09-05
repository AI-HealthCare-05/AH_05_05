# Feature 252 UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved 68-state mobile UI as six real application flows while preserving existing API behavior.

**Architecture:** Each domain updates its existing pages and entity adapters in an isolated branch. Figma frames define visual and interaction states, existing entity APIs remain the data boundary, and the integration branch resolves only route/export overlap.

**Tech Stack:** React 19, TypeScript, React Router 7, Tailwind CSS 4, Radix UI, Lucide React, Playwright, Vite.

**Spec:** `docs/superpowers/specs/2026-09-04-feature-252-ui-overhaul-design.md`

## Global Constraints

- Branch commits use `[feature/252][신동훈]변경 내용`.
- Mobile web only; 390×844 Figma reference and light theme.
- Use Figma file `3qUR2z0rh6aYJfeJSxiUmg`, section `614:161`; call `get_design_context` for every target frame before implementation.
- Reuse current components, entity APIs, and semantic tokens. Add no dependency and invent no HTTP endpoint.
- Touch targets are at least 44×44 CSS pixels and root tab screens use the shared `BottomTabbar`.
- Follow RED → GREEN with one focused Playwright contract per changed behavior, then typecheck and build.

---

### Task 1: Authentication and tutorial

**Files:**
- Modify: `frontend/src/pages/auth/AuthPage.tsx`
- Modify: `frontend/src/pages/splash/SplashPage.tsx`
- Create: `frontend/src/pages/tutorial/TutorialPage.tsx`
- Create: `frontend/src/pages/tutorial/index.ts`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/e2e/auth-signup-tutorial-figma.spec.ts`

**Interfaces:**
- Consumes: existing `createAccount`, `login`, `SessionContext`, `Header`, `Input`, `Button`.
- Produces: `/tutorial`, four-step signup state, existing final account submission.

- [ ] Capture design context for the 13 A/B frame IDs listed in the spec.
- [ ] Add a failing Playwright test for progress labels, back/next behavior, final existing API call, and once-per-session tutorial navigation.
- [ ] Run the focused test and record the expected failures.
- [ ] Implement the smallest state machine inside existing auth/splash flows and the new tutorial page.
- [ ] Run focused test, typecheck, and build; commit with the required convention.

### Task 2: Home

**Files:**
- Modify: `frontend/src/pages/home/HomePage.tsx`
- Modify: `frontend/src/pages/home/MedicationTimeline.tsx`
- Modify: `frontend/src/shared/ui/RxVitaFeatureCarousel.tsx`
- Test: `frontend/tests/e2e/home-figma-overhaul.spec.ts`

**Interfaces:**
- Consumes: medication overview/dose record APIs, supplement ranking APIs, `BottomTabbar`.
- Produces: episode-level completion and expansion, split note/taken actions, compact guest carousel.

- [ ] Capture design context for frames `622:183`, `622:271`, `622:361`, `623:198`, `630:214`, `630:256`, `630:298`, `631:218`.
- [ ] Add a failing Playwright test for grouped episodes, expand/collapse, batch completion, note navigation, and guest carousel height.
- [ ] Run the focused test and record the expected failures.
- [ ] Adapt the existing timeline and carousel without replacing API calls or adding dependencies.
- [ ] Run focused test, typecheck, and build; commit with the required convention.

### Task 3: Medication registration, prescriptions, and notes

**Files:**
- Modify: `frontend/src/pages/document-upload/DocumentUploadPage.tsx`
- Modify: `frontend/src/pages/ocr-review/OcrReviewPage.tsx`
- Modify: `frontend/src/pages/medication-schedule/MedicationSchedulePage.tsx`
- Modify: `frontend/src/pages/medication-schedule/MedicationAlarmTimesPage.tsx`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Modify: `frontend/src/pages/medications/MedicationEpisodeCard.tsx`
- Create: `frontend/src/pages/medications/MedicationNotesPage.tsx`
- Create: `frontend/src/pages/medications/MedicationNoteFormPage.tsx`
- Create: `frontend/src/entities/medication-note/types.ts`
- Create: `frontend/src/entities/medication-note/store.ts`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/e2e/medication-feature-252.spec.ts`

**Interfaces:**
- Consumes: document OCR, medication schedule, alarm, overview and delete APIs.
- Produces: five-step registration presentation; episode edit/view/delete; local note adapter and `/medications/notes` routes.

- [ ] Capture design context for all 21 D/E frame IDs listed in the spec.
- [ ] Add failing Playwright tests for `n / 5`, alias and slot flow, direct episode sheet, completed read-only detail, and note CRUD.
- [ ] Run focused tests and record the expected failures.
- [ ] Reshape existing registration/list components, retaining current API boundaries; implement the note adapter without a fabricated HTTP call.
- [ ] Run medication registration, medication management, focused feature tests, typecheck, and build; commit with the required convention.

### Task 4: Supplements

**Files:**
- Modify: `frontend/src/pages/supplements/SupplementsPage.tsx`
- Modify: `frontend/src/pages/supplements/SupplementsBrowseView.tsx`
- Modify: `frontend/src/pages/supplements/SupplementProductPage.tsx`
- Modify: `frontend/src/pages/supplements/EditSupplementSheet.tsx`
- Create: `frontend/src/pages/supplements/MySupplementDetailPage.tsx`
- Modify: `frontend/src/pages/supplements/index.ts`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/e2e/supplements-feature-252.spec.ts`

**Interfaces:**
- Consumes: existing supplement CRUD, ranking, search, detail, rating, memo, and review APIs.
- Produces: registered supplement detail route with rating edit and stop confirmation.

- [ ] Capture design context for all 11 F frame IDs listed in the spec.
- [ ] Add a failing Playwright test for own-supplement navigation, rating/memo/review display, rating edit, product link, and stop confirmation.
- [ ] Run the focused test and record the expected failures.
- [ ] Reuse existing supplement API and edit sheet behavior while matching Figma states.
- [ ] Run existing supplement tests, focused test, typecheck, and build; commit with the required convention.

### Task 5: Chatbot

**Files:**
- Modify: `frontend/src/pages/chat/ChatPage.tsx`
- Modify: `frontend/src/pages/chat/ChatSessionList.tsx`
- Modify: `frontend/src/pages/chat/ChatDeleteDialog.tsx`
- Create: `frontend/src/pages/chat/ChatFeedbackSheet.tsx`
- Test: `frontend/tests/e2e/chat-feature-252.spec.ts`

**Interfaces:**
- Consumes: existing chat history/send/session-list/session-delete APIs and chatbot avatar.
- Produces: chatbot naming, end-and-feedback states, selection deletion, corrected response metadata.

- [ ] Capture design context for frames `672:709`, `672:742`, `672:772`, `672:809`, `672:860`, `672:912`, `693:877`, `693:939`.
- [ ] Add a failing Playwright test for naming, end feedback height/content, response metadata, delete selection and existing delete API call.
- [ ] Run the focused test and record the expected failures.
- [ ] Implement the Figma states using current chat context and delete adapter.
- [ ] Run existing chat tests, focused test, typecheck, and build; commit with the required convention.

### Task 6: My page

**Files:**
- Modify: `frontend/src/pages/my/MyPage.tsx`
- Modify: `frontend/src/pages/my/MyProfilePage.tsx`
- Modify: `frontend/src/pages/my/FollowUpVisitsPage.tsx`
- Modify: `frontend/src/pages/my/FollowUpVisitSheet.tsx`
- Modify: `frontend/src/pages/my/MedicationTimeSettingsSheet.tsx`
- Modify: `frontend/src/pages/my/PasswordChangeSheet.tsx`
- Modify: `frontend/src/pages/my/WithdrawAccountDialog.tsx`
- Test: `frontend/tests/e2e/my-feature-252.spec.ts`

**Interfaces:**
- Consumes: existing account, follow-up visit, settings, password, logout, and withdrawal APIs.
- Produces: complete notification list, logout, password sheet, hidden withdrawal action, email-free profile form.

- [ ] Capture design context for all seven G frame IDs listed in the spec.
- [ ] Add a failing Playwright test for three notification toggles, logout, password change, no email field, withdrawal location, and visit sheets.
- [ ] Run the focused test and record the expected failures.
- [ ] Restyle and regroup existing controls while preserving their API behavior.
- [ ] Run existing My/visit/account tests, focused test, typecheck, and build; commit with the required convention.

### Task 7: Integration and visual QA

**Files:**
- Modify only conflicting exports/routes/styles discovered during cherry-pick.
- Test: all `frontend/tests/e2e/*.spec.ts`.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: a runnable `codex/feature-252-ui-overhaul` branch for user verification in PyCharm.

- [ ] Cherry-pick reviewed domain commits and resolve overlaps by preserving every route and existing API behavior.
- [ ] Run the complete Playwright suite, typecheck, and production build.
- [ ] Capture representative 390×844 screenshots for auth, home, medication/OCR, supplements, chatbot, and My.
- [ ] Check 375×812 and 844×390 for horizontal overflow, covered content, touch targets, and semantic token use.
- [ ] Run a final whole-branch review and fix any Critical or Important finding before handoff.
