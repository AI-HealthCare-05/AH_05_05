import { closeOverlay, downloadCsv, openOverlay, showToast } from "./overlay.js";

export function filterUsers(users, query, status) {
  const term = query.trim().toLowerCase();
  return users.filter((user) => {
    const matchesTerm = !term || `${user.id} ${user.name} ${user.email}`.toLowerCase().includes(term);
    return matchesTerm && (status === "전체" || user.status === status);
  });
}

export function suspendUser(users, memberId) {
  return users.map((user) => (user.id === memberId ? { ...user, status: "정지" } : { ...user }));
}

let users = [
  { id: "MBR-9201", name: "Dr. Sarah Connor", email: "s.connor@clinics.com", phone: "010-1234-5678", joined: "2024.11.02", status: "활성" },
  { id: "MBR-3810", name: "John Doe, MD", email: "johndoe@ozhealth.ai", phone: "010-2345-6789", joined: "2024.10.15", status: "활성" },
  { id: "MBR-2715", name: "Miles Dyson", email: "miles.d@cyberdyne.org", phone: "010-3456-7890", joined: "2024.10.02", status: "정지" },
  { id: "MBR-1941", name: "Dr. Ellie Sattler", email: "e.sattler@jurassicops.org", phone: "010-4567-8901", joined: "2024.09.28", status: "활성" },
  { id: "MBR-0824", name: "Ian Malcolm", email: "chaos.m@jurassicops.org", phone: "010-5678-9012", joined: "2024.09.15", status: "정지" },
];

function initializeUserManagement() {
  const tableBody = document.querySelector("[data-user-rows]");
  if (!tableBody) return;
  const search = document.querySelector("[data-user-search]");
  const status = document.querySelector("[data-user-status]");

  const render = () => {
    const visible = filterUsers(users, search.value, status.value);
    tableBody.innerHTML = visible.length ? visible.map((user) => `
      <tr data-member-id="${user.id}">
        <td><input type="checkbox" aria-label="${user.name} 선택"></td><td>${user.id}</td><td><strong>${user.name}</strong></td>
        <td>${user.email}</td><td>${user.phone}</td><td>${user.joined}</td>
        <td><span class="status-badge status-${user.status === "활성" ? "active" : "stopped"}">${user.status}</span></td>
        <td><button class="ui-link-button" type="button" data-user-detail="${user.id}">상세 보기</button></td>
      </tr>`).join("") : '<tr><td class="empty-row" colspan="8">조건에 맞는 회원이 없습니다.</td></tr>';
  };

  search.addEventListener("input", render);
  status.addEventListener("change", render);
  document.querySelector("[data-user-reset]").addEventListener("click", () => { search.value = ""; status.value = "전체"; render(); });
  document.querySelector("[data-user-export]").addEventListener("click", () => {
    const visible = filterUsers(users, search.value, status.value);
    const ok = downloadCsv("users.csv", [["회원 ID", "이름", "이메일", "전화번호", "가입일", "상태"], ...visible.map((u) => [u.id, u.name, u.email, u.phone, u.joined, u.status])]);
    if (!ok) showToast("내보낼 회원이 없습니다.", "error");
  });
  tableBody.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-user-detail]");
    if (!button) return;
    const user = users.find((item) => item.id === button.dataset.userDetail);
    try {
      const overlay = await openOverlay("overlay-user-detail.html", { onConfirm: async () => {
        await openOverlay("overlay-user-suspend-confirm.html", { onConfirm: () => {
          users = suspendUser(users, user.id); closeOverlay(); render(); showToast(`${user.name} 계정을 정지했습니다.`);
        }});
      }});
      overlay.querySelector("[data-user-name]").textContent = user.name;
      overlay.querySelector("[data-user-id]").textContent = user.id;
      overlay.querySelector("[data-user-email]").textContent = user.email;
    } catch (error) { showToast(error.message, "error"); }
  });
  render();
}

if (typeof document !== "undefined") initializeUserManagement();
