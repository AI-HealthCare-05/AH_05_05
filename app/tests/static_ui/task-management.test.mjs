import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as taskManagement from "../../static/js/task-management.js";
import {
  buildTaskQuery,
  formatTaskError,
  formatTaskTotal,
  getTaskPaginationState,
  renderTaskStats,
  validateTaskDateRange,
} from "../../static/js/task-management.js";

const templatePath = fileURLToPath(new URL("../../static/templates/screen-5-task-management.html", import.meta.url));

test("buildTaskQuery converts every selected condition to admin API parameters", () => {
  assert.deepEqual(
    buildTaskQuery({
      keyword: "42",
      type: "ALARM",
      status: "실패",
      startDate: "2026-08-01",
      endDate: "2026-08-26",
      page: 3,
      size: 50,
    }),
    {
      keyword: "42",
      jobType: "ALARM",
      status: "FAILED",
      startDate: "2026-08-01",
      endDate: "2026-08-26",
      page: 3,
      size: 50,
    },
  );
});

test("task management template exposes pagination below the table", () => {
  const html = readFileSync(templatePath, "utf8");
  const tableEnd = html.indexOf("</table>");

  assert.match(html, /data-task-pagination/);
  assert.match(html, /data-task-total[^>]*>총 -건/);
  assert.match(html, /data-task-page-size/);
  for (const size of [20, 50, 100]) assert.match(html, new RegExp(`<option value="${size}"`));
  assert.ok(tableEnd < html.indexOf("data-task-pagination"));
});

test("task list masks the user name and appends the user ID", () => {
  assert.equal(taskManagement.formatTaskUser({ userName: "김은미", userId: 9 }), "김*미(9)");
  assert.equal(taskManagement.formatTaskUser({ userName: "김미", userId: 10 }), "김미(10)");
  assert.equal(taskManagement.formatTaskUser({ userName: null, userId: null }), "시스템 자동");
});

test("task list renders localized alarm type labels", () => {
  assert.equal(taskManagement.formatAlarmType("MEDICATION"), "복약");
  assert.equal(taskManagement.formatAlarmType("NUTRIENT"), "영양제");
  assert.equal(taskManagement.formatAlarmType("FOLLOW_UP_VISIT"), "진료일정");
  assert.equal(taskManagement.formatAlarmType("GUIDE_CHECK"), "생활가이드");
  assert.equal(taskManagement.formatAlarmType(null), "-");
});

test("task list headers identify the masked user ID and alarm type columns", () => {
  const html = readFileSync(templatePath, "utf8");

  assert.match(html, /<th>사용자\(ID\)<\/th>/);
  assert.match(html, /<th>알림 유형<\/th>/);
});

test("task filter selects expose only supported type and status placeholders", () => {
  const html = readFileSync(templatePath, "utf8");
  const typeOptions = html.match(/<select data-task-type[^>]*>([\s\S]*?)<\/select>/)?.[1] ?? "";
  const statusOptions = html.match(/<select data-task-status[^>]*>([\s\S]*?)<\/select>/)?.[1] ?? "";

  assert.match(typeOptions, /<option>작업유형<\/option>/);
  assert.match(typeOptions, /<option>OCR<\/option>/);
  assert.match(typeOptions, /<option>ALARM<\/option>/);
  assert.match(typeOptions, /<option>EMAIL<\/option>/);
  assert.doesNotMatch(typeOptions, /<option>(전체|LLM|CHAT)<\/option>/);
  assert.match(statusOptions, /<option>상태<\/option>/);
  assert.doesNotMatch(statusOptions, /<option>전체<\/option>/);
});

test("formatTaskTotal renders API total count and failure fallback", () => {
  assert.equal(formatTaskTotal(37), "총 37건");
  assert.equal(formatTaskTotal(0), "총 0건");
  assert.equal(formatTaskTotal(null), "총 -건");
});

test("formatTaskError labels an expired Push subscription as deactivated", () => {
  assert.equal(
    formatTaskError({
      errorCode: "PUSH_SUBSCRIPTION_EXPIRED",
      errorMessage: null,
    }),
    "비활성화 처리(PUSH_SUBSCRIPTION_EXPIRED)",
  );
  assert.equal(
    formatTaskError({ errorCode: "PUSH_REJECTED", errorMessage: "provider rejected" }),
    "PUSH_REJECTED - provider rejected",
  );
});

test("getTaskPaginationState limits visible pages and clamps requested page", () => {
  assert.deepEqual(getTaskPaginationState(121, 9, 20), {
    currentPage: 7,
    totalPages: 7,
    pages: [3, 4, 5, 6, 7],
    hasPrevious: true,
    hasNext: false,
  });
  assert.deepEqual(getTaskPaginationState(0, 1, 20).pages, [1]);
});

test("buildTaskQuery maps every task type option to its API enum value", () => {
  const types = ["작업유형", "OCR", "ALARM", "EMAIL"];

  const values = types.map((type) => buildTaskQuery({
    keyword: "",
    type,
    status: "상태",
    startDate: "2026-08-26",
    endDate: "2026-08-26",
  }).jobType);

  assert.deepEqual(values, ["", "OCR", "ALARM", "EMAIL"]);
});

test("buildTaskQuery maps all task status labels to API enum values", () => {
  const statuses = ["상태", "진행중", "성공", "실패", "진행 대기", "재시도 대기", "취소"];

  const values = statuses.map((status) => buildTaskQuery({
    keyword: "",
    type: "작업유형",
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
