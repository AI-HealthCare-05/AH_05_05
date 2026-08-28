import { post, session } from "./api.js";

const TARGETS = Object.freeze({
  dashboard: "dashboard.html",
  users: "user-management.html",
  admins: "screen-4-admin-management.html",
  tasks: "screen-5-task-management.html",
  "supplement-ranking": "supplement-ranking.html",
  logout: "login.html",
});

export function getNavigationTarget(section) {
  return TARGETS[section] ?? TARGETS.dashboard;
}

export function initializeNavigation(root = document) {
  root.querySelectorAll("[data-nav]").forEach((link) => {
    link.href = getNavigationTarget(link.dataset.nav);
    if (link.dataset.nav === "logout") {
      link.addEventListener("click", handleLogout);
    }
  });
}

/**
 * 리프레시 쿠키를 서버에서 지우고 로컬 세션도 비운다.
 *
 * 액세스 토큰은 JWT 라 서버가 만료 전에 폐기하지 못한다. 프론트가 확실히 지워야
 * 같은 브라우저에서 다음 사람이 이어서 쓰지 못한다.
 */
async function handleLogout(event) {
  event.preventDefault();
  const target = event.currentTarget.href;
  try {
    await post("/admin/auth/logout");
  } catch {
    // 이미 만료됐거나 네트워크가 끊겨도 로컬 세션은 반드시 지운다.
  } finally {
    session.clear();
    window.location.href = target;
  }
}

if (typeof document !== "undefined") initializeNavigation();
