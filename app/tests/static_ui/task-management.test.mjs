import test from "node:test";
import assert from "node:assert/strict";
import {
  buildTaskQuery,
  renderTaskStats,
  validateTaskDateRange,
} from "../../static/js/task-management.js";

test("buildTaskQuery converts every selected condition to admin API parameters", () => {
  assert.deepEqual(
    buildTaskQuery({
      keyword: "42",
      type: "ALARM",
      status: "실패",
      startDate: "2026-08-01",
      endDate: "2026-08-26",
    }),
    {
      keyword: "42",
      jobType: "ALARM",
      status: "FAILED",
      startDate: "2026-08-01",
      endDate: "2026-08-26",
      page: 1,
      size: 100,
    },
  );
});

test("buildTaskQuery maps every task type option to its API enum value", () => {
  const types = ["전체", "OCR", "LLM", "CHAT", "ALARM"];

  const values = types.map((type) => buildTaskQuery({
    keyword: "",
    type,
    status: "전체",
    startDate: "2026-08-26",
    endDate: "2026-08-26",
  }).jobType);

  assert.deepEqual(values, ["", "OCR", "LLM", "CHAT", "ALARM"]);
});

test("buildTaskQuery maps all task status labels to API enum values", () => {
  const statuses = ["전체", "진행중", "성공", "실패", "진행 대기", "재시도 대기", "취소"];

  const values = statuses.map((status) => buildTaskQuery({
    keyword: "",
    type: "전체",
    status,
    startDate: "2026-08-26",
    endDate: "2026-08-26",
  }).status);

  assert.deepEqual(values, ["", "PROCESSING", "COMPLETED", "FAILED", "QUEUED", "RETRY_WAITING", "CANCELLED"]);
});

test("validateTaskDateRange clears an end date earlier than the start date", () => {
  const alerts = [];
  const endDate = { value: "2026-08-19" };

  assert.equal(validateTaskDateRange("2026-08-20", endDate, (message) => alerts.push(message)), false);
  assert.equal(endDate.value, "");
  assert.deepEqual(alerts, ["조회 기간이 올바르지 않습니다."]);
});

test("validateTaskDateRange accepts an equal or later end date", () => {
  const endDate = { value: "2026-08-20" };
  assert.equal(validateTaskDateRange("2026-08-20", endDate, () => assert.fail("alert must not run")), true);
  assert.equal(endDate.value, "2026-08-20");
});

test("renderTaskStats maps every API status count to its summary card", () => {
  const values = new Map();
  const root = {
    querySelector(selector) {
      if (!values.has(selector)) values.set(selector, { textContent: "0" });
      return values.get(selector);
    },
  };

  renderTaskStats(root, {
    QUEUED: 2,
    PROCESSING: 3,
    RETRY_WAITING: 4,
    COMPLETED: 5,
    FAILED: 6,
    CANCELLED: 7,
  });

  assert.equal(values.get("[data-task-count-queued]").textContent, "2");
  assert.equal(values.get("[data-task-count-processing]").textContent, "3");
  assert.equal(values.get("[data-task-count-retry-waiting]").textContent, "4");
  assert.equal(values.get("[data-task-count-completed]").textContent, "5");
  assert.equal(values.get("[data-task-count-failed]").textContent, "6");
  assert.equal(values.get("[data-task-count-cancelled]").textContent, "7");
});
