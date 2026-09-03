/**
 * 운영 대시보드.
 *
 * 회원, 알림, OCR 및 AI 챗봇 현황을 GET /api/v1/admin/dashboard/summary 에 연결한다.
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

export function alarmTrendLabel() {
  return "최근 14일 성공 발송";
}

export function trendGridColumns(pointCount) {
  return `repeat(${Math.max(1, pointCount)}, minmax(0, 1fr))`;
}

export function formatOcrConfidence(value) {
  if (value === null || value === undefined) return "데이터 없음";
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return "데이터 없음";
  return `${(confidence * 100).toFixed(1)}%`;
}

export function formatChatSatisfaction(value) {
  const rate = Number(value);
  if (value === null || value === undefined || !Number.isFinite(rate) || rate < 0 || rate > 100) {
    return {
      text: "데이터 없음",
      fillPercent: 0,
      ariaLabel: "챗봇 만족도 평가 데이터 없음",
    };
  }

  const rounded = Math.round(rate * 10) / 10;
  return {
    text: `${rounded.toFixed(1)}%`,
    fillPercent: rounded,
    ariaLabel: `챗봇 긍정 평가 비율 ${rounded.toFixed(1)}%`,
  };
}

// 카드 안에서 이미 쓰고 있는 색이다. 새 색을 만들지 않는다.
const CHANGE_COLORS = { up: "#16a34a", down: "#dc2626", flat: "#6b7280" };
const STATUS_COLORS = { positive: "#2563eb", negative: "#dc2626" };

// 막대 높이. 컨테이너가 70px 이고 패딩이 8px 씩이라 목 데이터의 최대 막대와 같은 52px 로 맞춘다.
const TREND_MAX_HEIGHT = 52;
// 0 명인 날도 축이 보이게 남기는 최소 높이. 전부 0 이면 빈 상자로 보인다.
const TREND_MIN_HEIGHT = 2;

const PLACEHOLDER = "—";

/** 가입 추이 API 데이터를 날짜 축·막대·도움말에 공통으로 사용할 표시 데이터로 바꾼다. */
export function buildTrendItems(points, unit = "명") {
  const max = Math.max(...points.map((point) => Number(point.count) || 0), 0);

  return points.map((point) => {
    const count = Number(point.count) || 0;
    const fullDate = formatDate(point.date);
    const scaled = max > 0 ? Math.round((count / max) * TREND_MAX_HEIGHT) : 0;

    return {
      dateLabel: fullDate.slice(5),
      tooltip: `${fullDate} · ${count}${unit}`,
      height: Math.max(TREND_MIN_HEIGHT, scaled),
    };
  });
}

export function buildAlarmTrendItems(points) {
  return buildTrendItems(points, "건");
}

export function selectPeriod(periods, selected) {
  return periods.map((period) => (period === selected ? "active" : "inactive"));
}

/**
 * 증감률 배지 문구. 직전 기간이 0건이면 서버가 null 을 준다(계산 불가).
 * null 을 0% 로 그리면 "변화 없음"으로 읽혀 뜻이 달라진다.
 */
export function changeBadge(rate) {
  if (rate === null || rate === undefined) return { text: PLACEHOLDER, color: CHANGE_COLORS.flat };
  if (rate > 0) return { text: `▲ +${rate}%`, color: CHANGE_COLORS.up };
  if (rate < 0) return { text: `▼ ${rate}%`, color: CHANGE_COLORS.down };
  return { text: "0%", color: CHANGE_COLORS.flat };
}

/** 비율(%). 분모가 0이면 나눌 수 없다. */
export function shareOfTotal(value, total) {
  if (!total) return null;
  return Math.round((value / total) * 100);
}

/** 탈퇴율 분모. API가 제공하는 네 계정 상태를 모두 포함한다. */
export function accountTotal(members) {
  return [members.active, members.pending, members.suspended, members.withdrawn].reduce(
    (total, value) => total + (Number(value) || 0),
    0,
  );
}

function formatCount(value) {
  return Number(value ?? 0).toLocaleString("ko-KR");
}

function setBadge(element, { text, color }) {
  if (!element) return;
  element.textContent = text;
  element.style.color = color;
}

/** 14일 가입 추이. 날짜가 표시된 전체 열에서 도움말을 열 수 있게 동적으로 구성한다. */
function renderTrend(
  container,
  points,
  {
    itemBuilder = buildTrendItems,
    barClassName = "member-trend-bar",
    tooltipIdPrefix = "member-trend-tooltip",
  } = {},
) {
  container.replaceChildren();
  container.style.gridTemplateColumns = trendGridColumns(points.length);

  itemBuilder(points).forEach((item, index) => {
    const column = document.createElement("div");
    column.className = "member-trend-column";
    column.tabIndex = 0;
    column.setAttribute("aria-label", item.tooltip);

    const barArea = document.createElement("div");
    barArea.className = "member-trend-bar-area";

    const bar = document.createElement("div");
    bar.className = barClassName;
    bar.style.height = `${item.height}px`;
    barArea.append(bar);

    const date = document.createElement("span");
    date.className = "member-trend-date";
    date.textContent = item.dateLabel;

    const tooltip = document.createElement("span");
    tooltip.className = "member-trend-tooltip";
    tooltip.id = `${tooltipIdPrefix}-${index}`;
    tooltip.role = "tooltip";
    tooltip.textContent = item.tooltip;
    column.setAttribute("aria-describedby", tooltip.id);

    column.append(barArea, date, tooltip);
    container.append(column);
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
    withdrawn: document.querySelector("[data-member-withdrawn]"),
    withdrawnRatio: document.querySelector("[data-member-withdrawn-ratio]"),
    signupsLabel: document.querySelector("[data-member-signups-label]"),
    alarmQueued: document.querySelector("[data-alarm-queued]"),
    alarmCompleted: document.querySelector("[data-alarm-completed]"),
    alarmFailed: document.querySelector("[data-alarm-failed]"),
    alarmTrendLabel: document.querySelector("[data-alarm-trend-label]"),
    ocrTotal: document.querySelector("[data-ocr-total]"),
    ocrQueued: document.querySelector("[data-ocr-queued]"),
    ocrCompleted: document.querySelector("[data-ocr-completed]"),
    ocrFailed: document.querySelector("[data-ocr-failed]"),
    ocrAccuracy: document.querySelector("[data-ocr-accuracy]"),
    chatTotal: document.querySelector("[data-chat-total]"),
    chatCompleted: document.querySelector("[data-chat-completed]"),
    chatFailed: document.querySelector("[data-chat-failed]"),
    chatSatisfaction: document.querySelector("[data-chat-satisfaction]"),
    chatSatisfactionFill: document.querySelector("[data-chat-satisfaction-fill]"),
    chatSatisfactionValue: document.querySelector("[data-chat-satisfaction-value]"),
  };
  const trend = document.querySelector("[data-member-trend]");
  const alarmTrend = document.querySelector("[data-alarm-trend]");

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
    [
      slots.total,
      slots.signups,
      slots.active,
      slots.withdrawn,
      slots.alarmQueued,
      slots.alarmCompleted,
      slots.alarmFailed,
      slots.ocrTotal,
      slots.ocrQueued,
      slots.ocrCompleted,
      slots.ocrFailed,
      slots.chatTotal,
      slots.chatCompleted,
      slots.chatFailed,
    ].forEach((slot) => {
      if (slot) slot.textContent = PLACEHOLDER;
    });
    [slots.totalRate, slots.signupsRate, slots.activeRatio, slots.withdrawnRatio].forEach((slot) =>
      setBadge(slot, { text: PLACEHOLDER, color: CHANGE_COLORS.flat }),
    );
    // 숫자만 비우고 차트를 두면 목 데이터 막대가 실제 추이처럼 남는다.
    if (trend) renderTrend(trend, []);
    if (alarmTrend) renderTrend(alarmTrend, []);
    if (slots.ocrAccuracy) slots.ocrAccuracy.textContent = "데이터 없음";
    const satisfaction = formatChatSatisfaction(null);
    if (slots.chatSatisfaction) slots.chatSatisfaction.setAttribute("aria-label", satisfaction.ariaLabel);
    if (slots.chatSatisfactionFill) slots.chatSatisfactionFill.style.width = `${satisfaction.fillPercent}%`;
    if (slots.chatSatisfactionValue) slots.chatSatisfactionValue.textContent = satisfaction.text;
  };

  const render = (body) => {
    const members = body.members;

    if (slots.total) slots.total.textContent = formatCount(members.total);
    if (slots.signups) slots.signups.textContent = formatCount(members.newSignups);
    if (slots.active) slots.active.textContent = formatCount(members.active);
    if (slots.withdrawn) slots.withdrawn.textContent = formatCount(members.withdrawn);

    setBadge(slots.totalRate, changeBadge(members.totalChangeRate));
    setBadge(slots.signupsRate, changeBadge(members.newSignupsChangeRate));

    const activeShare = shareOfTotal(members.active, members.total);
    const withdrawnShare = shareOfTotal(members.withdrawn, accountTotal(members));
    setBadge(slots.activeRatio, {
      text: activeShare === null ? PLACEHOLDER : `${activeShare}%`,
      color: STATUS_COLORS.positive,
    });
    setBadge(slots.withdrawnRatio, {
      text: withdrawnShare === null ? PLACEHOLDER : `${withdrawnShare}%`,
      color: STATUS_COLORS.negative,
    });

    if (trend) renderTrend(trend, members.signupTrend);
    const notifications = body.alarmNotifications;
    if (slots.alarmQueued) slots.alarmQueued.textContent = formatCount(notifications.queued);
    if (slots.alarmCompleted) slots.alarmCompleted.textContent = formatCount(notifications.completed);
    if (slots.alarmFailed) slots.alarmFailed.textContent = formatCount(notifications.failed);
    if (alarmTrend) {
      renderTrend(alarmTrend, notifications.completedTrend, {
        itemBuilder: buildAlarmTrendItems,
        barClassName: "alarm-trend-bar",
        tooltipIdPrefix: "alarm-trend-tooltip",
      });
    }
    const ocrDocuments = body.ocrDocuments;
    if (slots.ocrTotal) slots.ocrTotal.textContent = formatCount(ocrDocuments.total);
    if (slots.ocrQueued) slots.ocrQueued.textContent = formatCount(ocrDocuments.queued);
    if (slots.ocrCompleted) slots.ocrCompleted.textContent = formatCount(ocrDocuments.completed);
    if (slots.ocrFailed) slots.ocrFailed.textContent = formatCount(ocrDocuments.failed);
    if (slots.ocrAccuracy) {
      slots.ocrAccuracy.textContent = formatOcrConfidence(ocrDocuments.avgFieldConfidence);
    }
    const chatResponses = body.chatResponses;
    if (slots.chatTotal) slots.chatTotal.textContent = formatCount(chatResponses.total);
    if (slots.chatCompleted) slots.chatCompleted.textContent = formatCount(chatResponses.completed);
    if (slots.chatFailed) slots.chatFailed.textContent = formatCount(chatResponses.failed);
    const satisfaction = formatChatSatisfaction(chatResponses.likeRate);
    if (slots.chatSatisfaction) slots.chatSatisfaction.setAttribute("aria-label", satisfaction.ariaLabel);
    if (slots.chatSatisfactionFill) slots.chatSatisfactionFill.style.width = `${satisfaction.fillPercent}%`;
    if (slots.chatSatisfactionValue) slots.chatSatisfactionValue.textContent = satisfaction.text;
    setState(members.total === 0 ? "집계된 회원이 없습니다" : "");
  };

  let loaded = false;

  const load = async () => {
    setState("불러오는 중…");
    // 라벨은 응답이 아니라 선택한 탭을 따른다. 실패해도 숫자와 라벨이 어긋나지 않는다.
    if (slots.signupsLabel) slots.signupsLabel.textContent = signupsLabel(selectedLabel);
    if (slots.alarmTrendLabel) slots.alarmTrendLabel.textContent = alarmTrendLabel();
    if (alarmTrend) alarmTrend.setAttribute("aria-label", `${alarmTrendLabel()} 추이`);
    // 첫 조회 전에는 화면에 목 숫자가 남아 있다. 실제 값처럼 읽히지 않게 비운다.
    if (!loaded) clearNumbers();

    try {
      const body = await get("/admin/dashboard/summary", { period: periodValue(selectedLabel) });
      render(body);
      loaded = true;
    } catch (error) {
      clearNumbers();
      const message = error instanceof ApiError ? error.message : "회원 현황을 불러오지 못했습니다.";
      setState(`${message} 잠시 후 다시 시도해 주세요.`);
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
      load();
    });
  });

  load();
}

if (typeof document !== "undefined") {
  initializeDashboard();
}
