# Feature 166 Empty States Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent FastAPI developer details from reaching users, treat missing medication collections as empty state, and redirect real guest My-page visits to login while preserving the development guest view.

**Architecture:** Normalize unsafe API errors once in `shared/api/client.ts`, and translate the medication collection's expected 404 into `[]` at the entity boundary. Pages consume only safe `Error.message` values or normal empty collections, while authentication navigation stays inside page components so `app/` remains untouched.

**Tech Stack:** React 19, TypeScript, React Router 7, Playwright, Tailwind CSS

**Spec:** `C:/Users/sdh08/.codex/attachments/2a323b24-0ce4-4d68-a0a1-7da67cdbfbd0/pasted-text.txt`

## Global Constraints

- Work on branch `feature/166` from `main`.
- Commit messages use `[feature/166][신동훈]내용`; do not use Conventional Commits.
- Modify frontend files only; do not modify `app/` or supplement code.
- Keep all six page-level `error instanceof Error ? error.message : fallback` patterns unchanged.
- Use no hexadecimal colors in frontend TSX.
- Verify the resulting UI at a 375px viewport.

---

### Task 1: Safe API Error Detail Handling

**Files:**
- Modify: `frontend/src/shared/api/client.ts`
- Test: `frontend/tests/e2e/api-error-message.spec.ts`

**Interfaces:**
- Consumes: FastAPI error bodies with optional `code`, `message`, `field`, and `detail`.
- Produces: `ApiError(status, code, message, field?, detail?)` where `message` is either `body.message` or the Korean fallback and `detail` remains developer-only diagnostic data.

- [ ] **Step 1: Write failing browser tests**

Add routes returning 404 string `detail`, 422 validation-array `detail`, and Korean `message`; assert the first two render the Korean fallback rather than English detail, while the third renders the Korean server message.

- [ ] **Step 2: Run tests and verify RED**

Run: `pnpm exec playwright test tests/e2e/api-error-message.spec.ts`

Expected: detail cases fail because `Not Found` and `field required` are visible.

- [ ] **Step 3: Implement minimal normalization**

Add `readonly detail?: unknown` to `ApiError`, stop promoting `detail` into `message`, pass `body.detail` to the error, and call `console.warn` only when `import.meta.env.DEV` and detail is present.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same Playwright spec and expect all cases to pass.

### Task 2: Medication 404 and Empty-State Calls to Action

**Files:**
- Modify: `frontend/src/entities/medication/api.ts`
- Modify: `frontend/src/pages/home/HomePage.tsx`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Test: `frontend/tests/e2e/medication-empty-states.spec.ts`
- Update: existing affected Playwright expectations

**Interfaces:**
- Consumes: `ApiError` from `http.get('/v1/medications')`.
- Produces: `getMedicationOverviews(): Promise<MedicationOverview[]>`, returning `[]` only for status 404 and rethrowing all other failures.

- [ ] **Step 1: Write failing empty-state tests**

Assert a 404 produces the Home `오늘의 복약` card with the exact guidance and a working `/document-upload` button, and produces the medication-list guidance `복용약을 등록해 주세요.` with the same action. Assert a 500 still renders the existing error cards.

- [ ] **Step 2: Run tests and verify RED**

Run: `pnpm exec playwright test tests/e2e/medication-empty-states.spec.ts`

Expected: 404 renders an error and the requested copy/actions are missing.

- [ ] **Step 3: Implement the entity and page changes**

Catch only `ApiError` status 404 in `getMedicationOverviews`; use the existing Home `onUpload` callback; add the exact card titles, copy, and `약봉투 등록하기` buttons without changing non-404 error branches.

- [ ] **Step 4: Update superseded assertions and verify GREEN**

Update older specs that assert `약봉투를 등록해 주세요` or `약봉투 등록`, then run the new and affected specs.

### Task 3: Guest My-Page Redirect and Login Navigation

**Files:**
- Modify: `frontend/src/pages/my/MyPage.tsx`
- Modify: `frontend/src/pages/auth/AuthPage.tsx`
- Test: `frontend/tests/e2e/remaining-pages.spec.ts`

**Interfaces:**
- Consumes: `authenticatedOverride?: boolean` and session authentication.
- Produces: real unauthenticated `/my` visits navigate to `/login` with replacement; explicit `/dev/my-guest` remains renderable; Login exposes legal links and a bottom tabbar.

- [ ] **Step 1: Write failing navigation tests**

Assert `/my` redirects, browser Back does not restore `/my`, `/dev/my-guest` does not redirect, the removed guest card is absent, and `/login` exposes legal links plus navigation back to Home.

- [ ] **Step 2: Run tests and verify RED**

Run: `pnpm exec playwright test tests/e2e/remaining-pages.spec.ts`

Expected: `/my` remains on its guest card and Login lacks the legal links/tabbar.

- [ ] **Step 3: Implement minimal page behavior**

Redirect only when `authenticatedOverride === undefined && !authenticated`; remove the guest card; move legal links to Auth; add `BottomTabbar` with guest-safe tab handling.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same Playwright spec and expect all relevant tests to pass.

### Task 4: Regression and Scope Verification

**Files:**
- Verify only; no new production files.

**Interfaces:**
- Consumes: all changes above.
- Produces: a clean, reviewable feature branch with verified behavior.

- [ ] **Step 1: Run type and browser checks**

Run `pnpm typecheck` and all affected Playwright specs, then the full Playwright suite if the affected set is clean.

- [ ] **Step 2: Verify visual and scope constraints**

Run the targeted tests with a 375px viewport, scan frontend TSX for hexadecimal colors, inspect `git diff -- app`, and verify no supplement file changed.

- [ ] **Step 3: Review and commit**

Inspect the diff and commit with a message matching `[feature/166][신동훈]내용`.
