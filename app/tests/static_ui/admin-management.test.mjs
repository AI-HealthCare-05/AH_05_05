import test from "node:test";
import assert from "node:assert/strict";
import {
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
    assert.deepEqual(statusAction({ status }), {
      action: "suspend",
      label: "정지",
      nextStatus: "SUSPENDED",
      danger: true,
    });
  }
});

test("statusAction offers 활성화 for suspended rows and sends PENDING", () => {
  // ACTIVE 가 아니라 PENDING 이다. 해제된 계정은 본인이 로그인해야 ACTIVE 가 된다.
  assert.deepEqual(statusAction({ status: "SUSPENDED" }), {
    action: "activate",
    label: "활성화",
    nextStatus: "PENDING",
    danger: false,
  });
});

test("statusAction offers nothing for withdrawn rows", () => {
  assert.equal(statusAction({ status: "WITHDRAWN" }), null);
});

test("reset failure message says the target cannot log in", () => {
  // "발송 실패"만 쓰면 상대가 잠겼다는 사실이 안 보인다.
  assert.match(RESET_MAIL_FAILED_MESSAGE, /로그인할 수 없/);
});

test("updateAdminStatus changes only the matching admin", () => {
  const result = updateAdminStatus(admins, "ADM-1001", "정지");
  assert.equal(result[0].status, "정지");
  assert.equal(result[1].status, "정지");
  assert.equal(admins[0].status, "활성");
});
