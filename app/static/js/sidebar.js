import { initializeNavigation } from "./navigation.js";

const SIDEBAR_URL = new URL("../templates/partials/sidebar.html", import.meta.url);
const PAGE_SECTIONS = Object.freeze({
  "dashboard.html": "dashboard",
  "user-management.html": "users",
  "screen-4-admin-management.html": "admins",
  "screen-5-task-management.html": "tasks",
});

export function getActiveSection(pathname, fallbackSection) {
  const filename = pathname?.split("/").pop();
  return PAGE_SECTIONS[filename] ?? fallbackSection;
}

export function markActiveNavigation(sidebar, activeSection) {
  sidebar.querySelectorAll("[data-nav]").forEach((link) => {
    const isActive = link.dataset.nav === activeSection;
    link.classList.toggle("is-active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

export async function loadSidebar(root = document, fetcher = fetch) {
  const placeholder = root.querySelector("[data-sidebar]");
  if (!placeholder) return null;

  try {
    const response = await fetcher(SIDEBAR_URL);
    if (!response.ok) throw new Error(`sidebar request failed: ${response.status}`);

    const template = root.createElement("template");
    template.innerHTML = (await response.text()).trim();
    const sidebar = template.content.firstElementChild;
    if (!sidebar || sidebar.tagName !== "ASIDE") throw new Error("sidebar partial must have one aside root");

    const activeSection = getActiveSection(root.location?.pathname, placeholder.dataset.activeNav);
    markActiveNavigation(sidebar, activeSection);
    initializeNavigation(sidebar);
    placeholder.replaceWith(sidebar);
    return sidebar;
  } catch (error) {
    placeholder.dataset.sidebarError = "true";
    placeholder.textContent = "관리자 메뉴를 불러오지 못했습니다.";
    console.error(error);
    return null;
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => loadSidebar(), { once: true });
  } else {
    loadSidebar();
  }
}
