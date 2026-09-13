import { ApiError, escapeHtml, get, patch, post, request, requireLogin, tableState } from "./api.js";

const CHALLENGE_COLUMN_COUNT = 5;
const PARTICIPANT_COLUMN_COUNT = 2;
const PARTICIPANT_PAGE_SIZE = 20;
export const CHALLENGE_BADGE_TYPE_PATH = "/common-codes/CHL/BDG_TYPE";

export function standardBadgeTypeId(items) {
  return items.find((item) => item.detail_code === "STANDARD")?.id ?? null;
}

export function challengeActionMarkup(challengeId, isDeletable = true) {
  const disabled = isDeletable
    ? ""
    : ' disabled aria-disabled="true" title="참여자가 있는 챌린지는 삭제할 수 없습니다."';
  return `<button type="button" class="ui-link-button" data-edit-challenge="${challengeId}">수정</button> <button type="button" class="ui-link-button ui-link-button-danger" data-delete-challenge="${challengeId}"${disabled}>삭제</button>`;
}

export function challengePrimaryActionState(participantCount) {
  const opensParticipants = Number(participantCount) > 0;
  return {
    type: opensParticipants ? "button" : "submit",
    label: opensParticipants ? "챌린지 참여 확인" : "저장",
    opensParticipants,
  };
}

export function challengeParticipantPagination(totalCount, requestedPage) {
  const totalPages = Math.max(1, Math.ceil(Number(totalCount) / PARTICIPANT_PAGE_SIZE));
  const currentPage = Math.min(Math.max(1, Number(requestedPage) || 1), totalPages);
  const startPage = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
  const pages = Array.from(
    { length: Math.min(5, totalPages - startPage + 1) },
    (_, index) => startPage + index,
  );
  return {
    currentPage,
    totalPages,
    pages,
    hasPrevious: currentPage > 1,
    hasNext: currentPage < totalPages,
    pageSize: PARTICIPANT_PAGE_SIZE,
  };
}

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
  const primaryAction = form?.querySelector("[data-challenge-primary-action]");
  const participantDialog = document.querySelector("[data-challenge-participant-dialog]");
  const participantRows = document.querySelector("[data-challenge-participant-rows]");
  const participantTotal = document.querySelector("[data-challenge-participant-total]");
  const participantPagination = document.querySelector("[data-challenge-participant-pagination]");
  if (
    !tbody
    || !form
    || !searchForm
    || !primaryAction
    || !participantDialog
    || !participantRows
    || !participantTotal
    || !participantPagination
    || !requireLogin()
  ) {
    return;
  }

  const error = form.querySelector("[data-form-error]");
  const title = form.querySelector("[data-form-title]");
  let editingId = null;
  let participantPage = 1;
  let participantCount = 0;
  let lookups;
  let currentFilters = {};

  const applyPrimaryAction = (count) => {
    participantCount = Number(count) || 0;
    const state = challengePrimaryActionState(participantCount);
    primaryAction.type = state.type;
    primaryAction.textContent = state.label;
    primaryAction.dataset.opensParticipants = String(state.opensParticipants);
  };

  const renderParticipantPagination = () => {
    const state = challengeParticipantPagination(participantCount, participantPage);
    participantPage = state.currentPage;
    participantPagination.innerHTML = `
      <button class="ui-button" type="button" data-challenge-participant-page="${state.currentPage - 1}" ${state.hasPrevious ? "" : "disabled"}>이전</button>
      <div class="challenge-participant-pagination-pages">
        ${state.pages
          .map(
            (pageNumber) =>
              `<button class="ui-button challenge-participant-page-button${pageNumber === state.currentPage ? " is-active" : ""}" type="button" data-challenge-participant-page="${pageNumber}" ${pageNumber === state.currentPage ? 'aria-current="page"' : ""}>${pageNumber}</button>`,
          )
          .join("")}
      </div>
      <button class="ui-button" type="button" data-challenge-participant-page="${state.currentPage + 1}" ${state.hasNext ? "" : "disabled"}>다음</button>`;
  };

  const renderParticipants = (response, page) => {
    participantCount = Number(response.total_count) || 0;
    participantTotal.textContent = String(participantCount);
    participantPage = challengeParticipantPagination(participantCount, page).currentPage;
    if (!response.items.length) {
      tableState.empty(participantRows, PARTICIPANT_COLUMN_COUNT, "참여 내역이 없습니다.");
    } else {
      participantRows.innerHTML = response.items
        .map(
          (item) => `<tr>
            <td>${escapeHtml(item.masked_name)}</td>
            <td>${escapeHtml(formatDateTime(item.started_at))}</td>
          </tr>`,
        )
        .join("");
    }
    renderParticipantPagination();
  };

  const loadParticipants = async (page = 1) => {
    tableState.loading(participantRows, PARTICIPANT_COLUMN_COUNT, "참여 내역을 불러오는 중…");
    const response = await get(`/admin/challenges/${editingId}/participants`, {
      offset: (page - 1) * PARTICIPANT_PAGE_SIZE,
      limit: PARTICIPANT_PAGE_SIZE,
    });
    renderParticipants(response, page);
    return response;
  };

  const clearSelectedBadge = () => {
    form.elements.reward_badge_id.value = "";
  };

  const loadLookups = async () => {
    if (!lookups) {
      const [types, periods, checkTypes, frequencies, badgeTypes] = await Promise.all([
        get("/common-codes/CHL/CHL_TYPE"),
        get("/common-codes/CHL/CHL_PERIOD"),
        get("/common-codes/CHL/CHK_TYPE"),
        get("/common-codes/CHL/CHK_FREQ"),
        get(CHALLENGE_BADGE_TYPE_PATH),
      ]);
      const badgeTypeId = standardBadgeTypeId(badgeTypes.items);
      if (!badgeTypeId) throw new Error("STANDARD 배지 유형을 찾을 수 없습니다.");
      const badges = await get("/admin/badges", {
        type: badgeTypeId,
        is_active: true,
        offset: 0,
        limit: 100,
      });
      lookups = {
        types: types.items,
        periods: periods.items,
        checkTypes: checkTypes.items,
        frequencies: frequencies.items,
        badges: badges.items,
      };
    }

    const selectedSearchType = searchForm.elements.challenge_type_id.value;
    searchForm.elements.challenge_type_id.innerHTML =
      `<option value="">챌린지유형</option>${optionMarkup(lookups.types, selectedSearchType)}`;
    form.elements.challenge_type_id.innerHTML = optionMarkup(lookups.types);
    form.elements.challenge_period_id.innerHTML = optionMarkup(lookups.periods);
    form.elements.check_type_id.innerHTML = optionMarkup(lookups.checkTypes);
    form.elements.check_frequency_id.innerHTML = optionMarkup(lookups.frequencies);
    const selectedBadge = form.elements.reward_badge_id.value;
    form.elements.reward_badge_id.innerHTML = `<option value="">선택 안 함</option>${lookups.badges
      .map(
        (badge) =>
          `<option value="${badge.id}" ${String(badge.id) === String(selectedBadge) ? "selected" : ""}>${escapeHtml(badge.name)}</option>`,
      )
      .join("")}`;
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
            <td>${challengeActionMarkup(item.id, item.is_deletable)}</td>
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
    participantPage = 1;
    participantTotal.textContent = "0";
    participantRows.innerHTML = "";
    participantPagination.innerHTML = "";
    applyPrimaryAction(0);
    if (participantDialog.open) participantDialog.close();
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
      editingId = Number(id);
      const [item, participants] = await Promise.all([
        get(`/admin/challenges/${id}`),
        get(`/admin/challenges/${id}/participants`, {
          offset: 0,
          limit: PARTICIPANT_PAGE_SIZE,
        }),
      ]);
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
        form.elements.reward_badge_id.value = item.reward_badge_id;
      }
      form.elements.recruit_start_at.value = toLocalDateTime(item.recruit_start_at);
      form.elements.recruit_end_at.value = toLocalDateTime(item.recruit_end_at);
      form.elements.is_displayed.checked = item.is_displayed;
      renderParticipants(participants, 1);
      applyPrimaryAction(participants.total_count);
      title.textContent = "챌린지 수정";
      error.textContent = "";
      form.hidden = false;
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (caught) {
      window.alert(caught instanceof ApiError ? caught.message : "챌린지 정보를 불러오지 못했습니다.");
    }
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
    primaryAction.disabled = true;
    try {
      if (editingId) await patch(`/admin/challenges/${editingId}`, payload);
      else await post("/admin/challenges", payload);
      close();
      await load();
    } catch (caught) {
      error.textContent = caught instanceof ApiError ? caught.message : "저장에 실패했습니다.";
    } finally {
      primaryAction.disabled = false;
    }
  });

  primaryAction.addEventListener("click", () => {
    if (primaryAction.dataset.opensParticipants === "true") {
      participantDialog.showModal();
    }
  });

  participantPagination.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-challenge-participant-page]");
    if (!button || button.disabled) return;
    try {
      await loadParticipants(Number(button.dataset.challengeParticipantPage));
    } catch (caught) {
      tableState.error(
        participantRows,
        PARTICIPANT_COLUMN_COUNT,
        caught instanceof ApiError ? caught.message : "참여 내역 조회에 실패했습니다.",
      );
      participantPagination.innerHTML = "";
    }
  });

  participantRows.addEventListener("click", (event) => {
    if (event.target.closest("[data-retry]")) void loadParticipants(participantPage);
  });

  document.querySelectorAll("[data-close-challenge-participants]").forEach((button) => {
    button.addEventListener("click", () => participantDialog.close());
  });
  participantDialog.addEventListener("click", (event) => {
    if (event.target === participantDialog) participantDialog.close();
  });

  document.querySelector("[data-create-challenge]").addEventListener("click", openCreate);
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
