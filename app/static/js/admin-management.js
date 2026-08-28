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

// 재설정은 메일 발송에 실패해도 되돌리지 않는다. 비밀번호는 이미 바뀌었고 상태도
// PENDING 으로 내려가 있어, 대상자는 새 임시 비밀번호를 모르면 로그인할 수 없다.
// 그 사실을 문구에 담지 않으면 "메일만 안 갔구나" 로 읽고 넘어간다.
export const RESET_MAIL_FAILED_MESSAGE =
  "비밀번호는 재설정되었으나 메일 발송에 실패했습니다. 대상 관리자는 현재 로그인할 수 없으니 「재설정」을 다시 눌러 주세요.";

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
 * 「수정」을 누를 수 없는 이유. 없으면 누를 수 있다.
 *
 * 역할 변경과 기준이 다르다. 오버레이가 역할 전용에서 수정 화면으로 넓어지면서
 * **본인 행도 열어야 한다** — 이름과 비밀번호는 본인이 바꾸는 것이 정상이다.
 * 역할 select 만 본인일 때 잠기며, 그 판정은 roleChangeBlockedReason 이 맡는다.
 *
 * STAFF 는 남의 행을 못 고친다(서버도 403 으로 막는다). 숨기지 않고 비활성으로 두는
 * 이유는 행마다 갈리는 제약이라 숨기면 작업 열 정렬이 행마다 흔들리기 때문이다.
 */
export function editBlockedReason(admin, currentAdminId, currentRole) {
  if (admin.status === "SUSPENDED" || admin.status === "WITHDRAWN") {
    return "정지된 계정은 수정할 수 없습니다";
  }
  if (currentRole !== "ADMIN" && admin.adminId !== currentAdminId) {
    return "본인 계정만 수정할 수 있습니다";
  }
  return null;
}

/**
 * 작업 열에 놓을 상태 전환 버튼. 토글 스위치가 아니라 **버튼 하나가 교체**된다.
 *
 * 「활성화」가 ACTIVE 가 아니라 PENDING 을 보내는 것은 오타가 아니다. 정지 해제된
 * 계정은 본인이 로그인해야 ACTIVE 가 된다는 결정에 따른 것이고, 전환은 서버의 로그인
 * 처리에서 일어난다. 그래서 해제 직후에는 목록에 「대기」로 보인다.
 *
 * 관리자 계정에는 WITHDRAWN 을 쓰지 않지만, 값이 들어오면 서버가 어느 쪽으로도
 * 막으므로 버튼을 내지 않는다.
 */
export function statusAction(admin, currentAdminId) {
  if (admin.status === "SUSPENDED") {
    // 정지된 계정이 본인일 수는 없다. 정지되면 로그인 자체가 막힌다.
    return { action: "activate", label: "활성화", nextStatus: "PENDING", danger: false, disabledReason: null };
  }
  if (admin.status === "ACTIVE" || admin.status === "PENDING") {
    return {
      action: "suspend",
      label: "정지",
      nextStatus: "SUSPENDED",
      danger: true,
      // 서버가 409 CANNOT_SUSPEND_SELF 로 막는다. 눌러봐야 항상 실패하므로 미리 잠근다.
      disabledReason: admin.adminId === currentAdminId ? "본인 계정은 정지할 수 없습니다" : null,
    };
  }
  return null;
}

/**
 * 오버레이 HTML 은 openOverlay 가 fetch 로 가져온다. 그 경로에는 캐시 버스팅이 없어
 * 파일을 고쳐도 브라우저가 옛 HTML 을 쓸 수 있다. 내용이 바뀐 오버레이만 호출부에서
 * 쿼리를 붙인다. (js 모듈 import 경로 전반의 캐시 문제는 #128 에서 다룬다)
 */
const EDIT_OVERLAY_URL = "overlay-admin-edit.html";
// PR #118 에서 문구를 실제 동작에 맞게 고쳤다("재설정 링크 발송" -> 임시 비밀번호 발송).
// 캐시 무효화가 없어 옛 문구가 그대로 노출된다. 기능은 동작하므로 긴급하지는 않았다.
const PASSWORD_RESET_OVERLAY_URL = "overlay-password-reset.html";

/**
 * 서버 오류를 어느 칸에 붙일지 정한다. 해당 칸이 없으면 토스트로 흘린다.
 * 문구는 항상 서버 message 를 그대로 쓴다 — 화면에서 새로 만들면 서버와 어긋난다.
 */
const ERROR_FIELD_BY_CODE = {
  SAME_ROLE: "role",
  CANNOT_CHANGE_OWN_ROLE: "role",
  INVALID_PASSWORD: "currentPassword",
  SAME_AS_CURRENT: "newPassword",
};

const EDIT_FIELDS = ["name", "role", "currentPassword", "newPassword", "newPasswordConfirm"];

/**
 * 수정 오버레이의 프론트 검증.
 *
 * 비밀번호 정책(8자·대소문자·숫자·특수문자)은 서버가 판정한다. 같은 규칙을 여기서 다시
 * 구현하면 정책이 바뀔 때 두 곳이 어긋난다. 비어 있는지와 확인 값이 맞는지만 본다.
 *
 * 비밀번호 세 칸은 **한 칸이라도 채워졌을 때만** 검사한다. 이름만 고치러 들어온 사람에게
 * 비밀번호를 요구하면 안 된다.
 */
export function validateAdminEdit({ name, currentPassword, newPassword, newPasswordConfirm }) {
  const errors = {};
  if (!name.trim()) errors.name = "관리자 이름을 입력해주세요.";

  if (currentPassword || newPassword || newPasswordConfirm) {
    if (!currentPassword) errors.currentPassword = "현재 비밀번호를 입력해주세요.";
    if (!newPassword) errors.newPassword = "새 비밀번호를 입력해주세요.";
    if (!newPasswordConfirm) errors.newPasswordConfirm = "새 비밀번호를 한 번 더 입력해주세요.";
    else if (newPassword && newPassword !== newPasswordConfirm) {
      errors.newPasswordConfirm = "새 비밀번호가 일치하지 않습니다.";
    }
  }

  return { valid: Object.keys(errors).length === 0, errors };
}

/**
 * 오버레이에서 무엇을 보여줄지 정한다. 권한 매트릭스를 한 곳에 모아 둔다.
 *
 * 비밀번호 칸은 **본인 행에서만** 낸다. 변경 API 의 대상은 토큰의 sub 라 남의 행에서
 * 열어두면 ADMIN 이 남의 비밀번호를 바꾸는 줄 알고 자기 것을 바꾸게 된다. 남의 비밀번호를
 * 다루는 수단은 「재설정」(임시 비밀번호 재발송)뿐이다.
 *
 * 역할 칸은 ADMIN 이 남의 행을 볼 때만 낸다. 본인 역할은 서버가 409 로 막는다.
 */
export function editOverlayVisibility(admin, currentAdminId, currentRole) {
  const isSelf = admin.adminId === currentAdminId;
  const isAdmin = currentRole === "ADMIN";
  // 「재설정」도 본인 행에서는 감춘다. 자기 비밀번호를 임시 비밀번호로 갈아끼울 이유가 없고,
  // 바로 위 비밀번호 칸에서 직접 바꾸면 된다.
  return { role: isAdmin && !isSelf, password: isSelf, reset: isAdmin && !isSelf };
}

/** 권한별로 감출 블록과 그 선택자. applyEditOverlayVisibility 와 테스트가 함께 쓴다. */
export const EDIT_OVERLAY_SECTIONS = [
  ["role", "[data-role-field]"],
  ["password", "[data-password-section]"],
  ["reset", "[data-reset-section]"],
];

/**
 * 권한상 보이면 안 되는 블록을 DOM 에서 **제거**한다.
 *
 * hidden 속성을 쓰지 않는다. hidden 은 UA 스타일시트의 `[hidden] { display: none }`
 * 으로 동작하는데 작성자 스타일시트가 항상 이긴다. 이 블록들은 각각
 * `.overlay-field`(display:grid) · Tailwind `.grid`(display:grid) ·
 * `.overlay-actions`(display:flex) 를 달고 있어, hidden 을 걸어도 그대로 보였다.
 * 실제로 남의 행 오버레이에 비밀번호 칸이 노출됐다.
 *
 * 제거하면 CSS 가 되살릴 수 없고 "요소가 없다"로 검증할 수 있다. 순수 함수의 반환값만
 * 보는 테스트는 이 버그를 못 잡는다.
 */
export function applyEditOverlayVisibility(panel, visibility) {
  for (const [key, selector] of EDIT_OVERLAY_SECTIONS) {
    if (!visibility[key]) panel.querySelector(selector)?.remove();
  }
}

/**
 * 임시 비밀번호를 재발송한다. 목록의 「재설정」과 수정 오버레이의 「재설정」이 함께 쓴다.
 *
 * 되돌릴 수 없는 동작이라 확인 오버레이를 먼저 띄운다. 성공하면 대상 계정은 PENDING 이
 * 되고 기존 비밀번호는 못 쓴다.
 */
async function resetTemporaryPassword(adminId, reloadList) {
  await openOverlay(PASSWORD_RESET_OVERLAY_URL, {
    onConfirm: async () => {
      try {
        const result = await post(`/admin/accounts/${adminId}/password/reset`);
        closeOverlay();
        await reloadList();
        // 재설정 "링크"가 아니라 임시 비밀번호를 보낸다. 문구를 실제 동작에 맞춘다.
        if (result.emailSent) {
          showToast(`${result.email}로 임시 비밀번호를 발송했습니다.`);
        } else {
          // "발송 실패"만 쓰면 상대가 잠겼다는 사실이 안 보인다. 서버는 발송에
          // 실패해도 되돌리지 않고 비밀번호를 이미 바꿔놨다(reset_password).
          showToast(RESET_MAIL_FAILED_MESSAGE, "error");
        }
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "임시 비밀번호 발송에 실패했습니다.";
        showToast(message, "error");
      }
    },
  });
}

/** 관리자 수정 오버레이를 연다. 성공하면 목록을 다시 읽는다. */
async function openEditOverlay(admin, { currentAdminId, currentRole }, reloadList) {
  const visibility = editOverlayVisibility(admin, currentAdminId, currentRole);

  const overlay = await openOverlay(EDIT_OVERLAY_URL, {
    onConfirm: async (panel) => {
      const valueOf = (field) => panel.querySelector(`[name='${field}']`)?.value ?? "";
      const setFieldError = (field, message = "") => {
        const input = panel.querySelector(`[name='${field}']`);
        const slot = panel.querySelector(`[data-error-for='${field}']`);
        input?.setAttribute("aria-invalid", String(Boolean(message)));
        if (slot) slot.textContent = message;
      };

      const name = valueOf("name");
      const currentPassword = valueOf("currentPassword");
      const newPassword = valueOf("newPassword");

      const result = validateAdminEdit({
        name,
        currentPassword,
        newPassword,
        newPasswordConfirm: valueOf("newPasswordConfirm"),
      });
      EDIT_FIELDS.forEach((field) => setFieldError(field, result.errors[field]));
      if (!result.valid) return;

      const nextRole = visibility.role ? roleValue(valueOf("role")) : admin.role;
      const changed = [];

      const confirmButton = panel.querySelector("[data-overlay-confirm]");
      const originalLabel = confirmButton.textContent;
      confirmButton.disabled = true;
      confirmButton.textContent = "저장 중…";

      try {
        // 하나씩 순서대로 보낸다. 첫 실패에서 멈추므로 앞의 것은 이미 반영돼 있다.
        // 세 변경을 한 번에 담는 API 가 없어 원자성은 없다. 어디까지 됐는지는
        // 목록을 다시 읽어 보여준다.
        if (name.trim() !== admin.name) {
          await patch(`/admin/accounts/${admin.adminId}/name`, { name: name.trim() });
          changed.push("이름");
        }
        if (nextRole !== admin.role) {
          await patch(`/admin/accounts/${admin.adminId}/role`, { role: nextRole });
          changed.push("역할");
        }
        if (visibility.password && newPassword) {
          // 확인 칸은 보내지 않는다. API 는 currentPassword·newPassword 만 받는다.
          await patch("/admin/accounts/password", { currentPassword, newPassword });
          changed.push("비밀번호");
        }

        closeOverlay();
        await reloadList();
        showToast(changed.length ? `${changed.join("·")}을(를) 변경했습니다.` : "변경한 내용이 없습니다.");
      } catch (error) {
        if (!(error instanceof ApiError)) {
          showToast("수정하지 못했습니다.", "error");
          return;
        }
        // 422 는 공통 핸들러가 field 를 함께 준다. 없으면 코드로 칸을 찾는다.
        const field = ERROR_FIELD_BY_CODE[error.code] ?? (EDIT_FIELDS.includes(error.field) ? error.field : null);
        if (field && panel.querySelector(`[data-error-for='${field}']`)) setFieldError(field, error.message);
        else showToast(error.message, "error");
      } finally {
        confirmButton.disabled = false;
        confirmButton.textContent = originalLabel;
      }
    },
  });

  overlay.querySelector("[data-admin-email]").textContent = admin.email;
  overlay.querySelector("[name='name']").value = admin.name;
  overlay.querySelector("[name='role']").value = roleLabel(admin.role);

  // 권한 때문에 불가한 블록은 DOM 에서 지운다. hidden 은 CSS 에 짓밟힌다(위 주석 참고).
  applyEditOverlayVisibility(overlay, visibility);

  overlay.querySelector("[data-admin-edit-reset]")?.addEventListener("click", async () => {
    // 확인 오버레이가 열리면서 이 패널이 닫힌다. 입력하던 내용은 버려지므로,
    // 확인 문구에서 무슨 일이 일어나는지 분명히 알려야 한다.
    closeOverlay();
    await resetTemporaryPassword(admin.adminId, reloadList);
  });

  return overlay;
}

/**
 * 작업 열 버튼들. 노출 규칙이 두 가지로 갈린다.
 *
 * - 행마다 갈리는 제약(STAFF 가 보는 남의 행 「수정」)은 **비활성화**한다. 숨기면 작업
 *   열의 버튼 수가 행마다 달라져 정렬이 흔들린다.
 * - 역할 때문에 모든 행에서 균일하게 불가한 것(STAFF 의 정지·활성화·재설정)은 **숨긴다.**
 *   죽은 버튼이 열 전체를 채울 이유가 없다.
 *
 * 「재설정」은 여기 없다. 수정 오버레이 안으로 옮겼다. 목록에 두면 「수정」이 비활성인
 * 정지 계정에서 「재설정」만 활성으로 남아 어긋나고, 되돌릴 수 없는 동작이 한 번의
 * 클릭으로 닿는 자리에 있게 된다.
 *
 * 정지는 danger 로 갈라 둔다. 조회 동작과 같은 모양이면 옆 버튼을 잘못 누른다.
 * 비활성 색은 CSS 의 :disabled 가 danger 위에 덮는다.
 */
function actionsMarkup(admin, canManage, currentAdminId, currentRole) {
  const editBlocked = editBlockedReason(admin, currentAdminId, currentRole);
  const buttons = [
    `<button class="ui-link-button" data-admin-action="edit" data-admin-id="${admin.adminId}"${
      editBlocked ? ` disabled title="${escapeHtml(editBlocked)}"` : ""
    }>수정</button>`,
  ];

  if (!canManage) return buttons.join("\n       ");

  const transition = statusAction(admin, currentAdminId);
  if (transition) {
    buttons.push(
      `<button class="ui-link-button${transition.danger ? " ui-link-button-danger" : ""}" data-admin-action="${
        transition.action
      }" data-admin-id="${admin.adminId}"${
        transition.disabledReason ? ` disabled title="${escapeHtml(transition.disabledReason)}"` : ""
      }>${transition.label}</button>`,
    );
  }

  return buttons.join("\n       ");
}

function rowMarkup(admin, canManage, currentAdminId, currentRole) {
  return `<tr>
      <td>${admin.adminId}</td>
      <td><strong>${escapeHtml(admin.name)}</strong></td>
      <td>${escapeHtml(admin.email)}</td>
      <td>${roleLabel(admin.role)}</td>
      <td><span class="status-badge status-${statusBadgeClass(admin.status)}">${statusLabel(admin.status)}</span></td>
      <td class="flex gap-1 py-2">${actionsMarkup(admin, canManage, currentAdminId, currentRole)}</td>
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

  // 등록·정지·활성화·재설정은 ADMIN 전용이다(권한 매트릭스). STAFF 에게는 숨긴다.
  // **「수정」은 여기서 걸러내지 않는다.** STAFF 도 본인 것은 고칠 수 있어야 하는데,
  // 예전에는 canManage 가 false 면 작업 열을 통째로 비워 「수정」조차 못 봤다.
  const canManage = session.isAdminRole();
  if (!canManage && registerButton) registerButton.hidden = true;
  // 누구 행이 내 것인지 알아야 「수정」을 행마다 가를 수 있다. 로그인 때 저장한 프로필을 쓴다.
  const currentAdminId = session.admin().adminId;
  const currentRole = session.admin().role;

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
      tbody.innerHTML = currentItems
        .map((admin) => rowMarkup(admin, canManage, currentAdminId, currentRole))
        .join("");
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

    if (button.dataset.adminAction === "suspend") {
      await openOverlay("overlay-admin-status-confirm.html", {
        onConfirm: async () => {
          try {
            await patch("/admin/accounts/status", { adminIds: [adminId], status: "SUSPENDED" });
            closeOverlay();
            // 다시 그려야 버튼이 「활성화」로 바뀐다.
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

    if (button.dataset.adminAction === "activate") {
      if (!admin) return;
      // 확인 오버레이를 두지 않는다. 정지와 달리 되돌리기 쉽고(다시 정지하면 된다)
      // 잘못 눌러도 잃는 것이 없다.
      try {
        // ACTIVE 가 아니라 PENDING 이다. statusAction() 의 주석 참고 —
        // 해제된 계정은 본인이 로그인해야 ACTIVE 가 된다.
        const { nextStatus } = statusAction(admin, currentAdminId);
        await patch("/admin/accounts/status", { adminIds: [adminId], status: nextStatus });
        await load();
        showToast("관리자 계정을 활성화했습니다. 본인이 로그인하면 「활성」으로 바뀝니다.");
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "활성화에 실패했습니다.";
        showToast(message, "error");
      }
      return;
    }

    if (button.dataset.adminAction === "edit") {
      if (!admin) return;
      await openEditOverlay(admin, { currentAdminId, currentRole }, load);
    }
  });

  load();
}

if (typeof document !== "undefined") initializeAdminManagement();
