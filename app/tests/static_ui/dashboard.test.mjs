import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  accountTotal,
  alarmTrendLabel,
  buildAlarmTrendItems,
  buildTrendItems,
  changeBadge,
  formatChatSatisfaction,
  periodValue,
  selectPeriod,
  shareOfTotal,
  signupsLabel,
  trendGridColumns,
} from "../../static/js/dashboard.js";

test("selectPeriod marks only the selected period active", () => {
  assert.deepEqual(selectPeriod(["오늘", "7일", "30일"], "30일"), ["inactive", "inactive", "active"]);
});

test("selectPeriod leaves every period inactive for an unknown selection", () => {
  assert.deepEqual(selectPeriod(["오늘", "7일", "30일"], "90일"), ["inactive", "inactive", "inactive"]);
});

test("periodValue maps the tab label to the API enum", () => {
  assert.equal(periodValue("오늘"), "TODAY");
  assert.equal(periodValue("7일"), "LAST_7_DAYS");
  assert.equal(periodValue("30일"), "LAST_30_DAYS");
});

test("periodValue returns an empty value for an unknown label", () => {
  assert.equal(periodValue("90일"), "");
});

test("signupsLabel follows the selected period", () => {
  assert.equal(signupsLabel("오늘"), "오늘 가입");
  assert.equal(signupsLabel("7일"), "7일 가입");
  assert.equal(signupsLabel("30일"), "30일 가입");
});

test("signupsLabel falls back to a period-free label", () => {
  assert.equal(signupsLabel("90일"), "신규 가입");
});

test("alarmTrendLabel stays fixed at fourteen days", () => {
  assert.equal(alarmTrendLabel(), "최근 14일 성공 발송");
});

test("trendGridColumns keeps every period day on one chart row", () => {
  assert.equal(trendGridColumns(1), "repeat(1, minmax(0, 1fr))");
  assert.equal(trendGridColumns(7), "repeat(7, minmax(0, 1fr))");
  assert.equal(trendGridColumns(30), "repeat(30, minmax(0, 1fr))");
  assert.equal(trendGridColumns(0), "repeat(1, minmax(0, 1fr))");
});

test("changeBadge omits the neutral dash when the rate has not changed", () => {
  assert.deepEqual(changeBadge(0), { text: "0%", color: "#6b7280" });
});

test("withdrawn ratio uses every account status as its denominator", () => {
  const members = { active: 6, pending: 1, suspended: 2, withdrawn: 1 };

  assert.equal(accountTotal(members), 10);
  assert.equal(shareOfTotal(members.withdrawn, accountTotal(members)), 10);
});

test("buildTrendItems exposes dates and hover details for the entire trend column", () => {
  assert.deepEqual(
    buildTrendItems([
      { date: "2026-08-17", count: 0 },
      { date: "2026-08-18", count: 4 },
    ]),
    [
      { dateLabel: "08.17", tooltip: "2026.08.17 · 0명", height: 2 },
      { dateLabel: "08.18", tooltip: "2026.08.18 · 4명", height: 52 },
    ],
  );
});

test("buildAlarmTrendItems formats successful deliveries as dated counts", () => {
  assert.deepEqual(buildAlarmTrendItems([{ date: "2026-08-31", count: 3 }]), [
    { dateLabel: "08.31", tooltip: "2026.08.31 · 3건", height: 52 },
  ]);
});

test("dashboard renders alarm delivery data before AI chatbot status", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const notificationIndex = html.indexOf("알림 발송 현황");
  const chatbotIndex = html.indexOf("AI 챗봇 응답 현황");
  const notificationCard = html.slice(notificationIndex, chatbotIndex);

  assert.ok(notificationIndex >= 0);
  assert.equal(html.includes("알림 발송 허브"), false);
  assert.ok(notificationIndex < chatbotIndex);
  assert.match(notificationCard, /data-alarm-queued/);
  assert.match(notificationCard, /data-alarm-completed/);
  assert.match(notificationCard, /data-alarm-failed/);
  assert.match(notificationCard, /class="member-trend alarm-trend w-full"/);
  assert.doesNotMatch(notificationCard, /—/);
});

test("dashboard removes system status and swaps OCR with AI chatbot cards", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const firstColumn = html.slice(html.indexOf("<!-- col 1 -->"), html.indexOf("<!-- col 2 -->"));
  const secondColumn = html.slice(html.indexOf("<!-- col 2 -->"));

  assert.equal(html.includes("시스템 코어 및 마이크로서비스"), false);
  assert.match(firstColumn, /OCR 문서 처리/);
  assert.doesNotMatch(firstColumn, /AI 챗봇 응답 현황/);
  assert.match(secondColumn, /AI 챗봇 응답 현황/);
  assert.doesNotMatch(secondColumn, /OCR 문서 처리/);
});

test("OCR document card exposes API count slots without change badges", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const ocrIndex = html.indexOf("OCR 문서 처리");
  const ocrCard = html.slice(ocrIndex, html.indexOf("<!-- col 2 -->"));

  assert.match(ocrCard, /data-ocr-total/);
  assert.match(ocrCard, /data-ocr-queued/);
  assert.match(ocrCard, /data-ocr-completed/);
  assert.match(ocrCard, /data-ocr-failed/);
  assert.match(ocrCard, /data-ocr-accuracy/);
  assert.match(ocrCard, /OCR 추출 정확도/);
  assert.match(ocrCard, /약 제품명 confidence 평균을 나타냅니다\./);
  assert.doesNotMatch(ocrCard, /[▲▼—]/);
});

test("OCR field confidence is formatted as one decimal percent or no-data text", async () => {
  const dashboard = await import("../../static/js/dashboard.js");

  assert.equal(typeof dashboard.formatOcrConfidence, "function");
  assert.equal(dashboard.formatOcrConfidence(0.9846), "98.5%");
  assert.equal(dashboard.formatOcrConfidence(null), "데이터 없음");
});

test("chat satisfaction formats a fractional five-star average", () => {
  assert.deepEqual(formatChatSatisfaction(4.3), {
    text: "4.3 / 5.0",
    fillPercent: 86,
    ariaLabel: "챗봇 만족도 5점 만점에 4.3점",
  });
});

test("chat satisfaction leaves stars empty when no rating exists", () => {
  assert.deepEqual(formatChatSatisfaction(null), {
    text: "데이터 없음",
    fillPercent: 0,
    ariaLabel: "챗봇 만족도 평가 데이터 없음",
  });
});

test("chatbot card exposes API slots and an accessible five-star visualization", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const chatbotIndex = html.indexOf("AI 챗봇 응답 현황");
  const chatbotCard = html.slice(chatbotIndex);

  assert.match(chatbotCard, /data-chat-total/);
  assert.match(chatbotCard, /data-chat-completed/);
  assert.match(chatbotCard, /data-chat-failed/);
  assert.match(chatbotCard, /data-chat-satisfaction[^>]+role="img"/);
  assert.match(chatbotCard, /data-chat-satisfaction-fill/);
  assert.match(chatbotCard, /data-chat-satisfaction-value/);
  assert.match(chatbotCard, /챗봇 만족도/);
  assert.match(chatbotCard, /챗봇 사용자의 별점 평균을 나타냅니다\./);
  assert.doesNotMatch(chatbotCard, /자동 해결률|4,821|4,210|611/);
});

test("dashboard loads fractional star styles without changing the shared stylesheet version", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../static/css/dashboard.css", import.meta.url), "utf8");

  assert.match(html, /styles\.css\?v=20260831-9/);
  assert.match(html, /dashboard\.css\?v=20260902-1/);
  assert.match(styles, /\.chat-satisfaction-stars-fill\s*\{[^}]*overflow:\s*hidden;/s);
});

test("OCR accuracy and chatbot satisfaction use the same insight area height", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../static/css/dashboard.css", import.meta.url), "utf8");
  const ocrArea = html.slice(html.indexOf("data-ocr-accuracy") - 500, html.indexOf("data-ocr-accuracy"));
  const chatArea = html.slice(html.indexOf("data-chat-satisfaction") - 500, html.indexOf("data-chat-satisfaction"));

  assert.match(ocrArea, /dashboard-insight-card/);
  assert.match(chatArea, /dashboard-insight-card/);
  assert.match(styles, /\.dashboard-insight-card\s*\{[^}]*min-height:\s*80px;/s);
});

test("OCR accuracy uses the shared RxVita accent tokens", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const accuracyIndex = html.indexOf("OCR 추출 정확도");
  const accuracyCard = html.slice(Math.max(0, accuracyIndex - 900), accuracyIndex + 200);

  assert.match(accuracyCard, /border:6px solid var\(--brand-primary\)/);
  assert.match(accuracyCard, /color:var\(--brand-primary-strong\)/);
  assert.doesNotMatch(accuracyCard, /#1c64f2/);
});

test("dashboard uses blue for successful states and red for negative states", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");

  assert.match(html, /style="color:#2563eb;">활성<\/p>/);
  assert.match(html, /data-member-active[^>]+style="color:#2563eb;"/);
  assert.match(html, /style="color:#dc2626;">탈퇴<\/p>/);
  assert.match(html, /data-member-withdrawn[^>]+style="color:#dc2626;"/);

  for (const slot of ["ocr-completed", "alarm-completed"]) {
    assert.match(html, new RegExp(`data-${slot}[^>]+style="color:#2563eb;"`));
  }
  for (const slot of ["ocr-failed", "alarm-failed"]) {
    assert.match(html, new RegExp(`data-${slot}[^>]+style="color:#dc2626;"`));
  }

  assert.match(html, /style="color:#2563eb;">응답 성공<\/p>/);
  assert.match(html, /style="color:#dc2626;">응답 실패<\/p>/);
});
