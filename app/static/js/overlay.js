let activeOverlay;
let previousFocus;

export function serializeCsv(rows) {
  const escapeCell = (value) => {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  return `\uFEFF${rows.map((row) => row.map(escapeCell).join(",")).join("\r\n")}`;
}

export function downloadCsv(filename, rows) {
  if (!rows.length) return false;
  const blob = new Blob([serializeCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  return true;
}

export function showToast(message, type = "success") {
  let region = document.querySelector("[data-toast-region]");
  if (!region) {
    region = document.createElement("div");
    region.className = "toast-region";
    region.dataset.toastRegion = "";
    region.setAttribute("aria-live", "polite");
    document.body.append(region);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  region.append(toast);
  window.setTimeout(() => toast.remove(), 2800);
  return toast;
}

export function closeOverlay() {
  if (!activeOverlay) return;
  activeOverlay.remove();
  activeOverlay = undefined;
  document.body.classList.remove("overlay-open");
  previousFocus?.focus?.();
}

export async function openOverlay(path, options = {}) {
  closeOverlay();
  previousFocus = document.activeElement;
  const response = await fetch(path);
  if (!response.ok) throw new Error(`오버레이를 불러오지 못했습니다: ${response.status}`);
  const source = await response.text();
  const parsed = new DOMParser().parseFromString(source, "text/html");
  const panel = parsed.querySelector("[data-overlay-panel]") ?? parsed.body.firstElementChild;
  if (!panel) throw new Error("오버레이 콘텐츠가 없습니다.");

  activeOverlay = document.createElement("div");
  activeOverlay.className = "overlay-host";
  activeOverlay.dataset.overlayHost = "";
  activeOverlay.innerHTML = panel.outerHTML;
  document.body.append(activeOverlay);
  document.body.classList.add("overlay-open");

  activeOverlay.addEventListener("click", (event) => {
    if (event.target === activeOverlay || event.target.closest("[data-overlay-close]")) closeOverlay();
  });
  activeOverlay.querySelector("[data-overlay-confirm]")?.addEventListener("click", () => options.onConfirm?.(activeOverlay));
  activeOverlay.querySelector("input, select, textarea, button")?.focus();
  return activeOverlay;
}

if (typeof document !== "undefined") {
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeOverlay();
  });
}
