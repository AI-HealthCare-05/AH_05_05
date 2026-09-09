import { escapeHtml, get, requireLogin, tableState } from "./api.js";

const TYPE_VALUES = { OCR: "OCR", ALARM: "ALARM", EMAIL: "EMAIL" };
const STATUS_VALUES = {
  진행중: "PROCESSING",
  성공: "COMPLETED",
  실패: "FAILED",
  "진행 대기": "QUEUED",
  "재시도 대기": "RETRY_WAITING",
  취소: "CANCELLED",
};
const STATUS_LABELS = { QUEUED: "대기", PROCESSING: "진행 중", RETRY_WAITING: "재시도 대기", COMPLETED: "성공", FAILED: "실패", CANCELLED: "취소" };
const TASK_PAGE_SIZE = 20;

export function buildTaskQuery({ keyword, type, status, startDate, endDate, page = 1, size = TASK_PAGE_SIZE }) {
  return { keyword: keyword.trim(), jobType: TYPE_VALUES[type] ?? "", status: STATUS_VALUES[status] ?? "", startDate, endDate, page, size };
}

export function formatTaskTotal(totalCount) {
  return typeof totalCount === "number" ? `총 ${totalCount}건` : "총 -건";
}

export function getTaskPaginationState(totalCount, requestedPage, pageSize = TASK_PAGE_SIZE) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const currentPage = Math.min(Math.max(1, requestedPage), totalPages);
  const firstPage = Math.min(Math.max(1, currentPage - 2), Math.max(1, totalPages - 4));
  const lastPage = Math.min(totalPages, firstPage + 4);
  return {
    currentPage,
    totalPages,
    pages: Array.from({ length: lastPage - firstPage + 1 }, (_, index) => firstPage + index),
    hasPrevious: currentPage > 1,
    hasNext: currentPage < totalPages,
  };
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
  const pagination = document.querySelector("[data-task-pagination]");
  const pageSizeSelect = document.querySelector("[data-task-page-size]");
  const total = document.querySelector("[data-task-total]");
  const today = localDateValue(new Date());
  let currentPage = 1;

  const renderPagination = (totalCount) => {
    if (!totalCount) {
      pagination.innerHTML = "";
      return;
    }
    const state = getTaskPaginationState(totalCount, currentPage, Number(pageSizeSelect.value));
    pagination.innerHTML = `
      <button class="ui-button" type="button" data-task-page="${state.currentPage - 1}" ${state.hasPrevious ? "" : "disabled"}>이전</button>
      <div class="task-pagination-pages">
        ${state.pages.map((pageNumber) => `<button class="ui-button task-page-button${pageNumber === state.currentPage ? " is-active" : ""}" type="button" data-task-page="${pageNumber}" ${pageNumber === state.currentPage ? 'aria-current="page"' : ""}>${pageNumber}</button>`).join("")}
      </div>
      <button class="ui-button" type="button" data-task-page="${state.currentPage + 1}" ${state.hasNext ? "" : "disabled"}>다음</button>`;
  };

  const loadJobs = async () => {
    if (!startDate.value) startDate.value = today;
    if (!endDate.value) endDate.value = today;
    if (!validateTaskDateRange(startDate.value, endDate)) return;
    const previousRows = tbody.innerHTML;
    searchButton.disabled = true;
    try {
      const [jobsResponse, statsResponse] = await Promise.all([
        get("/admin/jobs", buildTaskQuery({ keyword: search.value, type: type.value, status: status.value, startDate: startDate.value, endDate: endDate.value, page: currentPage, size: Number(pageSizeSelect.value) })),
        get("/admin/jobs/stats", { startDate: startDate.value, endDate: endDate.value }),
      ]);
      const paginationState = getTaskPaginationState(jobsResponse.totalCount ?? 0, currentPage, Number(pageSizeSelect.value));
      if (paginationState.currentPage !== currentPage) {
        currentPage = paginationState.currentPage;
        await loadJobs();
        return;
      }
      renderJobs(tbody, jobsResponse.items ?? []);
      total.textContent = formatTaskTotal(jobsResponse.totalCount ?? 0);
      renderPagination(jobsResponse.totalCount ?? 0);
      renderTaskStats(document, statsResponse.counts);
    } catch {
      tbody.innerHTML = previousRows;
      total.textContent = formatTaskTotal(null);
      pagination.innerHTML = "";
      window.alert("작업 목록 조회에 실패했습니다.");
    } finally {
      searchButton.disabled = false;
    }
  };

  startDate.value = today;
  endDate.value = today;
  tableState.loading(tbody, 6, "오늘 작업을 조회하는 중…");

  endDate.addEventListener("change", () => validateTaskDateRange(startDate.value, endDate));
  searchButton.addEventListener("click", () => {
    currentPage = 1;
    loadJobs();
  });
  resetButton.addEventListener("click", () => {
    search.value = "";
    type.value = "작업유형";
    status.value = "상태";
    startDate.value = today;
    endDate.value = today;
    currentPage = 1;
  });
  pagination.addEventListener("click", (event) => {
    const button = event.target.closest("[data-task-page]");
    if (!button || button.disabled) return;
    currentPage = Number(button.dataset.taskPage);
    loadJobs();
  });
  pageSizeSelect.addEventListener("change", () => {
    currentPage = 1;
    loadJobs();
  });

  void loadJobs();
}

if (typeof document !== "undefined") initializeTaskManagement();
