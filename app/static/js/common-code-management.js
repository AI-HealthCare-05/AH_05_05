import { ApiError, escapeHtml, get, patch, post, requireLogin, session, tableState } from "./api.js";

const PAGE_SIZE = 20;
const CODE_PATTERN = /^[A-Z0-9_]+$/;
const COLUMN_COUNT = 5;

export function normalizeCodeInput(value) {
  return String(value ?? "").trim().toUpperCase();
}

export function isValidCodeInput(value) {
  return CODE_PATTERN.test(normalizeCodeInput(value));
}

export function sanitizeGroupCodeInput(value) {
  return normalizeCodeInput(value).replace(/[^A-Z0-9_]/g, "").slice(0, 20);
}

export function sanitizeDetailCodeInput(value) {
  return normalizeCodeInput(value).replace(/[^A-Z0-9_]/g, "").slice(0, 20);
}

export function sanitizeSortOrderInput(value) {
  return String(value ?? "").replace(/\D/g, "");
}

export function parseSortOrder(value) {
  const sanitized = sanitizeSortOrderInput(value);
  return sanitized ? Number(sanitized) : null;
}

export function buildGroupQuery({ category, groupCode, groupName, isActive, page = 1, size = PAGE_SIZE }) {
  return {
    category: sanitizeGroupCodeInput(category),
    group_code: sanitizeGroupCodeInput(groupCode),
    group_name: String(groupName ?? "").trim(),
    is_active: isActive,
    offset: (page - 1) * size,
    limit: size,
  };
}

export function buildGroupPayload(values, editing) {
  const payload = {
    group_name: String(values.groupName ?? "").trim(),
    description: String(values.description ?? "").trim() || null,
    is_active: Boolean(values.isActive),
  };
  if (!editing) {
    payload.category = sanitizeGroupCodeInput(values.category);
    payload.group_code = sanitizeGroupCodeInput(values.groupCode);
  }
  return payload;
}

function buildCodeQuery(form, page) {
  return {
    detail_code: normalizeCodeInput(form.elements.detail_code.value),
    detail_name: form.elements.detail_name.value.trim(),
    is_active: form.elements.is_active.value,
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
}

function message(error, fallback) {
  return error instanceof ApiError ? error.message : fallback;
}

function renderPagination(root, total, page, onPage) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (!total) {
    root.replaceChildren();
    return;
  }
  const previous = document.createElement("button");
  previous.type = "button";
  previous.className = "ui-button";
  previous.textContent = "이전";
  previous.disabled = page <= 1;
  previous.addEventListener("click", () => onPage(page - 1));
  const label = document.createElement("span");
  label.textContent = `${page} / ${pages}`;
  const next = document.createElement("button");
  next.type = "button";
  next.className = "ui-button";
  next.textContent = "다음";
  next.disabled = page >= pages;
  next.addEventListener("click", () => onPage(page + 1));
  root.replaceChildren(previous, label, next);
}

function statusBadge(active) {
  return `<span class="status-badge ${active ? "status-active" : "status-stopped"}">${active ? "사용" : "미사용"}</span>`;
}

function initializeCommonCodeManagement() {
  const groupSearch = document.querySelector("[data-group-search]");
  const groupList = document.querySelector("[data-group-list]");
  const codeSearch = document.querySelector("[data-code-search]");
  const codeList = document.querySelector("[data-code-list]");
  if (!groupSearch || !groupList || !codeSearch || !codeList || !requireLogin()) return;

  const isAdmin = session.isAdminRole();
  const groupPagination = document.querySelector("[data-group-pagination]");
  const codePagination = document.querySelector("[data-code-pagination]");
  const groupTotal = document.querySelector("[data-group-total]");
  const selectedGroupText = document.querySelector("[data-selected-group]");
  const groupDialog = document.querySelector("[data-group-dialog]");
  const codeDialog = document.querySelector("[data-code-dialog]");
  const groupForm = document.querySelector("[data-group-form]");
  const codeForm = document.querySelector("[data-code-form]");
  const codeCreate = document.querySelector("[data-code-create]");
  let groupPage = 1;
  let codePage = 1;
  let selectedGroup = null;
  let editingGroup = null;
  let editingCode = null;
  let groupItems = [];
  let codeItems = [];

  if (!isAdmin) document.querySelectorAll("[data-write-control]").forEach((node) => node.remove());
  document.querySelectorAll(".common-code-input").forEach((input) => {
    input.addEventListener("input", () => {
      input.value = sanitizeGroupCodeInput(input.value);
    });
  });
  document.querySelectorAll(".detail-code-input").forEach((input) => {
    input.addEventListener("input", () => {
      input.value = sanitizeDetailCodeInput(input.value);
    });
  });
  codeForm.elements.sort_order.addEventListener("input", (event) => {
    event.currentTarget.value = sanitizeSortOrderInput(event.currentTarget.value).slice(0, 2);
  });

  const renderGroups = (items) => {
    groupItems = items;
    if (!items.length) {
      tableState.empty(groupList, COLUMN_COUNT, "조회 결과가 없습니다.");
      return;
    }
    groupList.innerHTML = items.map((group) => `<tr data-group-id="${group.id}" class="${selectedGroup?.id === group.id ? "is-selected" : ""}">
      <td>${escapeHtml(group.category)}</td><td><strong>${escapeHtml(group.group_code)}</strong></td>
      <td>${escapeHtml(group.group_name)}</td><td>${statusBadge(group.is_active)}</td>
      <td>${isAdmin ? `<button type="button" class="ui-link-button" data-edit-group="${group.id}">수정</button>` : "-"}</td>
    </tr>`).join("");
  };

  const renderCodes = (items) => {
    codeItems = items;
    if (!items.length) {
      tableState.empty(codeList, COLUMN_COUNT, "조회 결과가 없습니다.");
      return;
    }
    codeList.innerHTML = items.map((code) => `<tr>
      <td><strong>${escapeHtml(code.detail_code)}</strong></td><td>${escapeHtml(code.detail_name)}</td>
      <td>${code.sort_order}</td><td>${statusBadge(code.is_active)}</td>
      <td>${isAdmin ? `<button type="button" class="ui-link-button" data-edit-code="${code.id}">수정</button>` : "-"}</td>
    </tr>`).join("");
  };

  const loadCodes = async (page = 1) => {
    if (!selectedGroup) return;
    codePage = page;
    tableState.loading(codeList, COLUMN_COUNT);
    try {
      const result = await get(`/admin/common-code-groups/${selectedGroup.id}/codes`, buildCodeQuery(codeSearch, page));
      renderCodes(result.items);
      renderPagination(codePagination, result.total_count, page, loadCodes);
    } catch (error) {
      tableState.error(codeList, COLUMN_COUNT, message(error, "상세 코드를 불러오지 못했습니다."));
    }
  };

  const selectGroup = (group) => {
    selectedGroup = group;
    codePage = 1;
    selectedGroupText.textContent = `${group.category} / ${group.group_code} · ${group.group_name}`;
    if (codeCreate) codeCreate.disabled = false;
    renderGroups(groupItems);
    void loadCodes();
  };

  const loadGroups = async (page = 1) => {
    groupPage = page;
    tableState.loading(groupList, COLUMN_COUNT);
    const query = buildGroupQuery({
      category: groupSearch.elements.category.value,
      groupCode: groupSearch.elements.group_code.value,
      groupName: groupSearch.elements.group_name.value,
      isActive: groupSearch.elements.is_active.value,
      page,
    });
    try {
      const result = await get("/admin/common-code-groups", query);
      if (selectedGroup && !result.items.some((item) => item.id === selectedGroup.id)) {
        selectedGroup = null;
        selectedGroupText.textContent = "왼쪽에서 코드 그룹을 선택해 주세요.";
        tableState.empty(codeList, COLUMN_COUNT, "코드 그룹을 선택해 주세요.");
        codePagination.replaceChildren();
        if (codeCreate) codeCreate.disabled = true;
      }
      renderGroups(result.items);
      groupTotal.textContent = `총 ${result.total_count}건`;
      renderPagination(groupPagination, result.total_count, page, loadGroups);
    } catch (error) {
      groupTotal.textContent = "총 -건";
      tableState.error(groupList, COLUMN_COUNT, message(error, "코드 그룹을 불러오지 못했습니다."));
    }
  };

  function openGroup(group = null) {
    editingGroup = group;
    groupForm.reset();
    groupForm.elements.is_active.checked = group?.is_active ?? true;
    groupForm.elements.category.value = group?.category ?? "";
    groupForm.elements.category.disabled = Boolean(group);
    groupForm.elements.group_code.value = group?.group_code ?? "";
    groupForm.elements.group_code.disabled = Boolean(group);
    groupForm.elements.group_name.value = group?.group_name ?? "";
    groupForm.elements.description.value = group?.description ?? "";
    document.querySelector("[data-group-dialog-title]").textContent = group ? "코드 그룹 수정" : "코드 그룹 등록";
    document.querySelector("[data-group-form-error]").textContent = "";
    groupDialog.showModal();
  }

  function openCode(code = null) {
    editingCode = code;
    codeForm.reset();
    codeForm.elements.is_active.checked = code?.is_active ?? true;
    codeForm.elements.detail_code.value = code?.detail_code ?? "";
    codeForm.elements.detail_code.disabled = Boolean(code);
    codeForm.elements.detail_name.value = code?.detail_name ?? "";
    codeForm.elements.description.value = code?.description ?? "";
    codeForm.elements.sort_order.value = code?.sort_order ?? 0;
    document.querySelector("[data-code-dialog-title]").textContent = code ? "상세 코드 수정" : "상세 코드 등록";
    document.querySelector("[data-code-form-error]").textContent = "";
    codeDialog.showModal();
  }

  groupSearch.addEventListener("submit", (event) => { event.preventDefault(); void loadGroups(1); });
  groupSearch.addEventListener("reset", () => queueMicrotask(() => void loadGroups(1)));
  codeSearch.addEventListener("submit", (event) => { event.preventDefault(); void loadCodes(1); });
  codeSearch.addEventListener("reset", () => queueMicrotask(() => void loadCodes(1)));
  document.querySelector("[data-group-create]")?.addEventListener("click", () => openGroup());
  codeCreate?.addEventListener("click", () => openCode());

  groupList.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-edit-group]");
    if (edit) {
      event.stopPropagation();
      openGroup(groupItems.find((item) => item.id === Number(edit.dataset.editGroup)));
      return;
    }
    const row = event.target.closest("[data-group-id]");
    const group = groupItems.find((item) => item.id === Number(row?.dataset.groupId));
    if (group) selectGroup(group);
  });
  codeList.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-edit-code]");
    const code = codeItems.find((item) => item.id === Number(edit?.dataset.editCode));
    if (code) openCode(code);
  });

  document.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });

  groupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const category = sanitizeGroupCodeInput(groupForm.elements.category.value);
    const groupCode = sanitizeGroupCodeInput(groupForm.elements.group_code.value);
    const errorRoot = document.querySelector("[data-group-form-error]");
    if (!editingGroup && (!isValidCodeInput(category) || !isValidCodeInput(groupCode))) {
      errorRoot.textContent = "대분류와 코드그룹은 영문, 숫자, 밑줄만 입력해 주세요.";
      return;
    }
    const payload = buildGroupPayload({
      category,
      groupCode,
      groupName: groupForm.elements.group_name.value,
      description: groupForm.elements.description.value.trim() || null,
      isActive: groupForm.elements.is_active.checked,
    }, Boolean(editingGroup));
    try {
      await (editingGroup ? patch(`/admin/common-code-groups/${editingGroup.id}`, payload) : post("/admin/common-code-groups", payload));
      groupDialog.close();
      await loadGroups(editingGroup ? groupPage : 1);
    } catch (error) {
      errorRoot.textContent = message(error, "코드 그룹을 저장하지 못했습니다.");
    }
  });

  codeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedGroup) return;
    const detailCode = normalizeCodeInput(codeForm.elements.detail_code.value);
    const errorRoot = document.querySelector("[data-code-form-error]");
    if (!editingCode && (!detailCode || !/^[A-Z0-9_]+$/.test(detailCode))) {
      errorRoot.textContent = "상세코드는 영문, 숫자, 밑줄만 입력해 주세요.";
      return;
    }
    const sortOrder = parseSortOrder(codeForm.elements.sort_order.value);
    if (sortOrder === null || sortOrder > 99) {
      errorRoot.textContent = "정렬순서는 0부터 99까지 입력해 주세요.";
      return;
    }
    const payload = {
      detail_name: codeForm.elements.detail_name.value.trim(),
      description: codeForm.elements.description.value.trim() || null,
      sort_order: sortOrder,
      is_active: codeForm.elements.is_active.checked,
    };
    if (!editingCode) payload.detail_code = detailCode;
    try {
      await (editingCode ? patch(`/admin/common-codes/${editingCode.id}`, payload) : post(`/admin/common-code-groups/${selectedGroup.id}/codes`, payload));
      codeDialog.close();
      await loadCodes(editingCode ? codePage : 1);
    } catch (error) {
      errorRoot.textContent = message(error, "상세 코드를 저장하지 못했습니다.");
    }
  });

  void loadGroups();
}

if (typeof document !== "undefined") initializeCommonCodeManagement();
