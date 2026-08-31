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
