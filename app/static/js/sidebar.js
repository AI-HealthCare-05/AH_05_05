import { initializeNavigation } from "./navigation.js?v=20260903-1";
import { session } from "./api.js";
import { openSmtpSettings } from "./smtp-settings.js";

const SIDEBAR_URL = new URL("../templates/partials/sidebar.html", import.meta.url);
const PAGE_SECTIONS = Object.freeze({
  "dashboard.html": "dashboard",
  "user-management.html": "users",
  "screen-4-admin-management.html": "admins",
  "screen-5-task-management.html": "tasks",
  "common-code-management.html": "common-codes",
  "supplement-ranking.html": "supplement-ranking",
});

export function getActiveSection(pathname, fallbackSection) {
  const filename = pathname?.split("/").pop();
  return PAGE_SECTIONS[filename] ?? fallbackSection;
}

export function getAdminDisplayName(admin = {}) {
  const name = typeof admin.name === "string" ? admin.name.trim() : "";
  const email = typeof admin.email === "string" ? admin.email.trim() : "";
  return name || email || "관리자";
}

export function getAdminRoleLabel(role) {
  return role || "권한 미지정";
}

export function renderAdminTopbar(root = document, admin = session.admin()) {
  const existing = root.querySelector?.("[data-admin-topbar]");
  if (existing) return existing;
  if (!root.body?.prepend || !root.createElement) return null;

  const topbar = root.createElement("header");
  topbar.className = "admin-topbar";
  topbar.setAttribute("data-admin-topbar", "");
  topbar.setAttribute("aria-label", "관리자 상단 영역");

  const user = root.createElement("div");
  user.className = "admin-topbar-user";
  user.setAttribute("aria-label", "로그인 사용자");
  user.style.gap = "8px";

  const userName = root.createElement("strong");
  userName.className = "admin-topbar-user-name";
  userName.setAttribute("data-login-user-name", "");
  userName.textContent = getAdminDisplayName(admin);

  const userRole = root.createElement("span");
  userRole.className = "admin-topbar-user-role";
  userRole.setAttribute("data-login-user-role", "");
  userRole.textContent = `(${getAdminRoleLabel(admin.role)})`;

  user.append(userName, userRole);
  topbar.append(user);
  root.body.prepend(topbar);
  return topbar;
}

export function relocateSettingsButtonToTopbar(sidebar, root = document) {
  const settingsButton = sidebar?.querySelector?.("[data-smtp-settings]");
  const userTarget = root.querySelector?.(".admin-topbar-user");
  if (!settingsButton || !userTarget?.append) return false;
  if (settingsButton.style) settingsButton.style.marginLeft = "0px";
  userTarget.append(settingsButton);
  return true;
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
    relocateSettingsButtonToTopbar(sidebar, root);
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
  const initializeAdminChrome = () => {
    renderAdminTopbar();
    loadSidebar();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeAdminChrome, { once: true });
  } else {
    initializeAdminChrome();
  }
}
