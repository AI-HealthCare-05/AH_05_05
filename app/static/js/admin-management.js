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

/**
 * 역할을 바꿀 수 없는 이유. 없으면 바꿀 수 있다.
 *
 * 서버가 409 로 막는 조건을 화면에서 미리 알려준다. 409 를 받고 나서 알려주는 것보다
 * 애초에 못 누르게 하는 편이 낫다. 대기(PENDING)는 막지 않는다 — 첫 로그인 전 역할
 * 오지정을 정정할 유일한 경로로 서버가 일부러 열어둔 상태다.
 */
export function roleChangeBlockedReason(admin, currentAdminId) {
  if (admin.adminId === currentAdminId) return "본인 역할은 변경할 수 없습니다";
  if (admin.status === "SUSPENDED" || admin.status === "WITHDRAWN") {
    return "정지된 계정은 역할을 변경할 수 없습니다";
  }
  return null;
}

/**
 * 오버레이 HTML 은 openOverlay 가 fetch 로 가져온다. 그 경로에는 캐시 버스팅이 없어
 * 파일을 고쳐도 브라우저가 옛 HTML 을 쓸 수 있다. 내용이 바뀐 오버레이만 호출부에서
 * 쿼리를 붙인다. (js 모듈 import 경로 전반의 캐시 문제는 #128 에서 다룬다)
 */
const ROLE_OVERLAY_URL = "overlay-admin-edit.html?v=20260827-3";
// PR #118 에서 문구를 실제 동작에 맞게 고쳤다("재설정 링크 발송" -> 임시 비밀번호 발송).
// 캐시 무효화가 없어 옛 문구가 그대로 노출된다. 기능은 동작하므로 긴급하지는 않았다.
const PASSWORD_RESET_OVERLAY_URL = "overlay-password-reset.html?v=20260827-3";

/**
 * 409 를 어디에 보여줄지 정한다. 역할 선택 자체의 문제면 오류칸, 그 외는 토스트다.
 * 문구는 항상 서버 message 를 그대로 쓴다 — 화면에서 새로 만들면 서버와 어긋난다.
 */
const ROLE_ERROR_IN_FIELD = new Set(["SAME_ROLE", "CANNOT_CHANGE_OWN_ROLE"]);

/** 역할 변경 오버레이를 연다. 성공하면 목록을 다시 읽는다. */
async function openRoleOverlay(admin, reloadList) {
  const overlay = await openOverlay(ROLE_OVERLAY_URL, {
    onConfirm: async (panel) => {
      const select = panel.querySelector("[name='role']");
      const errorSlot = panel.querySelector("[data-error-for='role']");
      const confirmButton = panel.querySelector("[data-overlay-confirm]");
      const nextRole = roleValue(select.value);

      errorSlot.textContent = "";
      const originalLabel = confirmButton.textContent;
      confirmButton.disabled = true;
      confirmButton.textContent = "변경 중…";

      try {
        await patch(`/admin/accounts/${admin.adminId}/role`, { role: nextRole });
        closeOverlay();
        await reloadList();
        showToast(`${admin.name}의 역할을 ${roleLabel(nextRole)}로 변경했습니다.`);
      } catch (error) {
        if (!(error instanceof ApiError)) {
          showToast("역할을 변경하지 못했습니다.", "error");
          return;
        }
        if (ROLE_ERROR_IN_FIELD.has(error.code)) errorSlot.textContent = error.message;
        else showToast(error.message, "error");
      } finally {
        confirmButton.disabled = false;
        confirmButton.textContent = originalLabel;
      }
    },
  });

  overlay.querySelector("[data-admin-name]").textContent = admin.name;
  overlay.querySelector("[data-admin-email]").textContent = admin.email;

  const select = overlay.querySelector("[name='role']");
  const confirmButton = overlay.querySelector("[data-overlay-confirm]");
  select.value = roleLabel(admin.role);

  // 같은 역할이면 서버가 409 SAME_ROLE 로 막는다. 굳이 보게 하지 않는다.
  const syncConfirmState = () => {
    confirmButton.disabled = roleValue(select.value) === admin.role;
  };
  select.addEventListener("change", syncConfirmState);
  syncConfirmState();

  return overlay;
}

function rowMarkup(admin, canManage, currentAdminId) {
  // 되돌릴 수 없는 동작(재설정·정지)은 danger 로 갈라 둔다. 조회 동작과 같은 모양이면
  // 옆 버튼을 잘못 누른다. 비활성 색은 CSS 의 :disabled 가 danger 위에 덮는다.
  const suspended = admin.status === "SUSPENDED";
  const blockedReason = roleChangeBlockedReason(admin, currentAdminId);
  const actions = canManage
    ? `<button class="ui-link-button" data-admin-action="edit" data-admin-id="${admin.adminId}"${
         blockedReason ? ` disabled title="${escapeHtml(blockedReason)}"` : ""
       }>수정</button>
       <button class="ui-link-button ui-link-button-danger" data-admin-action="reset" data-admin-id="${admin.adminId}">재설정</button>
       <button class="ui-link-button ui-link-button-danger" data-admin-action="stop" data-admin-id="${admin.adminId}"${
         suspended ? ' disabled title="이미 정지된 관리자입니다"' : ""
       }>${suspended ? "정지됨" : "정지"}</button>`
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
  // 본인 행의 「수정」을 잠그려면 내가 누구인지 알아야 한다. 로그인 때 저장한 프로필을 쓴다.
  const currentAdminId = session.admin().adminId;

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
      tbody.innerHTML = currentItems.map((admin) => rowMarkup(admin, canManage, currentAdminId)).join("");
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

  document.querySelector("[data-admin-reset]")?.addEventListener("click", () => {
    search.value = "";
    role.value = "전체";
    status.value = "전체";
    // 입력 디바운스가 걸려 있으면 방금 지운 값으로 한 번 더 조회된다.
    window.clearTimeout(searchTimer);
    load();
  });

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
      await openOverlay(PASSWORD_RESET_OVERLAY_URL, {
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

    if (button.dataset.adminAction === "edit") {
      if (!admin) return;
      await openRoleOverlay(admin, load);
    }
  });

  load();
}

if (typeof document !== "undefined") initializeAdminManagement();
