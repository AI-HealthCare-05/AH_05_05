import test from "node:test";
import assert from "node:assert/strict";
import { filterAdmins, updateAdminStatus, validateAdminInput } from "../../static/js/admin-management.js";

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

test("updateAdminStatus changes only the matching admin", () => {
  const result = updateAdminStatus(admins, "ADM-1001", "정지");
  assert.equal(result[0].status, "정지");
  assert.equal(result[1].status, "정지");
  assert.equal(admins[0].status, "활성");
});
