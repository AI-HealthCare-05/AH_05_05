import test from "node:test";
import assert from "node:assert/strict";

import { formatRefreshTime, selectPeriod } from "../../static/js/dashboard.js";

test("selectPeriod marks only the selected period active", () => {
  assert.deepEqual(selectPeriod(["오늘", "7일", "30일"], "30일"), ["inactive", "inactive", "active"]);
});

test("selectPeriod leaves every period inactive for an unknown selection", () => {
  assert.deepEqual(selectPeriod(["오늘", "7일", "30일"], "90일"), ["inactive", "inactive", "inactive"]);
});

test("formatRefreshTime pads hours and minutes", () => {
  const date = new Date(2026, 7, 13, 9, 5);

  assert.equal(formatRefreshTime(date), "최종 점검: 09:05");
});
