import test from "node:test";
import assert from "node:assert/strict";

import { formatRefreshTime, periodValue, selectPeriod, signupsLabel } from "../../static/js/dashboard.js";

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

test("periodValue maps the tab label to the API enum", () => {
  assert.equal(periodValue("오늘"), "TODAY");
  assert.equal(periodValue("7일"), "LAST_7_DAYS");
  assert.equal(periodValue("30일"), "LAST_30_DAYS");
});

test("periodValue returns an empty value for an unknown label", () => {
  assert.equal(periodValue("90일"), "");
});

test("signupsLabel follows the selected period", () => {
  assert.equal(signupsLabel("오늘"), "오늘 가입");
  assert.equal(signupsLabel("7일"), "7일 가입");
  assert.equal(signupsLabel("30일"), "30일 가입");
});

test("signupsLabel falls back to a period-free label", () => {
  assert.equal(signupsLabel("90일"), "신규 가입");
});
