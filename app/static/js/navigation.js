const TARGETS = Object.freeze({
  dashboard: "dashboard.html",
  users: "user-management.html",
  admins: "screen-4-admin-management.html",
  tasks: "screen-5-task-management.html",
  logout: "login.html",
});

export function getNavigationTarget(section) {
  return TARGETS[section] ?? TARGETS.dashboard;
}

export function initializeNavigation(root = document) {
  root.querySelectorAll("[data-nav]").forEach((link) => {
    link.href = getNavigationTarget(link.dataset.nav);
    if (link.dataset.nav === "logout") {
      link.addEventListener("click", () => window.sessionStorage.removeItem("adminAuthenticated"));
    }
  });
}

if (typeof document !== "undefined") initializeNavigation();
