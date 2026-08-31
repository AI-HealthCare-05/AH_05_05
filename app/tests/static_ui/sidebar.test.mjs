import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("markActiveNavigation marks only the current section", async () => {
  const { markActiveNavigation } = await import("../../static/js/sidebar.js");
  const links = ["dashboard", "users", "admins", "tasks"].map((section) => ({
    dataset: { nav: section },
    classList: {
      active: false,
      toggle(_className, enabled) {
        this.active = enabled;
      },
    },
    attributes: new Map(),
    setAttribute(name, value) {
      this.attributes.set(name, value);
    },
    removeAttribute(name) {
      this.attributes.delete(name);
    },
  }));
  const sidebar = { querySelectorAll: () => links };

  markActiveNavigation(sidebar, "admins");

  assert.deepEqual(links.map((link) => link.classList.active), [false, false, true, false]);
  assert.deepEqual(links.map((link) => link.attributes.get("aria-current")), [undefined, undefined, "page", undefined]);
});

test("loadSidebar replaces the placeholder and initializes the active link", async () => {
  const { loadSidebar } = await import("../../static/js/sidebar.js");
  const link = {
    dataset: { nav: "admins" },
    classList: { toggle(_className, enabled) { this.active = enabled; } },
    attributes: new Map(),
    setAttribute(name, value) { this.attributes.set(name, value); },
    removeAttribute(name) { this.attributes.delete(name); },
    addEventListener() {},
  };
  const sidebar = { tagName: "ASIDE", querySelectorAll: () => [link] };
  let replacement = null;
  const placeholder = {
    dataset: { activeNav: "dashboard" },
    replaceWith(element) { replacement = element; },
  };
  const root = {
    location: { pathname: "/templates/screen-4-admin-management.html" },
    querySelector: () => placeholder,
    createElement: () => ({ content: { firstElementChild: sidebar }, innerHTML: "" }),
  };
  const fetcher = async () => ({ ok: true, text: async () => "<aside></aside>" });

  const loaded = await loadSidebar(root, fetcher);

  assert.equal(loaded, sidebar);
  assert.equal(replacement, sidebar);
  assert.equal(link.classList.active, true);
  assert.equal(link.attributes.get("aria-current"), "page");
  assert.equal(link.href, "screen-4-admin-management.html");
});

test("loadSidebar bypasses stale browser cache for the shared partial", async () => {
  const { loadSidebar } = await import("../../static/js/sidebar.js");
  const sidebar = { tagName: "ASIDE", querySelectorAll: () => [] };
  const placeholder = {
    dataset: {},
    replaceWith() {},
  };
  const root = {
    location: { pathname: "/templates/dashboard.html" },
    querySelector: () => placeholder,
    createElement: () => ({ content: { firstElementChild: sidebar }, innerHTML: "" }),
  };
  let requestOptions;
  const fetcher = async (_url, options) => {
    requestOptions = options;
    return { ok: true, text: async () => "<aside></aside>" };
  };

  await loadSidebar(root, fetcher);

  assert.equal(requestOptions.cache, "no-store");
});

test("sidebar cache-busts the navigation module that owns menu targets", async () => {
  const source = await readFile(
    new URL("../../static/js/sidebar.js", import.meta.url),
    "utf8",
  );

  assert.match(source, /from "\.\/navigation\.js\?v=[^"]+"/);
});

test("loadSidebar leaves a visible message when the partial request fails", async () => {
  const { loadSidebar } = await import("../../static/js/sidebar.js");
  const placeholder = { dataset: {}, textContent: "" };
  const root = { querySelector: () => placeholder };
  const fetcher = async () => ({ ok: false, status: 500 });
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    const loaded = await loadSidebar(root, fetcher);

    assert.equal(loaded, null);
    assert.equal(placeholder.dataset.sidebarError, "true");
    assert.equal(placeholder.textContent, "관리자 메뉴를 불러오지 못했습니다.");
  } finally {
    console.error = originalConsoleError;
  }
});

test("configureSettingsButton removes the settings control for STAFF", async () => {
  const { configureSettingsButton } = await import("../../static/js/sidebar.js");
  let removed = false;
  const button = { remove() { removed = true; } };
  const sidebar = { querySelector: () => button };

  configureSettingsButton(sidebar, false, () => assert.fail("STAFF must not open settings"));

  assert.equal(removed, true);
});

test("configureSettingsButton lets ADMIN open SMTP settings", async () => {
  const { configureSettingsButton } = await import("../../static/js/sidebar.js");
  let clickHandler;
  let opened = false;
  const button = { addEventListener(_event, handler) { clickHandler = handler; } };
  const sidebar = { querySelector: () => button };

  configureSettingsButton(sidebar, true, () => { opened = true; });
  clickHandler();

  assert.equal(opened, true);
});

test("shared sidebar uses the RxVita symbol with an administrator label", async () => {
  const html = await readFile(new URL("../../static/templates/partials/sidebar.html", import.meta.url), "utf8");
  const managementStyles = await readFile(new URL("../../static/css/management.css", import.meta.url), "utf8");

  assert.match(html, /class="sidebar-brand-logo-frame"/);
  assert.match(html, /<img[^>]+class="sidebar-brand-logo"[^>]+src="\.\.\/images\/rxvita-logo-ai-chat-navy\.png"[^>]+alt="RxVita">/);
  assert.match(html, /<span class="sidebar-brand-title">관리자<\/span>/);
  assert.match(html, /data-smtp-settings/);
  assert.match(managementStyles, /\.sidebar-brand-logo-frame\s*\{[^}]*overflow:\s*hidden;/s);
  assert.match(managementStyles, /\.sidebar-brand-logo\s*\{[^}]*position:\s*absolute;[^}]*width:\s*auto;/s);
});

test("administrator display name prefers the signed-in profile name", async () => {
  const { getAdminDisplayName, getAdminRoleLabel } = await import("../../static/js/sidebar.js");

  assert.equal(getAdminDisplayName({ name: "김관리" }), "김관리");
  assert.equal(getAdminDisplayName({ email: "admin@rxvita.test" }), "admin@rxvita.test");
  assert.equal(getAdminDisplayName({}), "관리자");
  assert.equal(getAdminRoleLabel("ADMIN"), "ADMIN");
  assert.equal(getAdminRoleLabel("STAFF"), "STAFF");
  assert.equal(getAdminRoleLabel("AUDITOR"), "AUDITOR");
  assert.equal(getAdminRoleLabel(), "권한 미지정");
});

test("administrator pages expose a shared fixed top area", async () => {
  const source = await readFile(new URL("../../static/js/sidebar.js", import.meta.url), "utf8");
  const managementStyles = await readFile(new URL("../../static/css/management.css", import.meta.url), "utf8");
  const pages = [
    "dashboard.html",
    "user-management.html",
    "screen-4-admin-management.html",
    "screen-5-task-management.html",
    "supplement-ranking.html",
  ];

  assert.match(source, /data-admin-topbar/);
  assert.match(source, /data-admin-topbar-brand/);
  assert.match(source, /data-login-user-name/);
  assert.match(source, /data-login-user-role/);
  assert.match(source, /userName\.textContent\s*=\s*getAdminDisplayName\(admin\)/);
  assert.match(source, /userRole\.textContent\s*=\s*`\(\$\{getAdminRoleLabel\(admin\.role\)\}\)`/);
  assert.match(source, /relocateSidebarBrand\(sidebar, root\)/);
  assert.match(managementStyles, /\.admin-topbar\s*\{[^}]*position:\s*fixed;[^}]*top:\s*0;[^}]*right:\s*0;/s);
  assert.match(managementStyles, /\.admin-topbar-brand\s*\{[^}]*display:\s*flex;/s);
  assert.match(managementStyles, /\.admin-topbar\s+\.sidebar-brand\s*\{[^}]*width:\s*auto;/s);
  assert.match(managementStyles, /\.admin-topbar-user-name\s*\{[^}]*font-weight:\s*800;/s);
  assert.match(managementStyles, /body\.management-page,[^}]*body\.dashboard-page\s*\{[^}]*padding-top:\s*64px;/s);

  for (const page of pages) {
    const html = await readFile(new URL(`../../static/templates/${page}`, import.meta.url), "utf8");
    assert.match(html, /src="\.\.\/js\/sidebar\.js\?v=20260831-7"/, page);
  }
});

test("sidebar brand moves into the left side of the top area", async () => {
  const { relocateSidebarBrand } = await import("../../static/js/sidebar.js");
  const settingsButton = { style: { marginLeft: "auto" } };
  const brand = { id: "brand" };
  const moved = [];
  const sidebar = { querySelector: (selector) => ({ ".sidebar-brand": brand, "[data-smtp-settings]": settingsButton })[selector] ?? null };
  const brandTarget = { append(element) { moved.push(["left", element]); } };
  const userTarget = { append(element) { moved.push(["right", element]); } };
  const root = { querySelector: (selector) => ({ "[data-admin-topbar-brand]": brandTarget, ".admin-topbar-user": userTarget })[selector] ?? null };

  assert.equal(relocateSidebarBrand(sidebar, root), true);
  assert.deepEqual(moved, [["left", brand], ["right", settingsButton]]);
  assert.equal(settingsButton.style.marginLeft, "0px");
});
