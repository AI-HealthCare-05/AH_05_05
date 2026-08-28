import test from "node:test";
import assert from "node:assert/strict";
import * as userManagement from "../../static/js/user-management.js";

const { filterUsers, suspendUser } = userManagement;

const users = [
  { id: "MBR-9201", name: "Dr. Sarah Connor", email: "s.connor@clinics.com", status: "활성" },
  { id: "MBR-2715", name: "Miles Dyson", email: "miles.d@cyberdyne.org", status: "정지" },
];

test("filterUsers searches name and email case-insensitively", () => {
  assert.deepEqual(filterUsers(users, "SARAH", "전체").map((user) => user.id), ["MBR-9201"]);
  assert.deepEqual(filterUsers(users, "cyberdyne", "전체").map((user) => user.id), ["MBR-2715"]);
});

test("filterUsers applies the selected status", () => {
  assert.deepEqual(filterUsers(users, "", "정지").map((user) => user.id), ["MBR-2715"]);
});

test("suspendUser changes only the matching member", () => {
  const result = suspendUser(users, "MBR-9201");
  assert.equal(result[0].status, "정지");
  assert.equal(result[1].status, "정지");
  assert.equal(users[0].status, "활성");
});

test("formatUserIdLabel wraps the user id with the member label", () => {
  assert.equal(userManagement.formatUserIdLabel?.(42), "(회원 ID : 42)");
});

test("getPaginationState calculates navigation state from the API total", () => {
  assert.deepEqual(userManagement.getPaginationState?.(12, 3, 5), {
    currentPage: 3,
    totalPages: 3,
    pages: [1, 2, 3],
    hasPrevious: true,
    hasNext: false,
  });
});

test("getPaginationState keeps at most five page numbers around the current page", () => {
  assert.deepEqual(userManagement.getPaginationState?.(100, 10, 5).pages, [8, 9, 10, 11, 12]);
});

test("buildUserListQuery sends the selected page and size to the API", () => {
  assert.deepEqual(userManagement.buildUserListQuery?.(" 홍길동 ", " google.com ", "활성", 2, 20), {
    name: "홍길동",
    email: "google.com",
    status: "ACTIVE",
    page: 2,
    size: 20,
  });
});

test("getUserDetailAction exposes the suspend action for active users", () => {
  assert.deepEqual(userManagement.getUserDetailAction?.("ACTIVE"), {
    label: "계정 정지",
    nextStatus: "SUSPENDED",
    className: "ui-button ui-button-danger",
    requiresConfirmation: true,
  });
});

test("getUserDetailAction exposes the blue activation action for suspended users", () => {
  assert.deepEqual(userManagement.getUserDetailAction?.("SUSPENDED"), {
    label: "활성화",
    nextStatus: "ACTIVE",
    className: "ui-button ui-button-primary",
    requiresConfirmation: false,
  });
});

test("formatUserTotal displays the filtered API total", () => {
  assert.equal(userManagement.formatUserTotal?.(120), "총 120명");
});

test("formatUserTotal displays a placeholder when loading fails", () => {
  assert.equal(userManagement.formatUserTotal?.(null), "총 -명");
});
