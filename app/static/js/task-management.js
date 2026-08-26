import { escapeHtml, get, requireLogin, tableState } from "./api.js";

const TYPE_VALUES = { OCR: "OCR", LLM: "LLM", CHAT: "CHAT", ALARM: "ALARM" };
const STATUS_VALUES = {
  진행중: "PROCESSING",
  성공: "COMPLETED",
  실패: "FAILED",
  "진행 대기": "QUEUED",
  "재시도 대기": "RETRY_WAITING",
  취소: "CANCELLED",
};
const STATUS_LABELS = { QUEUED: "대기", PROCESSING: "진행 중", RETRY_WAITING: "재시도 대기", COMPLETED: "성공", FAILED: "실패", CANCELLED: "취소" };

export function buildTaskQuery({ keyword, type, status, startDate, endDate }) {
  return { keyword: keyword.trim(), jobType: TYPE_VALUES[type] ?? "", status: STATUS_VALUES[status] ?? "", startDate, endDate, page: 1, size: 100 };
}

export function validateTaskDateRange(startDate, endDateInput, alertFn = window.alert) {
  if (startDate && endDateInput.value && endDateInput.value < startDate) {
    alertFn("조회 기간이 올바르지 않습니다.");
    endDateInput.value = "";
    return false;
  }
  return true;
}

function localDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function statusClass(value) {
  if (value === "COMPLETED") return "active";
  if (value === "FAILED" || value === "CANCELLED") return "failed";
  return "processing";
}

function renderJobs(tbody, jobs) {
  if (!jobs.length) return tableState.empty(tbody, 6, "조회 결과가 없습니다.");
  tbody.innerHTML = jobs.map((job) => {
    const error = [job.errorCode, job.errorMessage].filter(Boolean).join(" - ") || "-";
    const userName = job.userName || (job.userId ? `사용자 #${job.userId}` : "시스템 자동");
    return `<tr><td><strong>${escapeHtml(job.jobId)}</strong></td><td>${escapeHtml(job.jobType)}</td><td>${escapeHtml(userName)}</td><td>${escapeHtml(formatDateTime(job.requestedAt))}</td><td><span class="status-badge status-${statusClass(job.status)}">${escapeHtml(STATUS_LABELS[job.status] ?? job.status)}</span></td><td>${escapeHtml(error)}</td></tr>`;
  }).join("");
}

export function renderTaskStats(root, counts) {
  const selectors = {
    QUEUED: "[data-task-count-queued]",
    PROCESSING: "[data-task-count-processing]",
    RETRY_WAITING: "[data-task-count-retry-waiting]",
    COMPLETED: "[data-task-count-completed]",
    FAILED: "[data-task-count-failed]",
    CANCELLED: "[data-task-count-cancelled]",
  };
  Object.entries(selectors).forEach(([jobStatus, selector]) => {
    root.querySelector(selector).textContent = String(counts?.[jobStatus] ?? 0);
  });
}

function initializeTaskManagement() {
  const tbody = document.querySelector("[data-task-rows]");
  if (!tbody || !requireLogin()) return;
  const search = document.querySelector("[data-task-search]");
  const type = document.querySelector("[data-task-type]");
  const status = document.querySelector("[data-task-status]");
  const startDate = document.querySelector("[data-task-start-date]");
  const endDate = document.querySelector("[data-task-end-date]");
  const searchButton = document.querySelector("[data-task-search-button]");
  const resetButton = document.querySelector("[data-task-reset]");
  const today = localDateValue(new Date());

  const loadJobs = async () => {
    if (!startDate.value) startDate.value = today;
    if (!endDate.value) endDate.value = today;
    if (!validateTaskDateRange(startDate.value, endDate)) return;
    const previousRows = tbody.innerHTML;
    searchButton.disabled = true;
    try {
      const [jobsResponse, statsResponse] = await Promise.all([
        get("/admin/jobs", buildTaskQuery({ keyword: search.value, type: type.value, status: status.value, startDate: startDate.value, endDate: endDate.value })),
        get("/admin/jobs/stats", { startDate: startDate.value, endDate: endDate.value }),
      ]);
      renderJobs(tbody, jobsResponse.items ?? []);
      renderTaskStats(document, statsResponse.counts);
    } catch {
      tbody.innerHTML = previousRows;
      window.alert("작업 목록 조회에 실패했습니다.");
    } finally {
      searchButton.disabled = false;
    }
  };

  startDate.value = today;
  endDate.value = today;
  tableState.loading(tbody, 6, "오늘 작업을 조회하는 중…");

  endDate.addEventListener("change", () => validateTaskDateRange(startDate.value, endDate));
  searchButton.addEventListener("click", loadJobs);
  resetButton.addEventListener("click", () => {
    search.value = "";
    type.value = "전체";
    status.value = "전체";
    startDate.value = today;
    endDate.value = today;
  });

  void loadJobs();
}

if (typeof document !== "undefined") initializeTaskManagement();
