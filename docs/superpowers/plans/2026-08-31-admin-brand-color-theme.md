# RxVita Admin Brand Color Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy blue interaction colors across every administrator web page with the approved RxVita teal palette, install the latest RxVita logo in the shared sidebar, and rebrand the temporary-password email.

**Architecture:** Define one shared palette in `styles.css`, consume it from `styles.css` and `management.css`, and remove the small number of inline blue exceptions from shared templates. Keep semantic success, warning, error, danger, neutral, layout, and JavaScript behavior unchanged. The email renderer remains independent of web CSS and uses matching literal inline colors for email-client compatibility.

**Tech Stack:** Static HTML, CSS custom properties, Tailwind CDN utility classes, JavaScript Node test runner, Python/Jinja2 email renderer, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-admin-brand-color-theme-design.md`

## Global Constraints

- Brand accent: `#18bfb3`; non-filled hover accent: `#0e9384`.
- Filled buttons and readable links: `#0b7f75`; filled hover: `#096c64`.
- Soft selection: `#e8f9f7`; faint selection: `rgba(24, 191, 179, 0.06)`; focus: `rgba(24, 191, 179, 0.18)`; row hover: `rgba(24, 191, 179, 0.04)`.
- Brand navy: `#06356f`, limited to brand-linked text and the approved logo.
- Preserve semantic success green, processing amber, error/danger red, stopped grey, white cards, neutral greys, typography, spacing, layout, and JavaScript behavior.
- Do not change the user-facing frontend or any email other than the administrator temporary-password email.
- Preserve the current uncommitted login branding changes and all unrelated user changes; stage only the exact files listed by each task.
- Use CSS cache version `20260831-3` for `styles.css`, `management.css`, and `overlays.css` on every administrator entry page.

---

## File Map

- Create `app/tests/static_ui/brand-theme.test.mjs`: shared palette, legacy-blue removal, semantic-color preservation, and cache-version contracts.
- Modify `app/static/css/styles.css`: palette definition and login/dashboard consumers.
- Modify `app/static/css/management.css`: management controls, tables, pagination, sidebar, and ranking consumers.
- Modify `app/static/templates/login.html`: normalized CSS cache versions only; retain the approved RxVita logo and copy.
- Modify `app/static/templates/dashboard.html`: normalized CSS cache versions and OCR inline accent.
- Modify `app/static/templates/user-management.html`: normalized CSS cache versions.
- Modify `app/static/templates/screen-4-admin-management.html`: normalized CSS cache versions.
- Modify `app/static/templates/screen-5-task-management.html`: normalized CSS cache versions.
- Modify `app/static/templates/supplement-ranking.html`: normalized CSS cache versions.
- Modify `app/tests/static_ui/login.test.mjs`: expect the tokenized accessible login action color.
- Modify `app/static/templates/partials/sidebar.html`: replace the legacy icon and copy with the latest full RxVita logo while preserving the SMTP control.
- Modify `app/tests/static_ui/sidebar.test.mjs`: shared sidebar brand contract.
- Modify `app/tests/static_ui/dashboard.test.mjs`: OCR accent token contract.
- Add `app/static/images/rxvita-logo-ai-chat-navy.png` to version control: shared approved logo asset already present in the workspace.
- Modify `app/core/email/renderer.py`: exact RxVita email subject.
- Modify `app/static/templates/emails/admin_temporary_password.html`: RxVita title, bold recipient name, and email-safe brand colors.
- Modify `app/tests/email/test_email_renderer.py`: subject, markup, palette, plain text, and escaping contracts.

---

### Task 1: Shared Web Palette and Administrator Entry Pages

**Files:**
- Create: `app/tests/static_ui/brand-theme.test.mjs`
- Modify: `app/static/css/styles.css`
- Modify: `app/static/css/management.css`
- Modify: `app/static/templates/login.html`
- Modify: `app/static/templates/dashboard.html`
- Modify: `app/static/templates/user-management.html`
- Modify: `app/static/templates/screen-4-admin-management.html`
- Modify: `app/static/templates/screen-5-task-management.html`
- Modify: `app/static/templates/supplement-ranking.html`
- Modify: `app/tests/static_ui/login.test.mjs`

**Interfaces:**
- Consumes: Existing stylesheet load order: `styles.css`, then `management.css`, then `overlays.css`.
- Produces: CSS custom properties `--brand-primary`, `--brand-primary-hover`, `--brand-primary-strong`, `--brand-primary-strong-hover`, `--brand-primary-soft`, `--brand-primary-faint`, `--brand-focus`, `--brand-hover-row`, and `--brand-navy` for all later web tasks.

- [ ] **Step 1: Write the failing shared-theme contract tests**

Create `app/tests/static_ui/brand-theme.test.mjs` with literal palette and page expectations:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const staticRoot = new URL("../../static/", import.meta.url);
const readStatic = (path) => readFile(new URL(path, staticRoot), "utf8");

test("administrator styles expose the approved RxVita palette", async () => {
  const styles = await readStatic("css/styles.css");

  assert.match(styles, /--brand-primary:\s*#18bfb3;/);
  assert.match(styles, /--brand-primary-hover:\s*#0e9384;/);
  assert.match(styles, /--brand-primary-strong:\s*#0b7f75;/);
  assert.match(styles, /--brand-primary-strong-hover:\s*#096c64;/);
  assert.match(styles, /--brand-primary-soft:\s*#e8f9f7;/);
  assert.match(styles, /--brand-primary-faint:\s*rgba\(24, 191, 179, 0\.06\);/);
  assert.match(styles, /--brand-focus:\s*rgba\(24, 191, 179, 0\.18\);/);
  assert.match(styles, /--brand-hover-row:\s*rgba\(24, 191, 179, 0\.04\);/);
  assert.match(styles, /--brand-navy:\s*#06356f;/);
});

test("administrator styles no longer carry the legacy blue interaction palette", async () => {
  const source = (await Promise.all([
    readStatic("css/styles.css"),
    readStatic("css/management.css"),
  ])).join("\n");

  for (const legacy of ["#1c64f2", "#1554d1", "#1d4ed8", "#eff6ff", "28,100,242", "28, 100, 242"]) {
    assert.equal(source.includes(legacy), false, `legacy brand color remains: ${legacy}`);
  }
});

test("semantic management colors remain distinct from the brand palette", async () => {
  const management = await readStatic("css/management.css");

  assert.match(management, /\.status-active\s*\{[^}]*background:\s*#dcfce7;[^}]*color:\s*#166534;/s);
  assert.match(management, /\.status-processing\s*\{[^}]*background:\s*#fef3c7;[^}]*color:\s*#92400e;/s);
  assert.match(management, /\.status-failed\s*\{[^}]*background:\s*#fee2e2;[^}]*color:\s*#b91c1c;/s);
  assert.match(management, /\.ui-button-danger\s*\{[^}]*background:\s*#dc2626;/s);
});

test("every administrator entry page loads the same stylesheet cache version", async () => {
  const pages = [
    "templates/login.html",
    "templates/dashboard.html",
    "templates/user-management.html",
    "templates/screen-4-admin-management.html",
    "templates/screen-5-task-management.html",
    "templates/supplement-ranking.html",
  ];

  for (const page of pages) {
    const html = await readStatic(page);
    for (const stylesheet of ["styles", "management", "overlays"]) {
      assert.match(html, new RegExp(`href="\\.\\.\\/css\\/${stylesheet}\\.css\\?v=20260831-3"`), page);
    }
  }
});
```

In `app/tests/static_ui/login.test.mjs`, change the login button assertion to the tokenized accessible action color:

```js
assert.match(styles, /\.login-button\s*\{[^}]*background:\s*var\(--brand-primary-strong\);/s);
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
node --test app/tests/static_ui/brand-theme.test.mjs app/tests/static_ui/login.test.mjs
```

Expected: FAIL because the palette variables and unified `20260831-3` cache URLs do not exist and legacy blue values remain.

- [ ] **Step 3: Define the palette and replace shared CSS consumers**

Insert these declarations at the start of the existing `:root` block in `app/static/css/styles.css`, before its current `color` and font declarations:

```css
--brand-primary: #18bfb3;
--brand-primary-hover: #0e9384;
--brand-primary-strong: #0b7f75;
--brand-primary-strong-hover: #096c64;
--brand-primary-soft: #e8f9f7;
--brand-primary-faint: rgba(24, 191, 179, 0.06);
--brand-focus: rgba(24, 191, 179, 0.18);
--brand-hover-row: rgba(24, 191, 179, 0.04);
--brand-navy: #06356f;
```

Replace only legacy blue interaction values in `styles.css`:

```css
.brand-mark { background: var(--brand-primary); }
.input-wrap:focus-within {
  border-color: var(--brand-primary);
  box-shadow: 0 0 0 3px var(--brand-focus);
}
.remember-option input { accent-color: var(--brand-primary-strong); }
.password-help { color: var(--brand-primary-strong); }
.login-button { background: var(--brand-primary-strong); }
.login-button:hover { background: var(--brand-primary-strong-hover); }
.login-button:focus-visible { outline-color: var(--brand-focus); }
.period-button.is-active {
  background: var(--brand-primary-faint);
  color: var(--brand-primary-strong);
}
.member-trend-bar { background: var(--brand-primary); }
```

Replace only legacy blue interaction values in `management.css`:

```css
.ui-control:focus { outline-color: var(--brand-focus); border-color: var(--brand-primary); }
.task-status-help:focus { outline-color: var(--brand-focus); }
.ui-button-primary { background: var(--brand-primary-strong); border-color: var(--brand-primary-strong); }
.ui-button-primary:hover { background: var(--brand-primary-strong-hover); }
.ui-link-button { color: var(--brand-primary-strong); }
.management-table tbody tr:hover { background: var(--brand-hover-row); }
.user-page-button.is-active,
.admin-page-button.is-active { background: var(--brand-primary-strong); border-color: var(--brand-primary-strong); }
.user-page-button.is-active:hover,
.admin-page-button.is-active:hover { background: var(--brand-primary-strong-hover); }
.sidebar-link.is-active {
  background: var(--brand-primary-soft);
  border-color: var(--brand-primary);
  color: var(--brand-primary-strong);
}
.rank-product-result:hover { border-color: var(--brand-primary); color: var(--brand-primary-strong); }
```

Do not change `.status-*`, `.ui-button-danger`, `.ui-link-button-danger`, `.toast-success`, or `.toast-error` declarations.

- [ ] **Step 4: Normalize stylesheet cache versions**

In each administrator entry page listed in Step 1, make all three links use these exact URLs while preserving their current load order:

```html
<link rel="stylesheet" href="../css/styles.css?v=20260831-3">
<link rel="stylesheet" href="../css/management.css?v=20260831-3">
<link rel="stylesheet" href="../css/overlays.css?v=20260831-3">
```

- [ ] **Step 5: Run the targeted tests and inspect remaining failures**

Run:

```bash
node --test app/tests/static_ui/brand-theme.test.mjs app/tests/static_ui/login.test.mjs
```

Expected: PASS. This task's legacy-blue contract covers the two shared CSS files; Task 2 adds explicit template-level contracts for the sidebar and dashboard exceptions.

- [ ] **Step 6: Commit the shared palette change**

```bash
git add app/tests/static_ui/brand-theme.test.mjs app/tests/static_ui/login.test.mjs app/static/css/styles.css app/static/css/management.css app/static/templates/login.html app/static/templates/dashboard.html app/static/templates/user-management.html app/static/templates/screen-4-admin-management.html app/static/templates/screen-5-task-management.html app/static/templates/supplement-ranking.html
git commit -m "feat: apply RxVita palette to admin pages"
```

---

### Task 2: Shared Sidebar Logo and Dashboard Inline Accents

**Files:**
- Modify: `app/tests/static_ui/sidebar.test.mjs`
- Modify: `app/tests/static_ui/dashboard.test.mjs`
- Modify: `app/static/templates/partials/sidebar.html`
- Modify: `app/static/templates/dashboard.html`
- Modify: `app/static/css/management.css`
- Add: `app/static/images/rxvita-logo-ai-chat-navy.png`
- Test: `app/tests/static_ui/brand-theme.test.mjs`

**Interfaces:**
- Consumes: Task 1 palette variables from `styles.css` and the existing `data-smtp-settings` button contract.
- Produces: `.sidebar-brand`, `.sidebar-brand-logo`, a shared full-logo header, and token-based dashboard OCR accents.

- [ ] **Step 1: Write failing sidebar and dashboard brand tests**

Append to `app/tests/static_ui/sidebar.test.mjs`:

```js
test("shared sidebar uses the approved full RxVita logo", async () => {
  const html = await readFile(new URL("../../static/templates/partials/sidebar.html", import.meta.url), "utf8");

  assert.match(html, /<img[^>]+class="sidebar-brand-logo"[^>]+src="\.\.\/images\/rxvita-logo-ai-chat-navy\.png"[^>]+alt="RxVita">/);
  assert.match(html, /data-smtp-settings/);
  assert.doesNotMatch(html, /포케 관리자/);
  assert.doesNotMatch(html, /background:#1c64f2/);
});
```

Append to `app/tests/static_ui/dashboard.test.mjs`:

```js
test("OCR accuracy uses the shared RxVita accent tokens", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const accuracyIndex = html.indexOf("OCR 추출 정확도");
  const accuracyCard = html.slice(Math.max(0, accuracyIndex - 900), accuracyIndex + 200);

  assert.match(accuracyCard, /border:6px solid var\(--brand-primary\)/);
  assert.match(accuracyCard, /color:var\(--brand-primary-strong\)/);
  assert.doesNotMatch(accuracyCard, /#1c64f2/);
});
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
node --test app/tests/static_ui/sidebar.test.mjs app/tests/static_ui/dashboard.test.mjs app/tests/static_ui/brand-theme.test.mjs
```

Expected: FAIL because the sidebar still contains the legacy icon/copy and the OCR card still contains `#1c64f2`.

- [ ] **Step 3: Replace the sidebar brand area without breaking SMTP settings**

Replace only the first brand row inside `partials/sidebar.html` with:

```html
<div class="sidebar-brand">
  <img class="sidebar-brand-logo" src="../images/rxvita-logo-ai-chat-navy.png" alt="RxVita">
  <button type="button" data-smtp-settings class="icon-button" style="display:none; margin-left:auto; min-width:32px; min-height:32px; padding:4px;" aria-label="SMTP 설정" title="SMTP 설정">
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.51a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2Z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  </button>
</div>
```

Add to `management.css`:

```css
.sidebar-brand {
  align-items: center;
  display: flex;
  gap: 8px;
  width: 100%;
}

.sidebar-brand-logo {
  display: block;
  height: auto;
  max-width: calc(100% - 40px);
  width: 180px;
}
```

Keep `data-smtp-settings`, its visibility behavior, accessible label, title, and SVG exactly as they are. Do not reuse `.sidebar-logo`, whose current `32px` dimensions are for compact marks.

- [ ] **Step 4: Tokenize the dashboard OCR accent**

In `dashboard.html`, change only the OCR accuracy ring and percentage:

```html
<div class="bg-white rounded-full flex flex-col items-center justify-center w-14 h-14 shrink-0"
     style="border:6px solid var(--brand-primary);">
  <p class="font-bold text-[10px]" style="color:var(--brand-primary-strong);">98%</p>
</div>
```

- [ ] **Step 5: Run the focused tests to verify GREEN**

Run:

```bash
node --test app/tests/static_ui/sidebar.test.mjs app/tests/static_ui/dashboard.test.mjs app/tests/static_ui/brand-theme.test.mjs
```

Expected: PASS, including the global legacy-blue assertion.

- [ ] **Step 6: Commit the shared brand header and inline accents**

```bash
git add app/tests/static_ui/sidebar.test.mjs app/tests/static_ui/dashboard.test.mjs app/tests/static_ui/brand-theme.test.mjs app/static/templates/partials/sidebar.html app/static/templates/dashboard.html app/static/css/management.css app/static/images/rxvita-logo-ai-chat-navy.png
git commit -m "feat: add RxVita branding to admin navigation"
```

---

### Task 3: Branded Administrator Temporary-Password Email

**Files:**
- Modify: `app/tests/email/test_email_renderer.py`
- Modify: `app/core/email/renderer.py`
- Modify: `app/static/templates/emails/admin_temporary_password.html`

**Interfaces:**
- Consumes: `EmailTemplateRenderer.render(payload: EmailJobPayload) -> EmailMessage`, Jinja autoescape, `recipient_name`, and `temporary_password`.
- Produces: exact subject `[RxVita] 임시비밀번호 안내`; HTML with a bold, escaped recipient name; unchanged plain-text wording; RxVita email-safe inline colors.

- [ ] **Step 1: Extend the email renderer tests before changing production code**

Add these assertions to `test_admin_temporary_password_template_renders_approved_text_and_html`:

```python
assert message.subject == "[RxVita] 임시비밀번호 안내"
assert "<strong>홍길동</strong> 님 안녕하세요." in message.html_body
assert "#e8f9f7" in message.html_body
assert "#0b7f75" in message.html_body
assert "#06356f" in message.html_body
assert "#f0f5ff" not in message.html_body
assert "#1746a2" not in message.html_body
```

Strengthen the escaping test so the bold wrapper cannot disable autoescape:

```python
assert "<strong>&lt;script&gt;alert(1)&lt;/script&gt;</strong>" in message.html_body
assert "<script>" not in message.html_body
```

- [ ] **Step 2: Run the renderer tests to verify RED**

Run:

```bash
uv run pytest app/tests/email/test_email_renderer.py -q
```

Expected: FAIL because the old subject and blue email palette remain and the recipient is not wrapped in `<strong>`.

- [ ] **Step 3: Change the exact subject in the renderer**

In `app/core/email/renderer.py`:

```python
ADMIN_TEMPORARY_PASSWORD_SUBJECT = "[RxVita] 임시비밀번호 안내"
```

Do not change `_plain_text`; plain text cannot express bold styling and its approved wording remains valid.

- [ ] **Step 4: Apply email-safe RxVita inline styling**

Update `admin_temporary_password.html` while preserving the existing presentation-table structure:

```html
<title>RxVita 임시비밀번호 안내</title>
```

Use these exact inline palette changes:

```html
<body style="margin:0;padding:24px;background:#f1fbfa;font-family:Arial,'Apple SD Gothic Neo',sans-serif;color:#06356f;">
```

```html
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
       style="max-width:560px;background:#ffffff;border:1px solid #cceeea;border-radius:12px;">
```

```html
<p style="margin:0 0 24px;"><strong>{{ recipient_name }}</strong> 님 안녕하세요.</p>
<p style="margin:0 0 24px;padding:16px;background:#e8f9f7;border-radius:8px;font-weight:700;color:#0b7f75;">임시비밀번호 : {{ temporary_password }}</p>
```

Keep `{{ recipient_name }}` and `{{ temporary_password }}` as normal Jinja variables so the environment's existing autoescape remains effective.

- [ ] **Step 5: Run the email tests to verify GREEN**

Run:

```bash
uv run pytest app/tests/email/test_email_renderer.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit the branded email**

```bash
git add app/tests/email/test_email_renderer.py app/core/email/renderer.py app/static/templates/emails/admin_temporary_password.html
git commit -m "feat: brand temporary password email for RxVita"
```

---

### Task 4: Cross-Surface Regression Verification

**Files:**
- Verify only; do not modify unrelated failing fixtures or user changes.

**Interfaces:**
- Consumes: Deliverables from Tasks 1-3.
- Produces: Evidence that the new brand contract passes and any unrelated pre-existing failure is reported separately.

- [ ] **Step 1: Run all directly affected static UI tests**

Run:

```bash
node --test app/tests/static_ui/brand-theme.test.mjs app/tests/static_ui/login.test.mjs app/tests/static_ui/sidebar.test.mjs app/tests/static_ui/dashboard.test.mjs app/tests/static_ui/user-management.test.mjs app/tests/static_ui/task-management.test.mjs app/tests/static_ui/supplement-ranking.test.mjs
```

Expected: all listed theme, login, sidebar, dashboard, user, task, and ranking tests pass. The administrator-management suite is exercised by the complete-suite step below, where its existing unrelated fixture failure can be reported separately.

- [ ] **Step 2: Run the email renderer tests**

Run:

```bash
uv run pytest app/tests/email/test_email_renderer.py -q
```

Expected: `2 passed`.

- [ ] **Step 3: Run the complete static UI suite for regression visibility**

Run:

```bash
node --test app/tests/static_ui/*.test.mjs
```

Expected: all new brand tests pass. The known unrelated password-reset confirmation fixture may remain the sole failure until its separate task is addressed.

- [ ] **Step 4: Verify exact change scope and file integrity**

Run:

```bash
git diff --check
git status --short
rg -n "#1c64f2|#1554d1|#1d4ed8|#eff6ff|28, ?100, ?242|\[Ozcoding AI Health\]" app/static/css app/static/templates app/core/email app/tests/static_ui app/tests/email
```

Expected: `git diff --check` exits zero; the search returns no legacy brand matches in the scoped files; status contains no accidental files beyond the intended commits and pre-existing user changes.

- [ ] **Step 5: Review the browser-visible entry points manually if a local server is already available**

Check `login.html`, `dashboard.html`, `user-management.html`, `screen-4-admin-management.html`, `screen-5-task-management.html`, and `supplement-ranking.html` at desktop width. Confirm white/grey structure is unchanged, sidebar logo is not distorted, teal active/hover/focus states are visible, semantic status colors remain, and no layout shift hides the SMTP settings button. Do not start or reconfigure external services solely for this visual check.
