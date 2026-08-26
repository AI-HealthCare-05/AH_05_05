import {
  ApiError,
  escapeHtml,
  get,
  patch,
  post,
  requireLogin,
  roleLabel,
  roleValue,
  session,
  statusBadgeClass,
  statusLabel,
  statusValue,
  tableState,
} from "./api.js";
import { closeOverlay, openOverlay, showToast } from "./overlay.js";

const COLUMN_COUNT = 6;
// 화면에 페이지 이동 UI 가 없어 1페이지만 보여준다.
const PAGE_SIZE = 50;

/**
 * 목 데이터 시절의 클라이언트 필터·변형 함수들.
 * 지금은 서버가 거르고 상태 변경도 API 가 하지만, 정적 UI 테스트가 검증하고 있어 그대로 둔다.
 */
export function filterAdmins(admins, query, role, status) {
  const term = query.trim().toLowerCase();
  return admins.filter(
    (admin) =>
      (!term || `${admin.name} ${admin.email}`.toLowerCase().includes(term)) &&
      (role === "전체" || admin.role === role) &&
      (status === "전체" || admin.status === status),
  );
}

export function validateAdminInput({ name, email }) {
  const errors = {};
  if (!name.trim()) errors.name = "관리자 이름을 입력해주세요.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errors.email = "올바른 이메일 주소를 입력해주세요.";
  return { valid: Object.keys(errors).length === 0, errors };
}

export function updateAdminStatus(admins, adminId, status) {
  return admins.map((admin) => (admin.id === adminId ? { ...admin, status } : { ...admin }));
}

let currentItems = [];

function rowMarkup(admin, canManage) {
  // 역할 변경 API 가 없어 수정은 연동하지 않는다. 버튼은 남기되 비활성화한다.
  const actions = canManage
    ? `<button class="ui-link-button" data-admin-action="edit" data-admin-id="${admin.adminId}" disabled
               title="역할 변경 API가 아직 없습니다">수정</button>
       <button class="ui-link-button" data-admin-action="reset" data-admin-id="${admin.adminId}">재설정</button>
       <button class="ui-link-button" data-admin-action="stop" data-admin-id="${admin.adminId}">정지</button>`
    : "";

  return `<tr>
      <td>${admin.adminId}</td>
      <td><strong>${escapeHtml(admin.name)}</strong></td>
      <td>${escapeHtml(admin.email)}</td>
      <td>${roleLabel(admin.role)}</td>
      <td><span class="status-badge status-${statusBadgeClass(admin.status)}">${statusLabel(admin.status)}</span></td>
      <td class="flex gap-1 py-2">${actions}</td>
    </tr>`;
}

function initializeAdminManagement() {
  const tbody = document.querySelector("[data-admin-rows]");
  if (!tbody) return;
  if (!requireLogin()) return;

  const search = document.querySelector("[data-admin-search]");
  const role = document.querySelector("[data-admin-role]");
  const status = document.querySelector("[data-admin-status]");
  const registerButton = document.querySelector("[data-admin-register]");

  // 등록·정지는 ADMIN 전용이다(권한 매트릭스). STAFF 에게는 버튼을 숨긴다.
  const canManage = session.isAdminRole();
  if (!canManage && registerButton) registerButton.hidden = true;

  const load = async () => {
    tableState.loading(tbody, COLUMN_COUNT);
    try {
      const page = await get("/admin/accounts", {
        keyword: search.value.trim(),
        role: roleValue(role.value),
        // 관리자에는 WITHDRAWN 을 쓰지 않는다. 화면 선택지도 활성·정지뿐이다.
        status: statusValue(status.value),
        page: 1,
        size: PAGE_SIZE,
      });
      currentItems = page.items;

      if (!currentItems.length) {
        tableState.empty(tbody, COLUMN_COUNT, "조건에 맞는 관리자가 없습니다.");
        return;
      }
      tbody.innerHTML = currentItems.map((admin) => rowMarkup(admin, canManage)).join("");
    } catch (error) {
      currentItems = [];
      const message = error instanceof ApiError ? error.message : "관리자 목록을 불러오지 못했습니다.";
      tableState.error(tbody, COLUMN_COUNT, message);
    }
  };

  let searchTimer;
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(load, 300);
  });
  [role, status].forEach((control) => control.addEventListener("change", load));

  registerButton?.addEventListener("click", async () => {
    await openOverlay("overlay-admin-register.html", {
      onConfirm: async (overlay) => {
        const name = overlay.querySelector("[name='name']").value;
        const email = overlay.querySelector("[name='email']").value;
        const result = validateAdminInput({ name, email });
        overlay.querySelector("[data-error-for='name']").textContent = result.errors.name ?? "";
        overlay.querySelector("[data-error-for='email']").textContent = result.errors.email ?? "";
        if (!result.valid) return;

        try {
          const created = await post("/admin/accounts", {
            name: name.trim(),
            email: email.trim(),
            role: roleValue(overlay.querySelector("[name='role']").value) || "STAFF",
          });
          closeOverlay();
          await load();

          // 계정은 만들어졌지만 임시 비밀번호를 전달할 방법이 없는 상태다. 반드시 알린다.
          if (created.emailSent) {
            showToast(`관리자를 등록했습니다. 임시 비밀번호를 ${created.email}로 보냈습니다.`);
          } else {
            showToast("관리자는 등록됐지만 메일 발송에 실패했습니다. 임시 비밀번호 재발송이 필요합니다.", "error");
          }
        } catch (error) {
          const message = error instanceof ApiError ? error.message : "관리자 등록에 실패했습니다.";
          showToast(message, "error");
        }
      },
    });
  });

  tbody.addEventListener("click", async (event) => {
    if (event.target.closest("[data-retry]")) {
      load();
      return;
    }

    const button = event.target.closest("[data-admin-action]");
    if (!button || button.disabled) return;
    const adminId = Number(button.dataset.adminId);
    const admin = currentItems.find((item) => item.adminId === adminId);

    if (button.dataset.adminAction === "reset") {
      await openOverlay("overlay-password-reset.html", {
        onConfirm: async () => {
          try {
            const result = await post(`/admin/accounts/${adminId}/password/reset`);
            closeOverlay();
            await load();
            // 재설정 "링크"가 아니라 임시 비밀번호를 보낸다. 문구를 실제 동작에 맞춘다.
            if (result.emailSent) {
              showToast(`${result.email}로 임시 비밀번호를 발송했습니다.`);
            } else {
              showToast("비밀번호는 재발급됐지만 메일 발송에 실패했습니다.", "error");
            }
          } catch (error) {
            const message = error instanceof ApiError ? error.message : "임시 비밀번호 발송에 실패했습니다.";
            showToast(message, "error");
          }
        },
      });
      return;
    }

    if (button.dataset.adminAction === "stop") {
      await openOverlay("overlay-admin-status-confirm.html", {
        onConfirm: async () => {
          try {
            await patch("/admin/accounts/status", { adminIds: [adminId], status: "SUSPENDED" });
            closeOverlay();
            await load();
            showToast("관리자 계정을 정지했습니다.");
          } catch (error) {
            // LAST_ACTIVE_ADMIN / CANNOT_SUSPEND_SELF 모두 409 다. 서버 문구를 그대로 띄운다.
            const message = error instanceof ApiError ? error.message : "정지 처리에 실패했습니다.";
            showToast(message, "error");
          }
        },
      });
      return;
    }

    // edit 은 역할 변경 API 가 없어 연동하지 않는다. 버튼이 disabled 라 여기까지 오지 않는다.
    showToast("관리자 정보 수정은 아직 지원하지 않습니다.", "error");
    if (admin) return;
  });

  load();
}

if (typeof document !== "undefined") initializeAdminManagement();
