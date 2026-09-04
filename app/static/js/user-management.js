import {
  ApiError,
  escapeHtml,
  formatDate,
  get,
  patch,
  requireLogin,
  session,
  statusBadgeClass,
  statusLabel,
  statusValue,
  tableState,
} from "./api.js";
import { openOverlay, showToast } from "./overlay.js";

const COLUMN_COUNT = 7;

/**
 * 목 데이터 시절의 클라이언트 필터. 지금은 서버가 keyword·status 로 거른다.
 * 정적 UI 테스트가 이 함수를 검증하고 있어 그대로 둔다.
 */
export function filterUsers(users, query, status) {
  const term = query.trim().toLowerCase();
  return users.filter((user) => {
    const matchesTerm = !term || `${user.id} ${user.name} ${user.email}`.toLowerCase().includes(term);
    return matchesTerm && (status === "전체" || user.status === status);
  });
}

export function suspendUser(users, memberId) {
  return users.map((user) => (user.id === memberId ? { ...user, status: "정지" } : { ...user }));
}

export function formatUserIdLabel(userId) {
  return `(회원 ID : ${userId})`;
}

export function getPaginationState(totalCount, requestedPage, pageSize) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const currentPage = Math.min(Math.max(1, requestedPage), totalPages);
  const firstPage = Math.min(Math.max(1, currentPage - 2), Math.max(1, totalPages - 4));
  const lastPage = Math.min(totalPages, firstPage + 4);
  const pages = Array.from({ length: lastPage - firstPage + 1 }, (_, index) => firstPage + index);

  return {
    currentPage,
    totalPages,
    pages,
    hasPrevious: currentPage > 1,
    hasNext: currentPage < totalPages,
  };
}

export function buildUserListQuery(name, email, status, page, size) {
  return {
    name: name.trim(),
    email: email.trim(),
    status: statusValue(status),
    page,
    size,
  };
}

export function getUserDetailAction(status) {
  if (status === "ACTIVE") {
    return {
      label: "계정 정지",
      nextStatus: "SUSPENDED",
      className: "ui-button ui-button-danger",
      requiresConfirmation: true,
    };
  }
  if (status === "SUSPENDED") {
    return {
      label: "활성화",
      nextStatus: "ACTIVE",
      className: "ui-button ui-button-primary",
      requiresConfirmation: false,
    };
  }
  return null;
}

export function formatUserTotal(totalCount) {
  return typeof totalCount === "number" ? `총 ${totalCount}명` : "총 -명";
}

/** 화면에 그려진 현재 페이지. */
let currentItems = [];

/** 값이 없는 칸의 표기. 빈 칸으로 두면 조회가 안 된 것인지 값이 없는 것인지 구분되지 않는다. */
const EMPTY_CELL = "-";

/**
 * 상세 패널의 상태 문구. 목록은 "활성"·"정지" 로 짧게 쓰지만 패널은 "회원"을 붙인다.
 * 색 규칙은 목록과 같은 statusBadgeClass 를 쓴다.
 */
const DETAIL_STATUS_LABELS = {
  ACTIVE: "활성 회원",
  SUSPENDED: "정지 회원",
  PENDING: "대기 회원",
  WITHDRAWN: "탈퇴 회원",
};

function detailStatusLabel(status) {
  return DETAIL_STATUS_LABELS[status] ?? statusLabel(status);
}

function rowMarkup(user, canViewDetail) {
  const label = statusLabel(user.status);
  const detailButtonState = canViewDetail
    ? ""
    : 'disabled aria-disabled="true" title="ADMIN 권한만 상세 정보를 볼 수 있습니다."';
  return `
      <tr data-member-id="${user.userId}">
        <td>${user.userId}</td>
        <td><strong>${escapeHtml(user.name)}</strong></td>
        <td>${escapeHtml(user.email)}</td>
        <td>${user.phone ? escapeHtml(user.phone) : EMPTY_CELL}</td>
        <td>${formatDate(user.createdAt)}</td>
        <td><span class="status-badge status-${statusBadgeClass(user.status)}">${label}</span></td>
        <td class="flex gap-1 py-2"><button class="ui-link-button" type="button" data-user-detail="${user.userId}" ${detailButtonState}>상세 보기</button></td>
      </tr>`;
}

/**
 * 오버레이 HTML 은 openOverlay 가 fetch 로 가져오고 그 경로에는 캐시 버스팅이 없다.
 * 이 패널은 구성이 바뀌었으므로(하드코딩 제거·항목 교체) 호출부에서 쿼리를 붙인다.
 * 붙이지 않으면 브라우저가 옛 HTML 을 써서 하드 리로드해야만 정상 동작한다.
 */
const USER_DETAIL_OVERLAY_URL = "overlay-user-detail.html";

/**
 * 회원 상세 패널을 연다.
 *
 * 정지에 성공하면 같은 함수를 다시 불러 새 데이터로 패널을 그린다. 배지와 버튼이
 * 즉시 바뀌어야 하는데, openOverlay 가 열 때 이전 패널을 닫으므로 별도 정리는 없다.
 * 목록도 함께 다시 읽는다 — 패널만 갱신하면 뒤의 목록이 옛 상태로 남는다.
 */
async function openUserDetail(userId, reloadList) {
  const user = await get(`/admin/users/${userId}`);
  const action = getUserDetailAction(user.status);

  const applyStatusChange = async () => {
    if (!action) return;
    try {
      await patch("/admin/users/status", { userIds: [userId], status: action.nextStatus });
      await reloadList();
      await openUserDetail(userId, reloadList);
      const completedAction = action.nextStatus === "ACTIVE" ? "활성화" : "정지";
      showToast(`${user.name} 계정을 ${completedAction}했습니다.`);
    } catch (error) {
      const fallback = action.nextStatus === "ACTIVE" ? "활성화 처리에 실패했습니다." : "정지 처리에 실패했습니다.";
      const message = error instanceof ApiError ? error.message : fallback;
      showToast(message, "error");
    }
  };

  const overlay = await openOverlay(USER_DETAIL_OVERLAY_URL, {
    onConfirm: async () => {
      if (!action) return;
      if (action.requiresConfirmation) {
        const confirmOverlay = await openOverlay("overlay-user-suspend-confirm.html", {
          onConfirm: applyStatusChange,
        });
        // 상세를 거쳐 열리지만 목록이 최신순이라, 확인 창에도 대상을 다시 적는다.
        confirmOverlay.querySelector("[data-confirm-name]").textContent = user.name;
        confirmOverlay.querySelector("[data-confirm-email]").textContent = user.email;
        return;
      }
      await applyStatusChange();
    },
  });

  const badge = overlay.querySelector("[data-user-status]");
  badge.textContent = detailStatusLabel(user.status);
  badge.className = `status-badge status-${statusBadgeClass(user.status)}`;

  overlay.querySelector("[data-user-name]").textContent = user.name;
  overlay.querySelector("[data-user-id]").textContent = formatUserIdLabel(user.userId);
  overlay.querySelector("[data-user-email]").textContent = user.email;
  overlay.querySelector("[data-user-phone]").textContent = user.phone || EMPTY_CELL;
  overlay.querySelector("[data-user-joined]").textContent = formatDate(user.createdAt) || EMPTY_CELL;

  const actionButton = overlay.querySelector("[data-overlay-confirm]");
  if (action) {
    actionButton.textContent = action.label;
    actionButton.className = action.className;
  } else {
    actionButton.disabled = true;
    actionButton.title = "상태를 변경할 수 없는 회원입니다";
  }

  return overlay;
}

function initializeUserManagement() {
  const tableBody = document.querySelector("[data-user-rows]");
  if (!tableBody) return;
  if (!requireLogin()) return;

  const nameSearch = document.querySelector("[data-user-name-search]");
  const emailSearch = document.querySelector("[data-user-email-search]");
  const status = document.querySelector("[data-user-status]");
  const pageSizeSelect = document.querySelector("[data-user-page-size]");
  const total = document.querySelector("[data-user-total]");
  const pagination = document.querySelector("[data-user-pagination]");
  const canViewDetail = session.isAdminRole();
  let currentPage = 1;

  const renderPagination = (totalCount) => {
    const state = getPaginationState(totalCount, currentPage, Number(pageSizeSelect.value));
    pagination.innerHTML = `
      <button class="ui-button" type="button" data-user-page="${state.currentPage - 1}" ${state.hasPrevious ? "" : "disabled"}>이전</button>
      <div class="user-pagination-pages">
        ${state.pages
          .map(
            (pageNumber) =>
              `<button class="ui-button user-page-button${pageNumber === state.currentPage ? " is-active" : ""}" type="button" data-user-page="${pageNumber}" ${pageNumber === state.currentPage ? 'aria-current="page"' : ""}>${pageNumber}</button>`,
          )
          .join("")}
      </div>
      <button class="ui-button" type="button" data-user-page="${state.currentPage + 1}" ${state.hasNext ? "" : "disabled"}>다음</button>`;
  };

  const load = async () => {
    tableState.loading(tableBody, COLUMN_COUNT);
    try {
      const pageSize = Number(pageSizeSelect.value);
      const page = await get(
        "/admin/users",
        buildUserListQuery(nameSearch.value, emailSearch.value, status.value, currentPage, pageSize),
      );
      const paginationState = getPaginationState(page.totalCount, currentPage, pageSize);
      if (paginationState.currentPage !== currentPage) {
        currentPage = paginationState.currentPage;
        await load();
        return;
      }

      currentItems = page.items;
      total.textContent = formatUserTotal(page.totalCount);
      renderPagination(page.totalCount);

      if (!currentItems.length) {
        tableState.empty(tableBody, COLUMN_COUNT, "조건에 맞는 회원이 없습니다.");
        return;
      }
      tableBody.innerHTML = currentItems.map((user) => rowMarkup(user, canViewDetail)).join("");
    } catch (error) {
      currentItems = [];
      total.textContent = formatUserTotal(null);
      pagination.innerHTML = "";
      const message = error instanceof ApiError ? error.message : "회원 목록을 불러오지 못했습니다.";
      tableState.error(tableBody, COLUMN_COUNT, message);
    }
  };

  // 입력할 때마다 요청을 보내면 글자 수만큼 호출된다. 잠시 멈춘 뒤에 조회한다.
  let searchTimer;
  const scheduleSearch = () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      currentPage = 1;
      load();
    }, 300);
  };
  nameSearch.addEventListener("input", scheduleSearch);
  emailSearch.addEventListener("input", scheduleSearch);
  status.addEventListener("change", () => {
    currentPage = 1;
    load();
  });
  pageSizeSelect.addEventListener("change", () => {
    currentPage = 1;
    load();
  });
  document.querySelector("[data-user-reset]").addEventListener("click", () => {
    nameSearch.value = "";
    emailSearch.value = "";
    status.selectedIndex = 0;
    currentPage = 1;
    load();
  });

  pagination.addEventListener("click", (event) => {
    const button = event.target.closest("[data-user-page]");
    if (!button || button.disabled) return;
    currentPage = Number(button.dataset.userPage);
    load();
  });

  tableBody.addEventListener("click", async (event) => {
    if (event.target.closest("[data-retry]")) {
      load();
      return;
    }

    const button = event.target.closest("[data-user-detail]");
    if (!button) return;
    const userId = Number(button.dataset.userDetail);

    try {
      await openUserDetail(userId, load);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "회원 정보를 불러오지 못했습니다.";
      showToast(message, "error");
    }
  });

  load();
}

if (typeof document !== "undefined") initializeUserManagement();
