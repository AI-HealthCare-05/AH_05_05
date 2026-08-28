import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
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

test("validateAdminInput rejects blank names and malformed emails", () => {
  assert.deepEqual(validateAdminInput({ name: " ", email: "not-email" }), {
    valid: false,
    errors: { name: "관리자 이름을 입력해주세요.", email: "올바른 이메일 주소를 입력해주세요." },
  });
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

test("editBlockedReason blocks suspended and withdrawn accounts for everyone", () => {
  assert.equal(
    editBlockedReason({ adminId: 3, status: "SUSPENDED" }, 3, "ADMIN"),
    "정지된 계정은 수정할 수 없습니다",
  );
  assert.equal(
    editBlockedReason({ adminId: 9, status: "WITHDRAWN" }, 3, "ADMIN"),
    "정지된 계정은 수정할 수 없습니다",
  );
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

test("reset failure message says the target cannot log in", () => {
  // "발송 실패"만 쓰면 상대가 잠겼다는 사실이 안 보인다.
  assert.match(RESET_MAIL_FAILED_MESSAGE, /로그인할 수 없/);
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

test("reset confirmation spells out that the target cannot log in", async () => {
  const templateUrl = new URL("../../static/templates/overlay-password-reset.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /메일을 받기 전까지 로그인할 수 없습니다/);
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
