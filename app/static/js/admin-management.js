import { closeOverlay, downloadCsv, openOverlay, showToast } from "./overlay.js";

export function filterAdmins(admins, query, role, status) {
  const term = query.trim().toLowerCase();
  return admins.filter((admin) => (!term || `${admin.name} ${admin.email}`.toLowerCase().includes(term)) && (role === "전체" || admin.role === role) && (status === "전체" || admin.status === status));
}

export function validateAdminInput({ name, email }) {
  const errors = {};
  if (!name.trim()) errors.name = "관리자 이름을 입력해주세요.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errors.email = "올바른 이메일 주소를 입력해주세요.";
  return { valid: Object.keys(errors).length === 0, errors };
}

export function updateAdminStatus(admins, adminId, status) {
  return admins.map((admin) => admin.id === adminId ? { ...admin, status } : { ...admin });
}

let admins = [
  { id: "ADM-1001", name: "Dr. Sarah Connor", email: "s.connor@clinics.com", role: "최고 관리자", status: "활성" },
  { id: "ADM-1002", name: "Dr. Park, AI", email: "park@ozcoding.ai", role: "일반 관리자", status: "활성" },
  { id: "ADM-1003", name: "John Doe", email: "john@ozcoding.ai", role: "일반 관리자", status: "정지" },
];

function initializeAdminManagement() {
  const tbody = document.querySelector("[data-admin-rows]"); if (!tbody) return;
  const search = document.querySelector("[data-admin-search]"); const role = document.querySelector("[data-admin-role]"); const status = document.querySelector("[data-admin-status]");
  const render = () => {
    const visible = filterAdmins(admins, search.value, role.value, status.value);
    tbody.innerHTML = visible.length ? visible.map((admin) => `<tr><td>${admin.id}</td><td><strong>${admin.name}</strong></td><td>${admin.email}</td><td>${admin.role}</td><td><span class="status-badge status-${admin.status === "활성" ? "active" : "stopped"}">${admin.status}</span></td><td class="flex gap-1 py-2"><button class="ui-link-button" data-admin-action="edit" data-admin-id="${admin.id}">수정</button><button class="ui-link-button" data-admin-action="reset" data-admin-id="${admin.id}">재설정</button><button class="ui-link-button" data-admin-action="stop" data-admin-id="${admin.id}">정지</button></td></tr>`).join("") : '<tr><td class="empty-row" colspan="6">조건에 맞는 관리자가 없습니다.</td></tr>';
  };
  [search, role, status].forEach((control) => control.addEventListener(control === search ? "input" : "change", render));
  document.querySelector("[data-admin-register]").addEventListener("click", async () => {
    await openOverlay("overlay-admin-register.html", { onConfirm: (overlay) => {
      const name = overlay.querySelector("[name='name']").value; const email = overlay.querySelector("[name='email']").value; const result = validateAdminInput({ name, email });
      overlay.querySelector("[data-error-for='name']").textContent = result.errors.name ?? ""; overlay.querySelector("[data-error-for='email']").textContent = result.errors.email ?? ""; if (!result.valid) return;
      admins = [...admins, { id: `ADM-${1001 + admins.length}`, name: name.trim(), email: email.trim(), role: overlay.querySelector("[name='role']").value, status: "활성" }]; closeOverlay(); render(); showToast("관리자를 등록했습니다.");
    }});
  });
  document.querySelector("[data-admin-export]").addEventListener("click", () => downloadCsv("admins.csv", [["ID","이름","이메일","역할","상태"], ...filterAdmins(admins, search.value, role.value, status.value).map((a) => [a.id,a.name,a.email,a.role,a.status])]));
  tbody.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-admin-action]"); if (!button) return; const admin = admins.find((item) => item.id === button.dataset.adminId);
    if (button.dataset.adminAction === "reset") { await openOverlay("overlay-password-reset.html", { onConfirm: () => { closeOverlay(); showToast(`${admin.email}로 재설정 링크를 발송했습니다.`); }}); return; }
    if (button.dataset.adminAction === "stop") { await openOverlay("overlay-admin-status-confirm.html", { onConfirm: () => { admins = updateAdminStatus(admins, admin.id, "정지"); closeOverlay(); render(); showToast("관리자 계정을 정지했습니다."); }}); return; }
    const overlay = await openOverlay("overlay-admin-edit.html", { onConfirm: (host) => { const target = admins.find((item) => item.id === admin.id); admins = admins.map((item) => item.id === admin.id ? { ...target, role: host.querySelector("[name='role']").value, status: host.querySelector("[name='status']").checked ? "활성" : "정지" } : item); closeOverlay(); render(); showToast("관리자 정보를 수정했습니다."); }}); overlay.querySelector("[name='name']").value = admin.name; overlay.querySelector("[name='email']").value = admin.email; overlay.querySelector("[name='role']").value = admin.role; overlay.querySelector("[name='status']").checked = admin.status === "활성";
  });
  render();
}
if (typeof document !== "undefined") initializeAdminManagement();
