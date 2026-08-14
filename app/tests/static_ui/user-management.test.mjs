import test from "node:test";
import assert from "node:assert/strict";
import { filterUsers, suspendUser } from "../../static/js/user-management.js";

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
