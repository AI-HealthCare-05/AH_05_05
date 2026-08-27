import { ApiError, escapeHtml, get, post, request, requireLogin, session, tableState } from "./api.js";

const COLUMN_COUNT = 3;
const DISPLAY_COLUMN_COUNT = 6;

export function renderSupplementRanking(tbody, supplements) {
  if (!supplements.length) {
    tableState.empty(tbody, COLUMN_COUNT, "복용 중인 영양제 데이터가 없습니다.");
    return;
  }

  tbody.innerHTML = supplements
    .map(
      (supplement, index) => `<tr>
        <td>${index + 1}</td>
        <td>${escapeHtml(supplement.id)}</td>
        <td><strong>${escapeHtml(supplement.name)}</strong></td>
      </tr>`,
    )
    .join("");
}

export function toDefaultRankItems(supplements) {
  return supplements.slice(0, 5).map(({ id, name }) => ({ id, name }));
}

export function validateRankDisplayInput({ title, startAt, endAt, items }) {
  if (!title?.trim()) return "전시 제목을 입력해 주세요.";
  if (!startAt || !endAt) return "전시 시작 일시와 종료 일시를 입력해 주세요.";
  if (new Date(endAt) < new Date(startAt)) return "전시 종료 일시는 시작 일시 이후여야 합니다.";
  if (!items?.length) return "전시할 영양제를 한 개 이상 선택해 주세요.";
  if (items.length > 5) return "전시 영양제는 최대 5개까지 선택할 수 있습니다.";
  if (new Set(items.map((item) => item.id)).size !== items.length) {
    return "같은 영양제를 중복 등록할 수 없습니다.";
  }
  return "";
}

export function buildRankDisplayPayload({ title, startAt, endAt, isEnabled, items }) {
  return {
    title: title.trim(),
    startAt,
    endAt,
    isEnabled: Boolean(isEnabled),
    items: items.map((item, index) => ({ supplementNutrientId: item.id, rankNo: index + 1 })),
  };
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function renderRankDisplayRows(tbody, displays, canWrite) {
  if (!displays.length) {
    tableState.empty(tbody, DISPLAY_COLUMN_COUNT, "등록된 영양제 랭킹 전시가 없습니다.");
    return;
  }
  tbody.innerHTML = displays
    .map(
      (display) => `<tr>
        <td>${escapeHtml(display.display_id)}</td>
        <td><strong>${escapeHtml(display.title)}</strong></td>
        <td>${escapeHtml(formatDateTime(display.start_at))} ~ ${escapeHtml(formatDateTime(display.end_at))}</td>
        <td>${escapeHtml(display.item_count)}개</td>
        <td><span class="status-badge ${display.is_enabled ? "status-active" : "status-stopped"}">${display.is_enabled ? "활성" : "비활성"}</span></td>
        <td>${
          canWrite
            ? `<button type="button" class="ui-link-button" data-edit-display="${display.display_id}">수정</button>
               <button type="button" class="ui-link-button ui-link-button-danger" data-delete-display="${display.display_id}">삭제</button>`
            : "-"
        }</td>
      </tr>`,
    )
    .join("");
}

function toDateTimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function initializeSupplementRanking() {
  const tbody = document.querySelector("[data-supplement-ranking-rows]");
  const displayTbody = document.querySelector("[data-rank-display-rows]");
  const form = document.querySelector("[data-display-form]");
  if (!tbody || !displayTbody || !form || !requireLogin()) return;

  const canWrite = session.isAdminRole();
  const createButton = document.querySelector("[data-create-display]");
  const keyword = document.querySelector("[data-product-keyword]");
  const results = document.querySelector("[data-product-results]");
  const selectedList = document.querySelector("[data-selected-products]");
  const formError = document.querySelector("[data-form-error]");
  let selectedItems = [];
  let editingId = null;
  let popularLoadPromise = null;
  let formGeneration = 0;

  if (!canWrite) createButton.hidden = true;

  const load = async () => {
    tableState.loading(tbody, COLUMN_COUNT, "영양제 랭킹을 불러오는 중…");
    try {
      const supplements = await get("/admin/supplement-nutrients/popular");
      renderSupplementRanking(tbody, supplements);
      return toDefaultRankItems(supplements);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "영양제 랭킹을 불러오지 못했습니다.";
      tableState.error(tbody, COLUMN_COUNT, message);
      return [];
    }
  };

  const reloadPopularSupplements = () => {
    popularLoadPromise = load();
    return popularLoadPromise;
  };

  const loadDisplays = async () => {
    tableState.loading(displayTbody, DISPLAY_COLUMN_COUNT, "전시 목록을 불러오는 중…");
    try {
      const response = await get("/admin/supplement-rank-displays", { page: 1, size: 100 });
      renderRankDisplayRows(displayTbody, response.items, canWrite);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "전시 목록을 불러오지 못했습니다.";
      tableState.error(displayTbody, DISPLAY_COLUMN_COUNT, message);
    }
  };

  const renderSelectedItems = () => {
    selectedList.innerHTML = selectedItems.length
      ? selectedItems
          .map(
            (item, index) => `<li>
              <span><strong>${index + 1}위</strong> ${escapeHtml(item.name)} <small>ID ${item.id}</small></span>
              <span>
                <button type="button" class="ui-link-button" data-move-product="${index}" data-direction="up" ${index === 0 ? "disabled" : ""}>위</button>
                <button type="button" class="ui-link-button" data-move-product="${index}" data-direction="down" ${index === selectedItems.length - 1 ? "disabled" : ""}>아래</button>
                <button type="button" class="ui-link-button ui-link-button-danger" data-remove-product="${index}">제거</button>
              </span>
            </li>`,
          )
          .join("")
      : '<li class="rank-selected-empty">선택된 영양제가 없습니다.</li>';
  };

  const closeForm = () => {
    formGeneration += 1;
    form.hidden = true;
    form.reset();
    selectedItems = [];
    editingId = null;
    formError.textContent = "";
    results.innerHTML = "";
    renderSelectedItems();
  };

  const openCreate = async () => {
    closeForm();
    const generation = formGeneration;
    document.querySelector("[data-form-title]").textContent = "전시 등록";
    form.hidden = false;
    const defaultItems = await (popularLoadPromise ?? reloadPopularSupplements());
    if (generation !== formGeneration || form.hidden || editingId !== null) return;
    selectedItems = defaultItems.map((item) => ({ ...item }));
    renderSelectedItems();
  };

  const openEdit = async (displayId) => {
    const generation = ++formGeneration;
    try {
      const display = await get(`/admin/supplement-rank-displays/${displayId}`);
      if (generation !== formGeneration) return;
      editingId = display.display_id;
      form.elements.title.value = display.title;
      form.elements.startAt.value = toDateTimeLocal(display.start_at);
      form.elements.endAt.value = toDateTimeLocal(display.end_at);
      form.elements.isEnabled.checked = display.is_enabled;
      selectedItems = display.items.map((item) => ({ id: item.supplement_nutrient_id, name: item.name }));
      document.querySelector("[data-form-title]").textContent = "전시 수정";
      formError.textContent = "";
      results.innerHTML = "";
      renderSelectedItems();
      form.hidden = false;
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      window.alert(error instanceof ApiError ? error.message : "전시 정보를 불러오지 못했습니다.");
    }
  };

  const searchProducts = async () => {
    const name = keyword.value.trim();
    if (!name) {
      results.textContent = "검색할 영양제명을 입력해 주세요.";
      return;
    }
    results.textContent = "검색 중…";
    try {
      const response = await get("/admin/supplement-nutrients", { name, offset: 0, limit: 20 });
      results.innerHTML = response.items.length
        ? response.items
            .map(
              (item) => `<button type="button" class="rank-product-result" data-add-product="${item.id}" data-product-name="${escapeHtml(item.name)}">${escapeHtml(item.name)} <small>ID ${item.id}</small></button>`,
            )
            .join("")
        : "검색 결과가 없습니다.";
    } catch (error) {
      results.textContent = error instanceof ApiError ? error.message : "영양제 검색에 실패했습니다.";
    }
  };

  tbody.addEventListener("click", (event) => {
    if (event.target.closest("[data-retry]")) void reloadPopularSupplements();
  });

  displayTbody.addEventListener("click", (event) => {
    if (event.target.closest("[data-retry]")) return void loadDisplays();
    const edit = event.target.closest("[data-edit-display]");
    if (edit) return void openEdit(edit.dataset.editDisplay);
    const remove = event.target.closest("[data-delete-display]");
    if (remove && window.confirm("이 영양제 랭킹 전시를 삭제하시겠습니까?")) {
      void request(`/admin/supplement-rank-displays/${remove.dataset.deleteDisplay}`, { method: "DELETE" })
        .then(loadDisplays)
        .catch((error) => window.alert(error instanceof ApiError ? error.message : "전시 삭제에 실패했습니다."));
    }
  });

  createButton.addEventListener("click", () => void openCreate());
  document.querySelectorAll("[data-cancel-display]").forEach((button) => button.addEventListener("click", closeForm));
  document.querySelector("[data-search-product]").addEventListener("click", () => void searchProducts());
  keyword.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void searchProducts();
    }
  });
  results.addEventListener("click", (event) => {
    const button = event.target.closest("[data-add-product]");
    if (!button) return;
    const id = Number(button.dataset.addProduct);
    if (selectedItems.some((item) => item.id === id)) return void (formError.textContent = "이미 선택한 영양제입니다.");
    if (selectedItems.length >= 5) return void (formError.textContent = "영양제는 최대 5개까지 선택할 수 있습니다.");
    selectedItems.push({ id, name: button.dataset.productName });
    formError.textContent = "";
    renderSelectedItems();
  });
  selectedList.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-product]");
    if (remove) selectedItems.splice(Number(remove.dataset.removeProduct), 1);
    const move = event.target.closest("[data-move-product]");
    if (move) {
      const from = Number(move.dataset.moveProduct);
      const to = move.dataset.direction === "up" ? from - 1 : from + 1;
      [selectedItems[from], selectedItems[to]] = [selectedItems[to], selectedItems[from]];
    }
    renderSelectedItems();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = {
      title: form.elements.title.value,
      startAt: form.elements.startAt.value,
      endAt: form.elements.endAt.value,
      isEnabled: form.elements.isEnabled.checked,
      items: selectedItems,
    };
    const message = validateRankDisplayInput(input);
    if (message) return void (formError.textContent = message);
    try {
      const payload = buildRankDisplayPayload(input);
      if (editingId) {
        await request(`/admin/supplement-rank-displays/${editingId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await post("/admin/supplement-rank-displays", payload);
      }
      closeForm();
      await loadDisplays();
    } catch (error) {
      formError.textContent = error instanceof ApiError ? error.message : "전시 저장에 실패했습니다.";
    }
  });

  renderSelectedItems();
  void reloadPopularSupplements();
  void loadDisplays();
}

if (typeof document !== "undefined") initializeSupplementRanking();
