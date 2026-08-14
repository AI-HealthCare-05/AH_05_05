export function selectPeriod(periods, selected) {
  return periods.map((period) => (period === selected ? "active" : "inactive"));
}

export function formatRefreshTime(date) {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `최종 점검: ${hours}:${minutes}`;
}

function initializePeriodButtons() {
  const buttons = [...document.querySelectorAll("[data-period]")];
  const periods = buttons.map((button) => button.dataset.period);

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const states = selectPeriod(periods, button.dataset.period);

      buttons.forEach((periodButton, index) => {
        const isActive = states[index] === "active";
        periodButton.classList.toggle("is-active", isActive);
        periodButton.setAttribute("aria-pressed", String(isActive));
      });
    });
  });
}

function initializeRefreshButton() {
  const refreshButton = document.querySelector("[data-refresh]");
  const refreshTime = document.querySelector("[data-refresh-time]");

  refreshButton?.addEventListener("click", () => {
    if (refreshTime) refreshTime.textContent = formatRefreshTime(new Date());
  });
}

function initializeLogout() {
  const logoutLink = document.querySelector("[data-logout]");

  logoutLink?.addEventListener("click", () => {
    window.sessionStorage.removeItem("adminAuthenticated");
  });
}

if (typeof document !== "undefined") {
  initializePeriodButtons();
  initializeRefreshButton();
  initializeLogout();
}
