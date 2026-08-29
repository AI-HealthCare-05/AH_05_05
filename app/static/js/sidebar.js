import { initializeNavigation } from "./navigation.js?v=20260827-2";
import { session } from "./api.js";
import { openSmtpSettings } from "./smtp-settings.js";

const SIDEBAR_URL = new URL("../templates/partials/sidebar.html", import.meta.url);
const PAGE_SECTIONS = Object.freeze({
  "dashboard.html": "dashboard",
  "user-management.html": "users",
  "screen-4-admin-management.html": "admins",
  "screen-5-task-management.html": "tasks",
  "supplement-ranking.html": "supplement-ranking",
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

export function configureSettingsButton(
  sidebar,
  isAdmin = session.isAdminRole(),
  opener = openSmtpSettings,
) {
  const button = sidebar.querySelector?.("[data-smtp-settings]");
  if (!button) return;
  if (!isAdmin) {
    button.remove();
    return;
  }
  if (button.style) button.style.display = "flex";
  button.addEventListener("click", opener);
}

export async function loadSidebar(root = document, fetcher = fetch) {
  const placeholder = root.querySelector("[data-sidebar]");
  if (!placeholder) return null;

  try {
    // 공통 partial은 메뉴 구성이 자주 바뀌므로 브라우저의 휴리스틱 캐시를 사용하지 않는다.
    // 이전 sidebar.html이 남으면 새 메뉴가 소스와 컨테이너에 있어도 화면에는 보이지 않는다.
    const response = await fetcher(SIDEBAR_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`sidebar request failed: ${response.status}`);

    const template = root.createElement("template");
    template.innerHTML = (await response.text()).trim();
    const sidebar = template.content.firstElementChild;
    if (!sidebar || sidebar.tagName !== "ASIDE") throw new Error("sidebar partial must have one aside root");

    const activeSection = getActiveSection(root.location?.pathname, placeholder.dataset.activeNav);
    markActiveNavigation(sidebar, activeSection);
    initializeNavigation(sidebar);
    configureSettingsButton(sidebar);
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
