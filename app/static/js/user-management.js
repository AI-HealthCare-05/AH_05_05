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
import { closeOverlay, downloadCsv, openOverlay, showToast } from "./overlay.js";

const COLUMN_COUNT = 8;
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

/** 화면에 그려진 현재 페이지. CSV 내보내기가 이 값을 쓴다. */
let currentItems = [];

function rowMarkup(user) {
  const label = statusLabel(user.status);
  return `
      <tr data-member-id="${user.userId}">
        <td><input type="checkbox" aria-label="${escapeHtml(user.name)} 선택"></td>
        <td>${user.userId}</td>
        <td><strong>${escapeHtml(user.name)}</strong></td>
        <td>${escapeHtml(user.email)}</td>
        <td>-</td>
        <td>${formatDate(user.createdAt)}</td>
        <td><span class="status-badge status-${statusBadgeClass(user.status)}">${label}</span></td>
        <td><button class="ui-link-button" type="button" data-user-detail="${user.userId}">상세 보기</button></td>
      </tr>`;
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

  document.querySelector("[data-user-export]").addEventListener("click", () => {
    const ok = downloadCsv("users.csv", [
      ["회원 ID", "이름", "이메일", "가입일", "상태"],
      ...currentItems.map((user) => [
        user.userId,
        user.name,
        user.email,
        formatDate(user.createdAt),
        statusLabel(user.status),
      ]),
    ]);
    if (!ok) showToast("내보낼 회원이 없습니다.", "error");
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
      const user = await get(`/admin/users/${userId}`);
      const overlay = await openOverlay("overlay-user-detail.html", {
        onConfirm: async () => {
          await openOverlay("overlay-user-suspend-confirm.html", {
            onConfirm: async () => {
              try {
                await patch("/admin/users/status", { userIds: [userId], status: "SUSPENDED" });
                closeOverlay();
                // 로컬 배열을 고치지 않고 서버 상태를 다시 읽는다.
                await load();
                showToast(`${user.name} 계정을 정지했습니다.`);
              } catch (error) {
                const message = error instanceof ApiError ? error.message : "정지 처리에 실패했습니다.";
                showToast(message, "error");
              }
            },
          });
        },
      });
      // 오버레이에 자리가 있는 항목만 채운다. 새 항목을 만들지 않는다.
      overlay.querySelector("[data-user-name]").textContent = user.name;
      overlay.querySelector("[data-user-id]").textContent = user.userId;
      overlay.querySelector("[data-user-email]").textContent = user.email;
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "회원 정보를 불러오지 못했습니다.";
      showToast(message, "error");
    }
  });

  load();
}

if (typeof document !== "undefined") initializeUserManagement();
