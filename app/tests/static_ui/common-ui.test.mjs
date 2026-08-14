import test from "node:test";
import assert from "node:assert/strict";

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
