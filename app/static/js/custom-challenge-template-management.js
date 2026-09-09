import { ApiError, escapeHtml, get, patch, post, requireLogin, tableState } from "./api.js";

const COLUMN_COUNT = 6;
export const CUSTOM_TEMPLATE_CHECK_TYPE_PATH = "/common-codes/CHL/CST_CHK_TYPE";
export const CUSTOM_TEMPLATE_CHALLENGE_TYPE_PATH = "/common-codes/CHL/CST_CHL_TYPE";
export const CUSTOM_TEMPLATE_BADGE_TYPE_PATH = "/common-codes/CHL/BDG_TYPE";

export function customBadgeTypeId(items) {
  return items.find((item) => item.detail_code === "CUSTOM")?.id ?? null;
}

export function resetCustomTemplateFilters(form) {
  form.elements.template_id.value = "";
  form.elements.name.value = "";
  form.elements.challenge_type.value = "";
  form.elements.check_type_id.value = "";
  form.elements.is_active.value = "";
}

function initializeCustomChallengeTemplateManagement() {
  const tbody = document.querySelector("[data-custom-template-rows]");
  const searchForm = document.querySelector("[data-custom-template-search]");
  const dialog = document.querySelector("[data-custom-template-dialog]");
  const form = document.querySelector("[data-custom-template-form]");
  if (!tbody || !searchForm || !dialog || !form || !requireLogin()) return;

  const error = form.querySelector("[data-form-error]");
  const formTitle = form.querySelector("[data-form-title]");
  let editingId = null;
  let checkTypes = [];
  let challengeTypes = [];
  let badges = [];

  const optionMarkup = (selected = "") => checkTypes
    .map((item) => `<option value="${item.id}" ${String(item.id) === String(selected) ? "selected" : ""}>${escapeHtml(item.detail_name)}</option>`)
    .join("");

  const loadLookups = async () => {
    if (!checkTypes.length || !challengeTypes.length) {
      const [checkTypeResponse, challengeTypeResponse, badgeTypeResponse] = await Promise.all([
        get(CUSTOM_TEMPLATE_CHECK_TYPE_PATH),
        get(CUSTOM_TEMPLATE_CHALLENGE_TYPE_PATH),
        get(CUSTOM_TEMPLATE_BADGE_TYPE_PATH),
      ]);
      const badgeTypeId = customBadgeTypeId(badgeTypeResponse.items);
      if (!badgeTypeId) throw new Error("CUSTOM 배지 유형을 찾을 수 없습니다.");
      const badgeResponse = await get("/admin/badges", {
        type: badgeTypeId,
        is_active: true,
        offset: 0,
        limit: 100,
      });
      checkTypes = checkTypeResponse.items;
      challengeTypes = challengeTypeResponse.items;
      badges = badgeResponse.items;
    }
    const selectedSearch = searchForm.elements.check_type_id.value;
    searchForm.elements.check_type_id.innerHTML = `<option value="">인증방식</option>${optionMarkup(selectedSearch)}`;
    const selectedChallengeType = searchForm.elements.challenge_type.value;
    const challengeTypeOptions = challengeTypes
      .map((item) => `<option value="${item.id}">${escapeHtml(item.detail_name)}</option>`)
      .join("");
    searchForm.elements.challenge_type.innerHTML = `<option value="">챌린지유형</option>${challengeTypeOptions}`;
    searchForm.elements.challenge_type.value = selectedChallengeType;
    form.elements.check_type_id.innerHTML = `<option value="">선택</option>${optionMarkup()}`;
    form.elements.challenge_type.innerHTML = `<option value="">선택</option>${challengeTypeOptions}`;
    form.elements.reward_badge_id.innerHTML = `<option value="">선택 안 함</option>${badges
      .map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`)
      .join("")}`;
  };

  const checkTypeName = (id) => checkTypes.find((item) => String(item.id) === String(id))?.detail_name ?? "-";
  const challengeTypeName = (id) => challengeTypes.find((item) => String(item.id) === String(id))?.detail_name ?? "-";

  const load = async () => {
    tableState.loading(tbody, COLUMN_COUNT, "맞춤 챌린지 템플릿을 불러오는 중…");
    try {
      await loadLookups();
      const search = new FormData(searchForm);
      const response = await get("/admin/custom-challenge-templates", {
        template_id: search.get("template_id")?.trim() || undefined,
        name: search.get("name")?.trim() || undefined,
        challenge_type: search.get("challenge_type") || undefined,
        check_type_id: search.get("check_type_id") || undefined,
        is_active: search.get("is_active") || undefined,
        offset: 0,
        limit: 100,
      });
      if (!response.items.length) return tableState.empty(tbody, COLUMN_COUNT, "조회 결과가 없습니다.");
      tbody.innerHTML = response.items.map((item) => `<tr>
        <td>${item.id}</td>
        <td><strong>${escapeHtml(item.name)}</strong></td>
        <td>${escapeHtml(challengeTypeName(item.challenge_type))}</td>
        <td>${escapeHtml(checkTypeName(item.check_type_id))}</td>
        <td><span class="status-badge ${item.is_active ? "status-active" : "status-stopped"}">${item.is_active ? "사용" : "미사용"}</span></td>
        <td><button type="button" class="ui-link-button" data-edit-custom-template="${item.id}">수정</button></td>
      </tr>`).join("");
    } catch (caught) {
      tableState.error(tbody, COLUMN_COUNT, caught instanceof ApiError ? caught.message : "템플릿 목록 조회에 실패했습니다.");
    }
  };

  const resetForm = () => {
    form.reset();
    editingId = null;
    error.textContent = "";
    document.body.classList.remove("modal-open");
  };
  const openDialog = () => {
    dialog.showModal();
    document.body.classList.add("modal-open");
  };
  const closeDialog = () => { if (dialog.open) dialog.close(); };

  document.querySelector("[data-create-custom-template]").addEventListener("click", async () => {
    resetForm();
    try {
      await loadLookups();
      formTitle.textContent = "맞춤 챌린지 템플릿 등록";
      form.elements.is_active.checked = true;
      openDialog();
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "등록 정보를 불러오지 못했습니다.");
    }
  });

  const openEdit = async (id) => {
    try {
      await loadLookups();
      const item = await get(`/admin/custom-challenge-templates/${id}`);
      editingId = item.id;
      form.elements.name.value = item.name;
      form.elements.check_type_id.value = item.check_type_id;
      form.elements.challenge_type.value = item.challenge_type ?? "";
      form.elements.reward_badge_id.value = item.reward_badge_id ?? "";
      form.elements.is_active.checked = item.is_active;
      formTitle.textContent = "맞춤 챌린지 템플릿 수정";
      error.textContent = "";
      openDialog();
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "템플릿 정보를 불러오지 못했습니다.");
    }
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    error.textContent = "";
    try {
      const payload = {
        name: form.elements.name.value.trim(),
        check_type_id: Number(form.elements.check_type_id.value),
        challenge_type: Number(form.elements.challenge_type.value) || null,
        reward_badge_id: Number(form.elements.reward_badge_id.value) || null,
        is_active: form.elements.is_active.checked,
      };
      if (editingId) await patch(`/admin/custom-challenge-templates/${editingId}`, payload);
      else await post("/admin/custom-challenge-templates", payload);
      closeDialog();
      await load();
    } catch (caught) {
      error.textContent = caught instanceof ApiError || caught instanceof Error ? caught.message : "저장에 실패했습니다.";
    } finally {
      submit.disabled = false;
    }
  });

  searchForm.addEventListener("submit", (event) => { event.preventDefault(); void load(); });
  searchForm.addEventListener("reset", (event) => {
    event.preventDefault();
    resetCustomTemplateFilters(searchForm);
    void load();
  });
  searchForm.elements.template_id.addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "");
  });
  document.querySelectorAll("[data-close-form]").forEach((button) => button.addEventListener("click", closeDialog));
  dialog.addEventListener("close", resetForm);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) closeDialog(); });
  tbody.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-edit-custom-template]");
    if (edit) void openEdit(edit.dataset.editCustomTemplate);
  });

  void load();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeCustomChallengeTemplateManagement, { once: true });
  } else {
    initializeCustomChallengeTemplateManagement();
  }
}
