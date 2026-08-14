import test from "node:test";
import assert from "node:assert/strict";
import { filterTasks, retryTask } from "../../static/js/task-management.js";

const tasks = [
  { id: "TSK-8812", type: "OCR 추출", status: "실패" },
  { id: "TSK-8801", type: "알림 발송", status: "진행 중" },
  { id: "TSK-8500", type: "챗봇 응답 검수", status: "성공" },
];

test("filterTasks combines task search, type and status", () => {
  assert.deepEqual(filterTasks(tasks, "8812", "OCR 추출", "실패").map((task) => task.id), ["TSK-8812"]);
  assert.deepEqual(filterTasks(tasks, "", "전체", "진행 중").map((task) => task.id), ["TSK-8801"]);
});

test("retryTask changes a failed task to processing without mutating input", () => {
  const result = retryTask(tasks, "TSK-8812");
  assert.equal(result[0].status, "진행 중");
  assert.equal(tasks[0].status, "실패");
});
