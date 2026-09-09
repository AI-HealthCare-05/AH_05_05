import { ApiError, escapeHtml, get, patch, post, request, requireLogin, tableState } from "./api.js";

const COLUMN_COUNT = 6;
export const BADGE_TYPE_PATH = "/common-codes/CHL/BDG_TYPE";

export function badgeActionMarkup(id, isDeletable = true) {
  const deleteState = isDeletable
    ? ""
    : ' disabled aria-disabled="true" title="사용 중인 배지는 삭제할 수 없습니다."';
  return `<button type="button" class="ui-link-button" data-edit-badge="${id}">수정</button> `
    + `<button type="button" class="ui-link-button ui-link-button-danger" data-delete-badge="${id}"${deleteState}>삭제</button>`;
}

function initializeBadgeManagement() {
  const tbody = document.querySelector("[data-badge-rows]");
  const form = document.querySelector("[data-badge-form]");
  const dialog = document.querySelector("[data-badge-dialog]");
  const searchForm = document.querySelector("[data-badge-search-form]");
  if (!tbody || !form || !dialog || !searchForm || !requireLogin()) return;
  const error = form.querySelector("[data-form-error]");
  const title = form.querySelector("[data-form-title]");
  const imageInput = form.querySelector("[data-badge-image-input]");
  const imageName = form.querySelector("[data-badge-image-name]");
  const imagePreview = form.querySelector("[data-badge-image-preview]");
  let editing = null;
  let previewObjectUrl = null;
  let badgeTypes = [];

  const loadBadgeTypes = async () => {
    if (!badgeTypes.length) badgeTypes = (await get(BADGE_TYPE_PATH)).items;
    const options = badgeTypes
      .map((item) => `<option value="${item.id}">${escapeHtml(item.detail_name)}</option>`)
      .join("");
    const selectedFilter = searchForm.elements.type.value;
    searchForm.elements.type.innerHTML = `<option value="">배지 유형</option>${options}`;
    searchForm.elements.type.value = selectedFilter;
    form.elements.type.innerHTML = `<option value="">선택</option>${options}`;
  };

  const clearImagePreview = () => {
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = null;
    imageName.value = "";
    imagePreview.removeAttribute("src");
    imagePreview.hidden = true;
  };

  const showImagePreview = (src, fileName) => {
    imageName.value = fileName;
    imagePreview.src = src;
    imagePreview.hidden = false;
  };

  const load = async () => {
    tableState.loading(tbody, COLUMN_COUNT, "배지를 불러오는 중…");
    try {
      await loadBadgeTypes();
      const search = new FormData(searchForm);
      const response = await get("/admin/badges", {
        badge_id: search.get("badge_id")?.trim() || undefined,
        name: search.get("name")?.trim() || undefined,
        type: search.get("type") || undefined,
        is_active: search.get("is_active") || undefined,
        offset: 0,
        limit: 100,
      });
      if (!response.items.length) return tableState.empty(tbody, COLUMN_COUNT, "등록된 배지가 없습니다.");
      tbody.innerHTML = response.items.map((item) => `<tr>
        <td>${item.id}</td><td><img class="badge-thumbnail" src="/${escapeHtml(item.image_path)}" alt=""></td><td><strong>${escapeHtml(item.name)}</strong></td>
        <td>${escapeHtml(badgeTypes.find((type) => String(type.id) === String(item.type))?.detail_name ?? "-")}</td>
        <td><span class="status-badge ${item.is_active ? "status-active" : "status-stopped"}">${item.is_active ? "사용" : "미사용"}</span></td>
        <td>${badgeActionMarkup(item.id, item.is_deletable)}</td>
      </tr>`).join("");
    } catch (caught) {
      tableState.error(tbody, COLUMN_COUNT, caught instanceof ApiError ? caught.message : "배지 목록 조회에 실패했습니다.");
    }
  };

  const resetFormState = () => {
    form.reset();
    clearImagePreview();
    editing = null;
    error.textContent = "";
    document.body.classList.remove("modal-open");
  };
  const openDialog = () => {
    dialog.showModal();
    document.body.classList.add("modal-open");
  };
  const close = () => { if (dialog.open) dialog.close(); };
  document.querySelector("[data-create-badge]").addEventListener("click", async () => {
    resetFormState();
    try {
      await loadBadgeTypes();
      title.textContent = "배지 등록";
      form.elements.is_active.checked = true;
      openDialog();
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "배지 유형을 불러오지 못했습니다.");
    }
  });
  document.querySelectorAll("[data-close-form]").forEach((button) => button.addEventListener("click", close));
  dialog.addEventListener("close", resetFormState);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) close(); });

  const openEdit = async (id) => {
    try {
      await loadBadgeTypes();
      editing = await get(`/admin/badges/${id}`);
      clearImagePreview();
      form.elements.name.value = editing.name;
      form.elements.description.value = editing.description ?? "";
      form.elements.type.value = editing.type ?? "";
      form.elements.is_active.checked = editing.is_active;
      const existingFileName = editing.image_path.split("/").pop() || "등록된 배지 이미지";
      showImagePreview(`/${editing.image_path}`, existingFileName);
      title.textContent = "배지 수정";
      error.textContent = "";
      openDialog();
    } catch (caught) { window.alert(caught instanceof ApiError ? caught.message : "배지 정보를 불러오지 못했습니다."); }
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const image = form.elements.image.files[0];
    if (!editing && !image) { error.textContent = "배지 이미지를 선택해 주세요."; return; }
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      let paths = null;
      if (image) {
        const imageData = new FormData();
        imageData.append("image", image);
        paths = await request("/admin/badge-images", { method: "POST", body: imageData });
      }
      const payload = { name: form.elements.name.value.trim(), description: form.elements.description.value.trim() || null, type: Number(form.elements.type.value) || null, is_active: form.elements.is_active.checked };
      if (paths) Object.assign(payload, paths);
      if (editing) await patch(`/admin/badges/${editing.id}`, payload);
      else await post("/admin/badges", payload);
      close(); await load();
    } catch (caught) { error.textContent = caught instanceof ApiError || caught instanceof Error ? caught.message : "저장에 실패했습니다."; }
    finally { submit.disabled = false; }
  });

  searchForm.addEventListener("submit", (event) => { event.preventDefault(); void load(); });
  searchForm.addEventListener("reset", () => { window.setTimeout(() => void load(), 0); });
  searchForm.elements.badge_id.addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "");
  });

  document.querySelector("[data-select-badge-image]").addEventListener("click", () => imageInput.click());
  imageInput.addEventListener("change", () => {
    const image = imageInput.files[0];
    if (!image) {
      clearImagePreview();
      if (editing) {
        const existingFileName = editing.image_path.split("/").pop() || "등록된 배지 이미지";
        showImagePreview(`/${editing.image_path}`, existingFileName);
      }
      return;
    }
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = URL.createObjectURL(image);
    showImagePreview(previewObjectUrl, image.name);
  });

  tbody.addEventListener("click", async (event) => {
    if (event.target.closest("[data-retry]")) return load();
    const edit = event.target.closest("[data-edit-badge]");
    if (edit) return openEdit(edit.dataset.editBadge);
    const remove = event.target.closest("[data-delete-badge]");
    if (!remove || !window.confirm("배지를 삭제하시겠습니까?")) return;
    remove.disabled = true;
    try {
      await request(`/admin/badges/${remove.dataset.deleteBadge}`, { method: "DELETE" });
      await load();
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "배지 삭제에 실패했습니다.");
      remove.disabled = false;
    }
  });
  void load();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializeBadgeManagement, { once: true });
  else initializeBadgeManagement();
}
