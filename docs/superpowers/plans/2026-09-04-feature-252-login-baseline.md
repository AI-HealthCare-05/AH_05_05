# Feature 252 Login Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the first user-reviewable #252 screen by matching the final Figma login frame without changing existing authentication behavior.

**Architecture:** Keep `AuthPage` as the behavior owner and adapt its login-mode layout using the project’s shared `Header`, `Input`, and `Button` components. Map the final Figma Light semantic values into the existing Tailwind aliases so later screens can reuse the same vocabulary without duplicating hex values.

**Tech Stack:** React 19, TypeScript, React Router 7, Tailwind CSS v4, Playwright

**Spec:** `docs/superpowers/specs/2026-09-04-feature-252-login-baseline-design.md`

## Global Constraints

- Visual source: Figma file `3qUR2z0rh6aYJfeJSxiUmg`, section `614:161`, frame `616:167`.
- Mobile-only review viewport: exactly 390 × 844.
- Light mode only; no Dark-mode implementation or theme toggle.
- Preserve login API, validation, session, and redirect behavior.
- Use semantic Tailwind tokens; no raw hex values in TS or TSX.
- Minimum interactive target is 44px; input and primary CTA height is 52px.
- Do not change signup steps in this task beyond shared-component visual effects.
- Do not add dependencies.
- Commit format: `[feature/252][신동훈]로그인 기본 화면 및 공통 토큰 정합화`.

---

### Task 1: Login visual baseline

**Files:**
- Modify: `frontend/src/app/styles/index.css`
- Modify: `frontend/src/shared/ui/Header.tsx`
- Modify: `frontend/src/shared/ui/Input.tsx`
- Modify: `frontend/src/shared/ui/Button.tsx`
- Modify: `frontend/src/pages/auth/AuthPage.tsx`
- Create: `frontend/tests/e2e/auth-login-figma-baseline.spec.ts`

**Interfaces:**
- Consumes: existing `login(payload)`, `useSession().signIn`, React Router navigation, `Header`, `Input`, and `Button` props.
- Produces: semantic Light token aliases and a `/login` layout matching Figma frame `616:167`; no API signature changes.

- [ ] **Step 1: Install the existing frontend dependencies without changing dependency declarations**

Run:

```powershell
cd frontend
pnpm install --offline --frozen-lockfile
```

Expected: installation completes from the existing pnpm store and `pnpm-lock.yaml` remains unchanged.

- [ ] **Step 2: Write the failing Playwright contract**

Create `frontend/tests/e2e/auth-login-figma-baseline.spec.ts` with a test that sets the viewport to 390 × 844, opens `/login`, and asserts all of the following:

```ts
await expect(page.getByRole('heading', { name: '로그인 · 회원가입' })).toBeVisible();
await expect(page.getByRole('heading', { name: '다시 만나서 반가워요' })).toBeVisible();
await expect(page.getByText('로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.')).toBeVisible();
await expect(page.getByLabel('이메일')).toBeVisible();
await expect(page.getByLabel('비밀번호')).toBeVisible();
await expect(page.getByRole('navigation', { name: '주요 화면' })).toHaveCount(0);
await expect(page.getByAltText('RxVita')).toHaveCount(0);
await expect(page.getByRole('link', { name: '이용약관' })).toBeVisible();
await expect(page.getByRole('link', { name: '개인정보 처리 안내' })).toBeVisible();
```

Also measure the header, inputs, and final exact-name login button with `boundingBox()` and assert heights 64, 52, 52, and 52 respectively. Assert the app container is 390px wide and does not overflow horizontally.

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```powershell
cd frontend
pnpm exec playwright test tests/e2e/auth-login-figma-baseline.spec.ts
```

Expected: FAIL because the current header and inputs are shorter, the existing page still renders the RxVita footer logo and bottom navigation, and the app container does not use the final 390px contract.

- [ ] **Step 4: Map Figma Light tokens into Tailwind aliases**

Update `frontend/src/app/styles/index.css` so the aliases used by existing components resolve to the exact Light values in the spec. Add `tertiary-foreground`, `info`, and `info-bg` aliases for later screens, set `--container-app: 390px`, `--spacing-header: 64px`, and add a 52px control/CTA size token. Keep the existing semantic class names working so unrelated pages do not require mechanical rewrites.

- [ ] **Step 5: Align the shared primitives used by the login screen**

Update the shared components as follows:

```text
Header: 64px height; 44px back target; 20px page title; white surface; subtle bottom border.
Input: 52px control height; 12px radius; control border by default; teal focus ring; existing labels/errors/actions unchanged.
Button: 52px primary CTA height; minimum 44px target; existing variants and disabled behavior unchanged.
```

Do not add screen-specific hex values or create parallel button/input implementations.

- [ ] **Step 6: Adapt AuthPage login layout**

In login mode, match Figma frame `616:167` with normal flex/grid layout rather than absolute positioning. Preserve the existing state and submit handler. Remove the RxVita logo and the bottom navigation from the authentication page; render only the two legal links in the footer. Keep password-reset text non-navigating if no existing route/API exists—do not invent a reset flow in this task.

- [ ] **Step 7: Run focused RED→GREEN verification**

Run:

```powershell
cd frontend
pnpm exec playwright test tests/e2e/auth-login-figma-baseline.spec.ts
pnpm typecheck
pnpm build
```

Expected: the focused test passes, typecheck passes, and the production build succeeds without warnings introduced by this task.

- [ ] **Step 8: Capture the review screenshot**

Start the existing Vite app and capture `/login` at exactly 390 × 844 to the report path supplied by the controller. Do not proceed to another screen.

- [ ] **Step 9: Commit**

```powershell
git add frontend/src/app/styles/index.css frontend/src/shared/ui/Header.tsx frontend/src/shared/ui/Input.tsx frontend/src/shared/ui/Button.tsx frontend/src/pages/auth/AuthPage.tsx frontend/tests/e2e/auth-login-figma-baseline.spec.ts
git commit -m "[feature/252][신동훈]로그인 기본 화면 및 공통 토큰 정합화"
```

Write the implementation report with changed files, RED output, GREEN commands and results, screenshot path, commit hash, and any concern. Return only status, commit hash, one-line test summary, and concerns to the controller.
