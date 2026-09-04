import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import * as adminManagement from "../../static/js/admin-management.js";
import {
  EDIT_OVERLAY_SECTIONS,
  applyEditOverlayVisibility,
  editOverlayVisibility,
  validateAdminEdit,
  RESET_MAIL_FAILED_MESSAGE,
  editBlockedReason,
  filterAdmins,
  roleChangeBlockedReason,
  statusAction,
  updateAdminStatus,
  validateAdminInput,
} from "../../static/js/admin-management.js";

const admins = [
  { id: "ADM-1001", name: "Dr. Sarah Connor", email: "s.connor@clinics.com", role: "최고 관리자", status: "활성" },
  { id: "ADM-1002", name: "Dr. Park", email: "park@ozcoding.ai", role: "일반 관리자", status: "정지" },
];

test("filterAdmins combines search, role and status filters", () => {
  assert.deepEqual(filterAdmins(admins, "park", "일반 관리자", "정지").map((admin) => admin.id), ["ADM-1002"]);
  assert.deepEqual(filterAdmins(admins, "clinics", "전체", "전체").map((admin) => admin.id), ["ADM-1001"]);
});

test("buildAdminListQuery sends separate name and email filters with pagination", () => {
  assert.deepEqual(
    adminManagement.buildAdminListQuery?.(" 김은미 ", " eunmi@ozcoding.ai ", "일반 관리자", "활성", 2, 50),
    {
      name: "김은미",
      email: "eunmi@ozcoding.ai",
      role: "STAFF",
      status: "ACTIVE",
      page: 2,
      size: 50,
    },
  );
});

test("getAdminPaginationState clamps the requested page and exposes five page buttons", () => {
  assert.deepEqual(adminManagement.getAdminPaginationState?.(260, 99, 50), {
    currentPage: 6,
    totalPages: 6,
    pages: [2, 3, 4, 5, 6],
    hasPrevious: true,
    hasNext: false,
  });
});

test("formatAdminTotal formats a count and a failed-load placeholder", () => {
  assert.equal(adminManagement.formatAdminTotal?.(27), "총 27명");
  assert.equal(adminManagement.formatAdminTotal?.(null), "총 -명");
});

test("resetAdminFilters restores the role and status placeholder options", () => {
  assert.equal(typeof adminManagement.resetAdminFilters, "function");
  const nameSearch = { value: "김은미" };
  const emailSearch = { value: "eunmi@ozcoding.ai" };
  const role = { value: "최고 관리자" };
  const status = { value: "활성" };

  adminManagement.resetAdminFilters(nameSearch, emailSearch, role, status);

  assert.equal(nameSearch.value, "");
  assert.equal(emailSearch.value, "");
  assert.equal(role.value, "권한");
  assert.equal(status.value, "상태");
});

test("admin management screen separates searches and places paging controls below the list", async () => {
  const templateUrl = new URL("../../static/templates/screen-4-admin-management.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  for (const hook of [
    "data-admin-name-search",
    "data-admin-email-search",
    "data-admin-pagination",
    "data-admin-total",
    "data-admin-page-size",
  ]) {
    assert.match(html, new RegExp(hook));
  }

  const tableEnd = html.indexOf("</table>");
  assert.ok(tableEnd < html.indexOf("data-admin-pagination"));
  assert.ok(tableEnd < html.indexOf("data-admin-total"));
  assert.ok(tableEnd < html.indexOf("data-admin-page-size"));
});

test("admin management page size offers twenty, fifty and one hundred items", async () => {
  const templateUrl = new URL("../../static/templates/screen-4-admin-management.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");
  const select = html.match(/<select id="admin-page-size"[\s\S]*?<\/select>/)?.[0] ?? "";

  assert.match(select, /<option value="20" selected>20개<\/option>/);
  assert.match(select, /<option value="50">50개<\/option>/);
  assert.match(select, /<option value="100">100개<\/option>/);
  assert.doesNotMatch(select, /value="1"|value="2"|value="5"/);
});

test("validateAdminInput rejects blank names and malformed emails", () => {
  assert.deepEqual(validateAdminInput({ name: " ", email: "not-email" }), {
    valid: false,
    errors: { name: "관리자 이름을 입력해주세요.", email: "올바른 이메일 주소를 입력해주세요." },
  });
});

test("validateAdminName applies the same rule as the user signup name", () => {
  for (const name of ["김진형", "KimJinhyeong", "山田", "홍길"]) {
    assert.equal(adminManagement.validateAdminName(name), null, name);
  }
  assert.equal(adminManagement.validateAdminName("가"), "이름을 두 글자 이상 입력해 주세요.");
  assert.equal(adminManagement.validateAdminName("가".repeat(21)), "이름은 20자 이하로 입력해 주세요.");
  for (const name of ["스모크2", "김 진형", "김철수!", "김철수😀"]) {
    assert.equal(adminManagement.validateAdminName(name), "이름에는 숫자, 공백, 특수문자를 사용할 수 없습니다.", name);
  }
  // 앞뒤 공백은 trim 되어 통과한다. 화면이 다듬어 보내고 서버가 공백을 거부한다.
  assert.equal(adminManagement.validateAdminName(" 홍길동 "), null);
});

test("validateAdminEdit rejects a name that breaks the rule", () => {
  const result = validateAdminEdit({ name: "스모크2", currentPassword: "", newPassword: "", newPasswordConfirm: "" });
  assert.equal(result.valid, false);
  assert.equal(result.errors.name, "이름에는 숫자, 공백, 특수문자를 사용할 수 없습니다.");
});

test("admin name inputs cap at twenty characters on both overlays", async () => {
  for (const [file, id] of [
    ["overlay-admin-register.html", "admin-name"],
    ["overlay-admin-edit.html", "admin-edit-name"],
  ]) {
    const html = await readFile(new URL(`../../static/templates/${file}`, import.meta.url), "utf8");
    const input = html.split("\n").find((line) => line.includes(`id="${id}"`));
    assert.match(input, /maxlength="20"/, `${file} ${id}`);
  }
});

test("suspend confirm overlays show which account is being suspended", async () => {
  for (const file of ["overlay-admin-status-confirm.html", "overlay-user-suspend-confirm.html"]) {
    const html = await readFile(new URL(`../../static/templates/${file}`, import.meta.url), "utf8");
    assert.match(html, /data-confirm-name/, file);
    assert.match(html, /data-confirm-email/, file);
  }
});

test("withSubmitLock ignores another submission while the first one is pending", async () => {
  assert.equal(typeof adminManagement.withSubmitLock, "function");
  const button = { disabled: false, textContent: "저장" };
  let release;
  let callCount = 0;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  const submit = () => {
    callCount += 1;
    return pending;
  };

  const first = adminManagement.withSubmitLock(button, "등록 중…", submit);
  const second = adminManagement.withSubmitLock(button, "등록 중…", submit);

  assert.equal(button.disabled, true);
  assert.equal(button.textContent, "등록 중…");
  assert.equal(callCount, 1);
  assert.equal(await second, undefined);

  release("created");
  assert.equal(await first, "created");
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, "저장");
});

test("roleChangeBlockedReason blocks the caller's own row", () => {
  assert.equal(
    roleChangeBlockedReason({ adminId: 3, status: "ACTIVE" }, 3),
    "본인 역할은 변경할 수 없습니다",
  );
});

test("roleChangeBlockedReason blocks suspended and withdrawn accounts", () => {
  assert.equal(
    roleChangeBlockedReason({ adminId: 4, status: "SUSPENDED" }, 3),
    "정지된 계정은 역할을 변경할 수 없습니다",
  );
  assert.equal(
    roleChangeBlockedReason({ adminId: 5, status: "WITHDRAWN" }, 3),
    "정지된 계정은 역할을 변경할 수 없습니다",
  );
});

test("roleChangeBlockedReason allows pending accounts", () => {
  // 첫 로그인 전 역할 오지정을 정정할 유일한 경로라 서버가 일부러 열어둔 상태다.
  assert.equal(roleChangeBlockedReason({ adminId: 22, status: "PENDING" }, 3), null);
});

test("roleChangeBlockedReason allows other active accounts", () => {
  assert.equal(roleChangeBlockedReason({ adminId: 28, status: "ACTIVE" }, 3), null);
});

test("editBlockedReason lets an admin edit their own row", () => {
  // 오버레이가 수정 화면으로 넓어져 본인 행도 열어야 한다. 역할 select 만 잠긴다.
  assert.equal(editBlockedReason({ adminId: 3, status: "ACTIVE" }, 3, "ADMIN"), null);
  assert.equal(editBlockedReason({ adminId: 3, status: "ACTIVE" }, 3, "STAFF"), null);
});

test("editBlockedReason lets an ADMIN edit other rows but blocks STAFF", () => {
  assert.equal(editBlockedReason({ adminId: 9, status: "ACTIVE" }, 3, "ADMIN"), null);
  assert.equal(
    editBlockedReason({ adminId: 9, status: "ACTIVE" }, 3, "STAFF"),
    "본인 계정만 수정할 수 있습니다",
  );
});

test("editBlockedReason lets ADMIN edit every status", () => {
  assert.equal(editBlockedReason({ adminId: 3, status: "SUSPENDED" }, 3, "ADMIN"), null);
  assert.equal(editBlockedReason({ adminId: 9, status: "WITHDRAWN" }, 3, "ADMIN"), null);
});

test("editBlockedReason allows pending accounts", () => {
  assert.equal(editBlockedReason({ adminId: 22, status: "PENDING" }, 3, "ADMIN"), null);
});

test("statusAction offers 정지 for active and pending rows", () => {
  for (const status of ["ACTIVE", "PENDING"]) {
    assert.deepEqual(statusAction({ adminId: 9, status }, 3), {
      action: "suspend",
      label: "정지",
      nextStatus: "SUSPENDED",
      danger: true,
      disabledReason: null,
    });
  }
});

test("statusAction locks 정지 on your own row", () => {
  // 서버가 409 CANNOT_SUSPEND_SELF 로 막는다. 눌러봐야 항상 실패한다.
  const action = statusAction({ adminId: 3, status: "ACTIVE" }, 3);

  assert.equal(action.disabledReason, "본인 계정은 정지할 수 없습니다");
});

test("statusAction offers 활성화 for suspended rows and sends PENDING", () => {
  // ACTIVE 가 아니라 PENDING 이다. 해제된 계정은 본인이 로그인해야 ACTIVE 가 된다.
  assert.deepEqual(statusAction({ adminId: 9, status: "SUSPENDED" }, 3), {
    action: "activate",
    label: "활성화",
    nextStatus: "PENDING",
    danger: false,
    disabledReason: null,
  });
});

test("statusAction offers nothing for withdrawn rows", () => {
  assert.equal(statusAction({ adminId: 9, status: "WITHDRAWN" }, 3), null);
});

test("statusAction hides status changes for ADMIN-role rows", () => {
  assert.equal(statusAction({ adminId: 9, role: "ADMIN", status: "ACTIVE" }, 3), null);
  assert.equal(statusAction({ adminId: 10, role: "ADMIN", status: "SUSPENDED" }, 3), null);
});

test("ADMIN sees edit on every row but status actions only on STAFF-role rows", () => {
  const adminRow = adminManagement.actionsMarkup?.(
    { adminId: 9, role: "ADMIN", status: "ACTIVE" },
    true,
    3,
    "ADMIN",
  ) ?? "";
  const staffRow = adminManagement.actionsMarkup?.(
    { adminId: 10, role: "STAFF", status: "SUSPENDED" },
    true,
    3,
    "ADMIN",
  ) ?? "";

  assert.match(adminRow, /data-admin-action="edit"/);
  assert.doesNotMatch(adminRow, /data-admin-action="suspend"|data-admin-action="activate"/);
  assert.match(staffRow, /data-admin-action="edit"/);
  assert.match(staffRow, /data-admin-action="activate"/);
});

test("STAFF sees only their own edit action and no status action", () => {
  const ownRow = adminManagement.actionsMarkup?.(
    { adminId: 3, role: "STAFF", status: "ACTIVE" },
    false,
    3,
    "STAFF",
  ) ?? "";
  const otherRow = adminManagement.actionsMarkup?.(
    { adminId: 9, role: "STAFF", status: "ACTIVE" },
    false,
    3,
    "STAFF",
  ) ?? "";

  assert.match(ownRow, /data-admin-action="edit"/);
  assert.doesNotMatch(ownRow, /data-admin-action="suspend"|data-admin-action="activate"/);
  assert.equal(otherRow, "");
});

test("admin rows keep the action table cell aligned when STAFF has no buttons", () => {
  const row = adminManagement.rowMarkup?.(
    { adminId: 9, name: "다른 관리자", email: "other@example.com", role: "STAFF", status: "ACTIVE" },
    false,
    3,
    "STAFF",
  ) ?? "";

  assert.match(row, /<td class="admin-actions-cell">\s*<div class="admin-row-actions"><\/div>\s*<\/td>/);
  assert.doesNotMatch(row, /<td[^>]*class="[^"]*\bflex\b/);
});

test("reset failure message warns that the previous password is unavailable", () => {
  assert.match(RESET_MAIL_FAILED_MESSAGE, /기존 비밀번호.*사용할 수 없/);
});

test("editOverlayVisibility shows role only to an ADMIN looking at someone else", () => {
  assert.equal(editOverlayVisibility({ adminId: 9 }, 3, "ADMIN").role, true);
  // 본인 역할은 서버가 409 로 막는다.
  assert.equal(editOverlayVisibility({ adminId: 3 }, 3, "ADMIN").role, false);
  assert.equal(editOverlayVisibility({ adminId: 9 }, 3, "STAFF").role, false);
});

test("editOverlayVisibility shows the password fields only on your own row", () => {
  // 변경 API 의 대상은 토큰의 sub 다. 남의 행에서 열어두면 자기 비밀번호를 바꾸게 된다.
  assert.equal(editOverlayVisibility({ adminId: 3 }, 3, "ADMIN").password, true);
  assert.equal(editOverlayVisibility({ adminId: 3 }, 3, "STAFF").password, true);
  assert.equal(editOverlayVisibility({ adminId: 9 }, 3, "ADMIN").password, false);
});

test("editOverlayVisibility hides 재설정 from STAFF and from your own row", () => {
  assert.equal(editOverlayVisibility({ adminId: 9 }, 3, "ADMIN").reset, true);
  assert.equal(editOverlayVisibility({ adminId: 3 }, 3, "STAFF").reset, false);
  // 본인 것은 바로 위 비밀번호 칸에서 직접 바꾸면 된다.
  assert.equal(editOverlayVisibility({ adminId: 3 }, 3, "ADMIN").reset, false);
});

/**
 * querySelector/remove 만 흉내 내는 최소 패널.
 *
 * jsdom 이 없어 진짜 DOM 을 못 쓴다. 그래도 "어느 노드를 지웠는가"는 검증할 수 있고,
 * 이번 버그(감춰야 할 블록이 화면에 남음)가 정확히 그 지점이다.
 */
function fakePanel() {
  const present = new Set(EDIT_OVERLAY_SECTIONS.map(([, selector]) => selector));
  return {
    present,
    querySelector(selector) {
      if (!present.has(selector)) return null;
      return {
        remove() {
          present.delete(selector);
        },
      };
    },
  };
}

test("applyEditOverlayVisibility removes the blocks that must not show", () => {
  // hidden 속성은 쓰지 않는다. .overlay-field(display:grid) 등 작성자 CSS 가
  // UA 의 [hidden]{display:none} 을 이겨 화면에 그대로 남았다. 실제로 남의 행
  // 오버레이에 비밀번호 칸이 노출된 버그가 있었다.
  const panel = fakePanel();

  applyEditOverlayVisibility(panel, { role: true, password: false, reset: true });

  assert.equal(panel.present.has("[data-password-section]"), false);
  assert.equal(panel.present.has("[data-role-field]"), true);
  assert.equal(panel.present.has("[data-reset-section]"), true);
});

test("applyEditOverlayVisibility strips password and reset on someone else's row", () => {
  const panel = fakePanel();

  applyEditOverlayVisibility(panel, editOverlayVisibility({ adminId: 9 }, 3, "ADMIN"));

  assert.equal(panel.present.has("[data-password-section]"), false);
  assert.equal(panel.present.has("[data-role-field]"), true);
});

test("applyEditOverlayVisibility leaves STAFF only the name fields on their own row", () => {
  const panel = fakePanel();

  applyEditOverlayVisibility(panel, editOverlayVisibility({ adminId: 3 }, 3, "STAFF"));

  assert.equal(panel.present.has("[data-role-field]"), false);
  assert.equal(panel.present.has("[data-reset-section]"), false);
  assert.equal(panel.present.has("[data-password-section]"), true);
});

test("the script does not fall back to the hidden attribute for overlay sections", async () => {
  // hidden 으로 되돌아가면 CSS 가 다시 이겨서 같은 버그가 재발한다.
  const scriptUrl = new URL("../../static/js/admin-management.js", import.meta.url);
  const source = await readFile(scriptUrl, "utf8");

  for (const [, selector] of EDIT_OVERLAY_SECTIONS) {
    assert.doesNotMatch(source, new RegExp(`querySelector\\("${selector.replace(/[[\]]/g, "\\$&")}"\\)\\.hidden`));
  }
});

test("validateAdminEdit rejects a blank name", () => {
  assert.deepEqual(validateAdminEdit({ name: "  ", currentPassword: "", newPassword: "", newPasswordConfirm: "" }), {
    valid: false,
    errors: { name: "관리자 이름을 입력해주세요." },
  });
});

test("validateAdminEdit does not demand a password when only the name changes", () => {
  assert.deepEqual(validateAdminEdit({ name: "한지수", currentPassword: "", newPassword: "", newPasswordConfirm: "" }), {
    valid: true,
    errors: {},
  });
});

test("validateAdminEdit demands the whole trio once any password field is touched", () => {
  const result = validateAdminEdit({
    name: "한지수",
    currentPassword: "",
    newPassword: "NewPass1!",
    newPasswordConfirm: "",
  });

  assert.equal(result.valid, false);
  assert.equal(result.errors.currentPassword, "현재 비밀번호를 입력해주세요.");
  assert.equal(result.errors.newPasswordConfirm, "새 비밀번호를 한 번 더 입력해주세요.");
});

test("validateAdminEdit rejects a mismatched confirmation", () => {
  const result = validateAdminEdit({
    name: "한지수",
    currentPassword: "Temp1234!",
    newPassword: "NewPass1!",
    newPasswordConfirm: "NewPass2!",
  });

  assert.deepEqual(result.errors, { newPasswordConfirm: "새 비밀번호가 일치하지 않습니다." });
});

test("validateAdminEdit leaves the password policy to the server", () => {
  // 8자 미만이지만 프론트는 막지 않는다. 정책 판정은 서버 몫이다.
  assert.deepEqual(
    validateAdminEdit({ name: "한지수", currentPassword: "Temp1234!", newPassword: "s", newPasswordConfirm: "s" }),
    { valid: true, errors: {} },
  );
});

test("edit overlay carries the fields the script fills in", async () => {
  const templateUrl = new URL("../../static/templates/overlay-admin-edit.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  for (const hook of [
    "data-admin-email",
    "data-role-field",
    "data-password-section",
    "data-reset-section",
    "data-admin-edit-reset",
  ]) {
    assert.match(html, new RegExp(hook), `${hook} 가 없으면 스크립트가 조용히 아무것도 못 한다`);
  }
  for (const field of ["name", "role", "currentPassword", "newPassword", "newPasswordConfirm"]) {
    assert.match(html, new RegExp(`name="${field}"`));
  }
});

test("edit overlay shows email in a readonly control matching the name field", async () => {
  const templateUrl = new URL("../../static/templates/overlay-admin-edit.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");
  const emailField = html.match(/<div class="overlay-field">[\s\S]*?id="admin-edit-email"[\s\S]*?<\/div>/)?.[0] ?? "";

  assert.match(emailField, /<label for="admin-edit-email">이메일<\/label>/);
  assert.match(emailField, /<input[^>]*data-admin-email[^>]*class="ui-control"[^>]*readonly/);
  assert.doesNotMatch(emailField, /data-error-for="email"/);
});

test("populateAdminEditFields places email in the readonly control value", () => {
  const controls = {
    "[data-admin-email]": { value: "" },
    "[name='name']": { value: "" },
    "[name='role']": { value: "" },
  };
  const panel = { querySelector: (selector) => controls[selector] };

  adminManagement.populateAdminEditFields?.(panel, {
    email: "staff@example.com",
    name: "일반 관리자",
    role: "STAFF",
  });

  assert.equal(controls["[data-admin-email]"].value, "staff@example.com");
  assert.equal(controls["[name='name']"].value, "일반 관리자");
  assert.equal(controls["[name='role']"].value, "일반 관리자");
});

test("edit overlay states the password policy", async () => {
  const templateUrl = new URL("../../static/templates/overlay-admin-edit.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /8자 이상, 대문자·소문자·숫자·특수문자를 각각 1개 이상/);
});

test("edit overlay keeps the reset button out of the save/cancel row", async () => {
  // .overlay-actions 안에 두면 flex:1 로 전체 폭 빨강 버튼이 되어 「저장」보다 눈에 띈다.
  // 저장하려다 잘못 누르면 상대 계정이 잠긴다.
  const templateUrl = new URL("../../static/templates/overlay-admin-edit.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /class="overlay-danger-zone" data-reset-section/);
  assert.doesNotMatch(html, /class="overlay-actions" data-reset-section/);
});

test("edit overlay puts the password label and temporary-password button on one row", async () => {
  const templateUrl = new URL("../../static/templates/overlay-admin-edit.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");
  const resetSection = html.slice(html.indexOf('class="overlay-danger-zone"'), html.indexOf('class="overlay-actions"'));
  const firstRow = resetSection.match(/<div[^>]*data-reset-header[^>]*>[\s\S]*?<\/div>/)?.[0] ?? "";

  assert.match(firstRow, />비밀번호<\/p>/);
  assert.match(firstRow, /data-admin-edit-reset[^>]*>임시 비밀번호 발송<\/button>/);
  assert.doesNotMatch(firstRow, /기존 비밀번호는 사용할 수 없습니다/);
  assert.ok(
    resetSection.indexOf(firstRow) <
      resetSection.indexOf("임시 비밀번호 발송 시 기존 비밀번호는 사용할 수 없으며 계정 상태는 변경되지 않습니다."),
  );
});

test("reset confirmation says the account status is preserved", async () => {
  const templateUrl = new URL("../../static/templates/overlay-password-reset.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /계정 상태는 변경되지 않습니다/);
  assert.match(html, /기존 비밀번호는 사용할 수 없습니다/);
});

test("edit overlay does not resurrect the account-active checkbox", async () => {
  // 정지·활성화는 목록 버튼이 맡는다. 두 곳에서 상태를 바꾸면 서로 어긋난다.
  const templateUrl = new URL("../../static/templates/overlay-admin-edit.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.doesNotMatch(html, /type="checkbox"/);
});

test("updateAdminStatus changes only the matching admin", () => {
  const result = updateAdminStatus(admins, "ADM-1001", "정지");
  assert.equal(result[0].status, "정지");
  assert.equal(result[1].status, "정지");
  assert.equal(admins[0].status, "활성");
});
