/**
 * 운영 대시보드.
 *
 * 회원 현황 카드만 GET /api/v1/admin/dashboard/summary 에 연결한다.
 * OCR·챗봇·알림·시스템 카드는 백엔드에 지표가 없어 목 데이터를 그대로 둔다 —
 * 0 으로 채우면 화면이 정상값으로 그려 "기능이 죽었다"는 오해를 부른다.
 */

import { ApiError, formatDate, get, requireLogin } from "./api.js";

/** 화면 탭 표기 -> API enum. api.js 의 statusValue/roleValue 와 같은 방식이다. */
const PERIOD_VALUES = {
  오늘: "TODAY",
  "7일": "LAST_7_DAYS",
  "30일": "LAST_30_DAYS",
};

/** 모르는 표기면 빈 값을 준다. buildQuery 가 빼고 서버 기본값(TODAY)이 쓰인다. */
export function periodValue(label) {
  return PERIOD_VALUES[label] ?? "";
}

/**
 * 신규 가입 칸의 라벨. 값이 선택한 기간의 가입 수라서 라벨도 같이 움직여야 한다.
 * "오늘 가입" 으로 고정하면 30일 탭에서 30일치 숫자를 오늘 가입으로 읽게 된다.
 */
export function signupsLabel(periodLabel) {
  return PERIOD_VALUES[periodLabel] ? `${periodLabel} 가입` : "신규 가입";
}

// 카드 안에서 이미 쓰고 있는 색이다. 새 색을 만들지 않는다.
const CHANGE_COLORS = { up: "#16a34a", down: "#dc2626", flat: "#6b7280" };

/**
 * 정지 비율 경보 단계별 색.
 *
 * 단계는 서버가 판정한 status 를 그대로 쓴다. 임계치를 프론트에서 다시 계산하면
 * config 값을 바꿨을 때 화면과 서버 판단이 어긋난다.
 */
const ALERT_COLORS = { NORMAL: "#6b7280", WARNING: "#d97706", DANGER: "#dc2626" };

// 막대 높이. 컨테이너가 70px 이고 패딩이 8px 씩이라 목 데이터의 최대 막대와 같은 52px 로 맞춘다.
const TREND_MAX_HEIGHT = 52;
// 0 명인 날도 축이 보이게 남기는 최소 높이. 전부 0 이면 빈 상자로 보인다.
const TREND_MIN_HEIGHT = 2;

const PLACEHOLDER = "—";

export function selectPeriod(periods, selected) {
  return periods.map((period) => (period === selected ? "active" : "inactive"));
}

export function formatRefreshTime(date) {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `최종 점검: ${hours}:${minutes}`;
}

/**
 * 증감률 배지 문구. 직전 기간이 0건이면 서버가 null 을 준다(계산 불가).
 * null 을 0% 로 그리면 "변화 없음"으로 읽혀 뜻이 달라진다.
 */
export function changeBadge(rate) {
  if (rate === null || rate === undefined) return { text: PLACEHOLDER, color: CHANGE_COLORS.flat };
  if (rate > 0) return { text: `▲ +${rate}%`, color: CHANGE_COLORS.up };
  if (rate < 0) return { text: `▼ ${rate}%`, color: CHANGE_COLORS.down };
  return { text: "— 0%", color: CHANGE_COLORS.flat };
}

/**
 * 활성·정지 비율(%). total = active + suspended 라서 두 값의 합이 100 이 된다.
 * 회원이 0명이면 나눌 수 없다.
 */
export function shareOfTotal(value, total) {
  if (!total) return null;
  return Math.round((value / total) * 100);
}

function formatCount(value) {
  return Number(value ?? 0).toLocaleString("ko-KR");
}

function setBadge(element, { text, color }) {
  if (!element) return;
  element.textContent = text;
  element.style.color = color;
}

/**
 * 14일 가입 추이. 막대는 HTML 에 이미 14개 있고 높이만 바꾼다.
 * 요소를 새로 만들면 승인받은 태그 구조를 건드리게 된다.
 */
function renderTrend(container, points) {
  const bars = [...container.children];
  if (!bars.length) return;

  const max = Math.max(...points.map((point) => point.count), 0);

  bars.forEach((bar, index) => {
    const point = points[index];
    if (!point) {
      bar.style.height = `${TREND_MIN_HEIGHT}px`;
      bar.removeAttribute("title");
      return;
    }
    const scaled = max > 0 ? Math.round((point.count / max) * TREND_MAX_HEIGHT) : 0;
    bar.style.height = `${Math.max(TREND_MIN_HEIGHT, scaled)}px`;
    bar.title = `${formatDate(point.date)} · ${point.count}명`;
  });
}

function initializeDashboard() {
  const state = document.querySelector("[data-member-state]");
  if (!state) return;
  if (!requireLogin()) return;

  const slots = {
    total: document.querySelector("[data-member-total]"),
    totalRate: document.querySelector("[data-member-total-rate]"),
    signups: document.querySelector("[data-member-signups]"),
    signupsRate: document.querySelector("[data-member-signups-rate]"),
    active: document.querySelector("[data-member-active]"),
    activeRatio: document.querySelector("[data-member-active-ratio]"),
    suspended: document.querySelector("[data-member-suspended]"),
    suspendedRatio: document.querySelector("[data-member-suspended-ratio]"),
    signupsLabel: document.querySelector("[data-member-signups-label]"),
  };
  const trend = document.querySelector("[data-member-trend]");
  const refreshTime = document.querySelector("[data-refresh-time]");

  const periodButtons = [...document.querySelectorAll("[data-period]")];
  const periodLabels = periodButtons.map((button) => button.dataset.period);
  // 처음 선택된 탭은 HTML 의 is-active 가 정한다(지금은 7일). JS 가 다시 정하면 둘이 어긋난다.
  let selectedLabel =
    periodButtons.find((button) => button.classList.contains("is-active"))?.dataset.period ?? periodLabels[0];

  // 카드 제목에 상태를 덧붙인다. 상태 표시용 요소를 새로 넣을 수 없어 제목을 쓴다.
  const baseTitle = state.textContent;
  const setState = (message) => {
    state.textContent = message ? `${baseTitle} · ${message}` : baseTitle;
  };

  const clearNumbers = () => {
    [slots.total, slots.signups, slots.active, slots.suspended].forEach((slot) => {
      if (slot) slot.textContent = PLACEHOLDER;
    });
    [slots.totalRate, slots.signupsRate, slots.activeRatio, slots.suspendedRatio].forEach((slot) =>
      setBadge(slot, { text: PLACEHOLDER, color: CHANGE_COLORS.flat }),
    );
    // 숫자만 비우고 차트를 두면 목 데이터 막대가 실제 추이처럼 남는다.
    if (trend) renderTrend(trend, []);
  };

  const render = (body) => {
    const members = body.members;

    if (slots.total) slots.total.textContent = formatCount(members.total);
    if (slots.signups) slots.signups.textContent = formatCount(members.newSignups);
    if (slots.active) slots.active.textContent = formatCount(members.active);
    if (slots.suspended) slots.suspended.textContent = formatCount(members.suspended);

    setBadge(slots.totalRate, changeBadge(members.totalChangeRate));
    setBadge(slots.signupsRate, changeBadge(members.newSignupsChangeRate));

    const activeShare = shareOfTotal(members.active, members.total);
    const suspendedShare = shareOfTotal(members.suspended, members.total);
    setBadge(slots.activeRatio, {
      text: activeShare === null ? PLACEHOLDER : `— ${activeShare}%`,
      color: CHANGE_COLORS.flat,
    });
    setBadge(slots.suspendedRatio, {
      text: suspendedShare === null ? PLACEHOLDER : `— ${suspendedShare}%`,
      color: ALERT_COLORS[members.status] ?? CHANGE_COLORS.flat,
    });

    if (trend) renderTrend(trend, members.signupTrend);
    // 시각은 서버가 집계한 시점(generatedAt)이다. 브라우저 시계를 쓰면 실제 집계 시점과 벌어진다.
    if (refreshTime) refreshTime.textContent = formatRefreshTime(new Date(body.generatedAt));

    setState(members.total === 0 ? "집계된 회원이 없습니다" : "");
  };

  let loaded = false;

  const load = async () => {
    setState("불러오는 중…");
    // 라벨은 응답이 아니라 선택한 탭을 따른다. 실패해도 숫자와 라벨이 어긋나지 않는다.
    if (slots.signupsLabel) slots.signupsLabel.textContent = signupsLabel(selectedLabel);
    // 첫 조회 전에는 화면에 목 숫자가 남아 있다. 실제 값처럼 읽히지 않게 비운다.
    if (!loaded) clearNumbers();

    try {
      const body = await get("/admin/dashboard/summary", { period: periodValue(selectedLabel) });
      render(body);
      loaded = true;
    } catch (error) {
      clearNumbers();
      const message = error instanceof ApiError ? error.message : "회원 현황을 불러오지 못했습니다.";
      setState(`${message} 새로고침을 눌러 주세요.`);
    }
  };

  periodButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const states = selectPeriod(periodLabels, button.dataset.period);

      periodButtons.forEach((periodButton, index) => {
        const isActive = states[index] === "active";
        periodButton.classList.toggle("is-active", isActive);
        periodButton.setAttribute("aria-pressed", String(isActive));
      });

      selectedLabel = button.dataset.period;
      // period 는 신규 가입과 증감률에만 걸린다. 전체·활성·정지가 그대로인 것은 정상이다.
      load();
    });
  });

  document.querySelector("[data-refresh]")?.addEventListener("click", load);

  load();
}

if (typeof document !== "undefined") {
  initializeDashboard();
}
