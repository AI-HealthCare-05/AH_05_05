import test from "node:test";
import assert from "node:assert/strict";

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
