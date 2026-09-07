import { ApiError, escapeHtml, get, patch, post, request, requireLogin, tableState } from "./api.js";

const CHALLENGE_COLUMN_COUNT = 5;
const BADGE_SEARCH_COLUMN_COUNT = 3;

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(value),
  );
}

function toLocalDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function optionMarkup(items, selected = "") {
  return items
    .map(
      (item) =>
        `<option value="${item.id}" ${String(item.id) === String(selected) ? "selected" : ""}>${escapeHtml(item.detail_name)}</option>`,
    )
    .join("");
}

function initializeChallengeManagement() {
  const tbody = document.querySelector("[data-challenge-rows]");
  const form = document.querySelector("[data-challenge-form]");
  const searchForm = document.querySelector("[data-challenge-search]");
  const badgeDialog = document.querySelector("[data-badge-search-dialog]");
  const badgeSearchForm = document.querySelector("[data-badge-search-form]");
  const badgeSearchRows = document.querySelector("[data-badge-search-rows]");
  if (
    !tbody ||
    !form ||
    !searchForm ||
    !badgeDialog ||
    !badgeSearchForm ||
    !badgeSearchRows ||
    !requireLogin()
  ) {
    return;
  }

  const error = form.querySelector("[data-form-error]");
  const title = form.querySelector("[data-form-title]");
  let editingId = null;
  let lookups;
  let currentFilters = {};
  let badgeSearchItems = new Map();

  const clearSelectedBadge = () => {
    form.elements.reward_badge_id.value = "";
    form.elements.reward_badge_name.value = "";
  };

  const loadLookups = async () => {
    if (!lookups) {
      const [types, periods, checkTypes, frequencies] = await Promise.all([
        get("/common-codes/CHL/CHL_TYPE"),
        get("/common-codes/CHL/CHL_PERIOD"),
        get("/common-codes/CHL/CHK_TYPE"),
        get("/common-codes/CHL/CHK_FREQ"),
      ]);
      lookups = {
        types: types.items,
        periods: periods.items,
        checkTypes: checkTypes.items,
        frequencies: frequencies.items,
      };
    }

    const selectedSearchType = searchForm.elements.challenge_type_id.value;
    searchForm.elements.challenge_type_id.innerHTML =
      `<option value="">전체</option>${optionMarkup(lookups.types, selectedSearchType)}`;
    form.elements.challenge_type_id.innerHTML = optionMarkup(lookups.types);
    form.elements.challenge_period_id.innerHTML = optionMarkup(lookups.periods);
    form.elements.check_type_id.innerHTML = optionMarkup(lookups.checkTypes);
    form.elements.check_frequency_id.innerHTML = optionMarkup(lookups.frequencies);
  };

  const load = async () => {
    tableState.loading(tbody, CHALLENGE_COLUMN_COUNT, "챌린지를 불러오는 중…");
    try {
      const response = await get("/admin/challenges", {
        ...currentFilters,
        offset: 0,
        limit: 100,
      });
      if (!response.items.length) {
        return tableState.empty(tbody, CHALLENGE_COLUMN_COUNT, "조회 결과가 없습니다.");
      }
      tbody.innerHTML = response.items
        .map(
          (item) => `<tr>
            <td>${item.id}</td><td><strong>${escapeHtml(item.name)}</strong></td>
            <td>${escapeHtml(formatDateTime(item.recruit_start_at))} ~ ${escapeHtml(formatDateTime(item.recruit_end_at))}</td>
            <td><span class="status-badge ${item.is_displayed ? "status-active" : "status-stopped"}">${item.is_displayed ? "전시" : "미전시"}</span></td>
            <td><button type="button" class="ui-link-button" data-edit-challenge="${item.id}">수정</button> <button type="button" class="ui-link-button ui-link-button-danger" data-delete-challenge="${item.id}">삭제</button></td>
          </tr>`,
        )
        .join("");
    } catch (caught) {
      tableState.error(
        tbody,
        CHALLENGE_COLUMN_COUNT,
        caught instanceof ApiError ? caught.message : "챌린지 목록 조회에 실패했습니다.",
      );
    }
  };

  const close = () => {
    form.hidden = true;
    form.reset();
    clearSelectedBadge();
    editingId = null;
    error.textContent = "";
  };

  const openCreate = async () => {
    close();
    try {
      await loadLookups();
      title.textContent = "챌린지 등록";
      form.hidden = false;
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "등록 정보를 불러오지 못했습니다.");
    }
  };

  const openEdit = async (id) => {
    try {
      await loadLookups();
      const item = await get(`/admin/challenges/${id}`);
      editingId = item.id;
      for (const key of ["name", "phrase", "description"]) {
        form.elements[key].value = item[key] ?? "";
      }
      for (const key of [
        "challenge_type_id",
        "challenge_period_id",
        "check_type_id",
        "check_frequency_id",
      ]) {
        form.elements[key].value = item[key] ?? "";
      }
      clearSelectedBadge();
      if (item.reward_badge_id) {
        const badge = await get(`/admin/badges/${item.reward_badge_id}`);
        form.elements.reward_badge_id.value = badge.id;
        form.elements.reward_badge_name.value = badge.name;
      }
      form.elements.recruit_start_at.value = toLocalDateTime(item.recruit_start_at);
      form.elements.recruit_end_at.value = toLocalDateTime(item.recruit_end_at);
      form.elements.is_displayed.checked = item.is_displayed;
      title.textContent = "챌린지 수정";
      error.textContent = "";
      form.hidden = false;
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "챌린지 정보를 불러오지 못했습니다.");
    }
  };

  const badgeSearchParams = () => {
    const badgeId = badgeSearchForm.elements.badge_id.value.trim();
    return {
      badge_id: badgeId ? Number(badgeId) : undefined,
      name: badgeSearchForm.elements.name.value.trim(),
      is_active: true,
      offset: 0,
      limit: 100,
    };
  };

  const loadBadgeSearch = async () => {
    tableState.loading(badgeSearchRows, BADGE_SEARCH_COLUMN_COUNT, "배지를 불러오는 중…");
    try {
      const response = await get("/admin/badges", badgeSearchParams());
      badgeSearchItems = new Map(response.items.map((item) => [String(item.id), item]));
      if (!response.items.length) {
        return tableState.empty(badgeSearchRows, BADGE_SEARCH_COLUMN_COUNT, "조회 결과가 없습니다.");
      }
      badgeSearchRows.innerHTML = response.items
        .map(
          (item) => `<tr>
            <td>${item.id}</td>
            <td>${escapeHtml(item.name)}</td>
            <td><button type="button" class="ui-button ui-button-primary ui-button-small" data-select-badge="${item.id}">선택</button></td>
          </tr>`,
        )
        .join("");
    } catch (caught) {
      tableState.error(
        badgeSearchRows,
        BADGE_SEARCH_COLUMN_COUNT,
        caught instanceof ApiError ? caught.message : "배지 목록 조회에 실패했습니다.",
      );
    }
  };

  const openBadgeSearch = () => {
    badgeSearchForm.reset();
    badgeDialog.showModal();
    void loadBadgeSearch();
  };

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const startDate = searchForm.elements.recruit_start_date.value;
    const endDate = searchForm.elements.recruit_end_date.value;
    if (startDate && endDate && endDate < startDate) {
      window.alert("조회 기간이 올바르지 않습니다.");
      searchForm.elements.recruit_end_date.value = "";
      return;
    }
    const displayed = searchForm.elements.is_displayed.value;
    currentFilters = {
      name: searchForm.elements.name.value.trim(),
      challenge_type_id: searchForm.elements.challenge_type_id.value || undefined,
      is_displayed: displayed === "" ? undefined : displayed === "true",
      recruit_start_date: startDate,
      recruit_end_date: endDate,
    };
    void load();
  });

  document.querySelector("[data-reset-challenge-search]").addEventListener("click", (event) => {
    event.preventDefault();
    searchForm.reset();
    currentFilters = {};
    void load();
  });

  badgeSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void loadBadgeSearch();
  });
  badgeSearchForm.elements.badge_id.addEventListener("input", (event) => {
    event.currentTarget.value = event.currentTarget.value.replace(/\D/g, "").slice(0, 20);
  });
  document.querySelector("[data-reset-badge-search]").addEventListener("click", (event) => {
    event.preventDefault();
    badgeSearchForm.reset();
    void loadBadgeSearch();
  });
  document.querySelectorAll("[data-close-badge-dialog]").forEach((button) => {
    button.addEventListener("click", () => badgeDialog.close());
  });
  badgeSearchRows.addEventListener("click", (event) => {
    if (event.target.closest("[data-retry]")) return loadBadgeSearch();
    const selectButton = event.target.closest("[data-select-badge]");
    if (!selectButton) return;
    const selected = badgeSearchItems.get(selectButton.dataset.selectBadge);
    if (!selected) return;
    form.elements.reward_badge_id.value = selected.id;
    form.elements.reward_badge_name.value = selected.name;
    badgeDialog.close();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    if (new Date(data.get("recruit_end_at")) <= new Date(data.get("recruit_start_at"))) {
      error.textContent = "모집 종료 일시는 모집 시작 일시보다 늦어야 합니다.";
      return;
    }
    const payload = {
      name: data.get("name").trim(),
      challenge_type_id: Number(data.get("challenge_type_id")),
      phrase: data.get("phrase").trim(),
      description: data.get("description").trim() || null,
      recruit_start_at: data.get("recruit_start_at"),
      recruit_end_at: data.get("recruit_end_at"),
      challenge_period_id: Number(data.get("challenge_period_id")),
      check_type_id: Number(data.get("check_type_id")),
      check_frequency_id: Number(data.get("check_frequency_id")),
      reward_badge_id: data.get("reward_badge_id") ? Number(data.get("reward_badge_id")) : null,
      is_displayed: form.elements.is_displayed.checked,
    };
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      if (editingId) await patch(`/admin/challenges/${editingId}`, payload);
      else await post("/admin/challenges", payload);
      close();
      await load();
    } catch (caught) {
      error.textContent = caught instanceof ApiError ? caught.message : "저장에 실패했습니다.";
    } finally {
      submit.disabled = false;
    }
  });

  document.querySelector("[data-create-challenge]").addEventListener("click", openCreate);
  document.querySelector("[data-open-badge-search]").addEventListener("click", openBadgeSearch);
  document.querySelector("[data-clear-badge]").addEventListener("click", clearSelectedBadge);
  document.querySelectorAll("[data-close-form]").forEach((button) => {
    button.addEventListener("click", close);
  });
  tbody.addEventListener("click", async (event) => {
    if (event.target.closest("[data-retry]")) return load();
    const edit = event.target.closest("[data-edit-challenge]");
    if (edit) return openEdit(edit.dataset.editChallenge);
    const remove = event.target.closest("[data-delete-challenge]");
    if (remove && window.confirm("이 챌린지를 삭제하시겠습니까?")) {
      try {
        await request(`/admin/challenges/${remove.dataset.deleteChallenge}`, { method: "DELETE" });
        await load();
      } catch (caught) {
        window.alert(caught instanceof ApiError ? caught.message : "삭제에 실패했습니다.");
      }
    }
  });

  void loadLookups().catch(() => {});
  void load();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeChallengeManagement, { once: true });
  } else {
    initializeChallengeManagement();
  }
}
