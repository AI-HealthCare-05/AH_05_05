import test from "node:test";
import assert from "node:assert/strict";

import { statusBadgeClass } from "../../static/js/api.js";
import { getNavigationTarget } from "../../static/js/navigation.js";
import { serializeCsv } from "../../static/js/overlay.js";

test("getNavigationTarget maps each sidebar section to its page", () => {
  assert.equal(getNavigationTarget("dashboard"), "dashboard.html");
  assert.equal(getNavigationTarget("users"), "user-management.html");
  assert.equal(getNavigationTarget("admins"), "screen-4-admin-management.html");
  assert.equal(getNavigationTarget("tasks"), "screen-5-task-management.html");
  assert.equal(getNavigationTarget("logout"), "login.html");
});

test("getNavigationTarget returns the dashboard for an unknown section", () => {
  assert.equal(getNavigationTarget("unknown"), "dashboard.html");
});

test("statusBadgeClass separates active, suspended and pending", () => {
  assert.equal(statusBadgeClass("ACTIVE"), "active");
  assert.equal(statusBadgeClass("SUSPENDED"), "stopped");
  assert.equal(statusBadgeClass("PENDING"), "processing");
});

test("statusBadgeClass keeps suspended grey, not the danger colour", () => {
  // 정지는 오류가 아니라 관리자가 의도한 상태다. 빨강은 파괴적 동작 버튼이 쓴다.
  assert.notEqual(statusBadgeClass("SUSPENDED"), "failed");
});

test("statusBadgeClass falls back to grey for statuses the screens do not handle", () => {
  assert.equal(statusBadgeClass("WITHDRAWN"), "stopped");
  assert.equal(statusBadgeClass(undefined), "stopped");
});

test("serializeCsv quotes commas and double quotes", () => {
  assert.equal(
    serializeCsv([[
      "이름",
      "메모",
    ], [
      "Dr. Sarah Connor",
      "서울, 강남 \"센터\"",
    ]]),
    '\uFEFF이름,메모\r\nDr. Sarah Connor,"서울, 강남 ""센터"""',
  );
});
