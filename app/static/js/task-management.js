import { closeOverlay, openOverlay, showToast } from "./overlay.js";

export function filterTasks(tasks, query, type, status) {
  const term = query.trim().toLowerCase();
  return tasks.filter((task) => (!term || `${task.id} ${task.type}`.toLowerCase().includes(term)) && (type === "전체" || task.type === type) && (status === "전체" || task.status === status));
}

export function retryTask(tasks, taskId) {
  return tasks.map((task) => task.id === taskId ? { ...task, status: "진행 중" } : { ...task });
}

let tasks = [
  { id: "TSK-8812", type: "OCR 추출", owner: "시스템 자동", started: "2024.12.14 09:31", status: "실패" },
  { id: "TSK-8801", type: "알림 발송", owner: "시스템 자동", started: "2024.12.14 09:44", status: "진행 중" },
  { id: "TSK-8500", type: "챗봇 응답 검수", owner: "Dr. Park, AI", started: "2024.12.13 22:10", status: "성공" },
  { id: "TSK-8488", type: "OCR 추출", owner: "시스템 자동", started: "2024.12.13 21:02", status: "성공" },
];

function initializeTaskManagement() {
  const tbody = document.querySelector("[data-task-rows]"); if (!tbody) return;
  const search = document.querySelector("[data-task-search]"); const type = document.querySelector("[data-task-type]"); const status = document.querySelector("[data-task-status]");
  const render = () => { const visible = filterTasks(tasks, search.value, type.value, status.value); tbody.innerHTML = visible.length ? visible.map((task) => `<tr><td><strong>${task.id}</strong></td><td>${task.type}</td><td>${task.owner}</td><td>${task.started}</td><td><span class="status-badge status-${task.status === "성공" ? "active" : task.status === "실패" ? "failed" : "processing"}">${task.status}</span></td><td><button class="ui-link-button" data-task-detail="${task.id}">상세 보기</button></td></tr>`).join("") : '<tr><td class="empty-row" colspan="6">조건에 맞는 작업이 없습니다.</td></tr>'; };
  [search, type, status].forEach((control) => control.addEventListener(control === search ? "input" : "change", render));
  document.querySelector("[data-task-reset]").addEventListener("click", () => { search.value = ""; type.value = "전체"; status.value = "전체"; render(); });
  tbody.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-task-detail]"); if (!button) return; const task = tasks.find((item) => item.id === button.dataset.taskDetail);
    const file = task.status === "성공" ? "overlay-task-detail-success.html" : task.status === "진행 중" ? "overlay-task-detail-processing.html" : "overlay-task-retry.html";
    const overlay = await openOverlay(file, { onConfirm: task.status === "실패" ? () => { tasks = retryTask(tasks, task.id); closeOverlay(); render(); showToast(`${task.id} 재시도를 시작했습니다.`); } : undefined });
    overlay.querySelectorAll("[data-task-id]").forEach((node) => { node.textContent = task.id; });
  }); render();
}
if (typeof document !== "undefined") initializeTaskManagement();
