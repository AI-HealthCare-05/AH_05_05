import {
  ApiError,
  escapeHtml,
  formatDate,
  get,
  patch,
  requireLogin,
  statusBadgeClass,
  statusLabel,
  statusValue,
  tableState,
} from "./api.js";
import { openOverlay, showToast } from "./overlay.js";

const COLUMN_COUNT = 7;
// 화면에 페이지 이동 UI 가 없어 1페이지만 보여준다. 디자인을 바꾸지 않기 위한 선택이다.
const PAGE_SIZE = 50;

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

function rowMarkup(user) {
  const label = statusLabel(user.status);
  return `
      <tr data-member-id="${user.userId}">
        <td>${user.userId}</td>
        <td><strong>${escapeHtml(user.name)}</strong></td>
        <td>${escapeHtml(user.email)}</td>
        <td>${user.phone ? escapeHtml(user.phone) : EMPTY_CELL}</td>
        <td>${formatDate(user.createdAt)}</td>
        <td><span class="status-badge status-${statusBadgeClass(user.status)}">${label}</span></td>
        <td class="flex gap-1 py-2"><button class="ui-link-button" type="button" data-user-detail="${user.userId}">상세 보기</button></td>
      </tr>`;
}

/**
 * 오버레이 HTML 은 openOverlay 가 fetch 로 가져오고 그 경로에는 캐시 버스팅이 없다.
 * 이 패널은 구성이 바뀌었으므로(하드코딩 제거·항목 교체) 호출부에서 쿼리를 붙인다.
 * 붙이지 않으면 브라우저가 옛 HTML 을 써서 하드 리로드해야만 정상 동작한다.
 */
const USER_DETAIL_OVERLAY_URL = "overlay-user-detail.html?v=20260827-2";

/**
 * 회원 상세 패널을 연다.
 *
 * 정지에 성공하면 같은 함수를 다시 불러 새 데이터로 패널을 그린다. 배지와 버튼이
 * 즉시 바뀌어야 하는데, openOverlay 가 열 때 이전 패널을 닫으므로 별도 정리는 없다.
 * 목록도 함께 다시 읽는다 — 패널만 갱신하면 뒤의 목록이 옛 상태로 남는다.
 */
async function openUserDetail(userId, reloadList) {
  const user = await get(`/admin/users/${userId}`);

  const overlay = await openOverlay(USER_DETAIL_OVERLAY_URL, {
    onConfirm: async () => {
      await openOverlay("overlay-user-suspend-confirm.html", {
        onConfirm: async () => {
          try {
            await patch("/admin/users/status", { userIds: [userId], status: "SUSPENDED" });
            await reloadList();
            await openUserDetail(userId, reloadList);
            showToast(`${user.name} 계정을 정지했습니다.`);
          } catch (error) {
            const message = error instanceof ApiError ? error.message : "정지 처리에 실패했습니다.";
            showToast(message, "error");
          }
        },
      });
    },
  });

  const badge = overlay.querySelector("[data-user-status]");
  badge.textContent = detailStatusLabel(user.status);
  badge.className = `status-badge status-${statusBadgeClass(user.status)}`;

  overlay.querySelector("[data-user-name]").textContent = user.name;
  overlay.querySelector("[data-user-id]").textContent = user.userId;
  overlay.querySelector("[data-user-email]").textContent = user.email;
  overlay.querySelector("[data-user-phone]").textContent = user.phone || EMPTY_CELL;
  overlay.querySelector("[data-user-joined]").textContent = formatDate(user.createdAt) || EMPTY_CELL;

  // 정지는 ACTIVE 인 회원에게만 걸 수 있다. 나머지 상태는 서버가 막으므로 버튼을 잠근다.
  const suspendButton = overlay.querySelector("[data-overlay-confirm]");
  if (user.status !== "ACTIVE") {
    suspendButton.disabled = true;
    if (user.status === "SUSPENDED") {
      suspendButton.textContent = "정지됨";
      suspendButton.title = "이미 정지된 회원입니다";
    } else {
      suspendButton.title = "정지할 수 있는 상태가 아닙니다";
    }
  }

  return overlay;
}

function initializeUserManagement() {
  const tableBody = document.querySelector("[data-user-rows]");
  if (!tableBody) return;
  if (!requireLogin()) return;

  const search = document.querySelector("[data-user-search]");
  const status = document.querySelector("[data-user-status]");

  const load = async () => {
    tableState.loading(tableBody, COLUMN_COUNT);
    try {
      const page = await get("/admin/users", {
        keyword: search.value.trim(),
        status: statusValue(status.value),
        page: 1,
        size: PAGE_SIZE,
      });
      currentItems = page.items;

      if (!currentItems.length) {
        tableState.empty(tableBody, COLUMN_COUNT, "조건에 맞는 회원이 없습니다.");
        return;
      }
      tableBody.innerHTML = currentItems.map(rowMarkup).join("");
    } catch (error) {
      currentItems = [];
      const message = error instanceof ApiError ? error.message : "회원 목록을 불러오지 못했습니다.";
      tableState.error(tableBody, COLUMN_COUNT, message);
    }
  };

  // 입력할 때마다 요청을 보내면 글자 수만큼 호출된다. 잠시 멈춘 뒤에 조회한다.
  let searchTimer;
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(load, 300);
  });
  status.addEventListener("change", load);
  document.querySelector("[data-user-reset]").addEventListener("click", () => {
    search.value = "";
    status.value = "전체";
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
