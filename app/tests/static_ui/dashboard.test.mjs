import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  accountTotal,
  alarmTrendLabel,
  buildAlarmTrendItems,
  buildReasonRing,
  buildTrendItems,
  changeBadge,
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

test("dashboard renders alarm delivery data before AI chatbot evaluations", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const notificationIndex = html.indexOf("알림 발송 현황");
  const chatbotIndex = html.indexOf("AI 챗봇 평가 현황");
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
  assert.doesNotMatch(firstColumn, /AI 챗봇 평가 현황/);
  assert.match(secondColumn, /AI 챗봇 평가 현황/);
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

test("reason ring converts counts into colored donut segments", () => {
  assert.deepEqual(
    buildReasonRing(
      [
        { code: "P01", name: "정확함", count: 2, percentage: 66.7 },
        { code: "P02", name: "도움이 됨", count: 1, percentage: 33.3 },
      ],
      ["#0f766e", "#5eead4"],
    ),
    {
      total: 3,
      background: "conic-gradient(#0f766e 0% 66.7%, #5eead4 66.7% 100%)",
      items: [
        { code: "P01", name: "정확함", count: 2, percentage: 66.7, color: "#0f766e" },
        { code: "P02", name: "도움이 됨", count: 1, percentage: 33.3, color: "#5eead4" },
      ],
    },
  );
});

test("reason ring returns an empty visualization without selected reasons", () => {
  assert.deepEqual(buildReasonRing([], ["#0f766e"]), {
    total: 0,
    background: "#e5e7eb",
    items: [],
  });
});

test("chatbot evaluation card exposes counts and two reason rings", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const chatbotIndex = html.indexOf("AI 챗봇 평가 현황");
  const chatbotCard = html.slice(chatbotIndex);

  assert.match(chatbotCard, /data-chat-liked/);
  assert.match(chatbotCard, /data-chat-disliked/);
  assert.match(chatbotCard, /data-chat-unrated/);
  assert.match(chatbotCard, /data-positive-reason-ring/);
  assert.match(chatbotCard, /data-positive-reason-legend/);
  assert.match(chatbotCard, /data-negative-reason-ring/);
  assert.match(chatbotCard, /data-negative-reason-legend/);
  assert.match(chatbotCard, /좋아요 사유/);
  assert.match(chatbotCard, /싫어요 사유/);
  assert.doesNotMatch(chatbotCard, /전체 응답|응답 성공|응답 실패|챗봇 만족도/);
});

test("dashboard loads two-column reason ring styles", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../static/css/dashboard.css", import.meta.url), "utf8");

  assert.match(html, /styles\.css\?v=20260831-9/);
  assert.match(html, /dashboard\.css\?v=20260910-1/);
  assert.match(styles, /\.chat-reason-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s);
  assert.match(styles, /\.chat-reason-ring\s*\{[^}]*border-radius:\s*50%;/s);
});

test("OCR accuracy and chatbot reason panels share the same minimum height", async () => {
  const styles = await readFile(new URL("../../static/css/dashboard.css", import.meta.url), "utf8");

  assert.match(styles, /--dashboard-insight-height:\s*136px;/);
  assert.match(
    styles,
    /\.dashboard-insight-card,\s*\.chat-reason-panel\s*\{[^}]*min-height:\s*var\(--dashboard-insight-height\);/s,
  );
});

test("OCR accuracy and chatbot reason rings share the same diameter", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../static/css/dashboard.css", import.meta.url), "utf8");

  assert.match(html, /class="[^"]*ocr-accuracy-ring[^"]*"/);
  assert.match(styles, /--dashboard-ring-size:\s*88px;/);
  assert.match(styles, /\.ocr-accuracy-ring\s*\{[^}]*width:\s*var\(--dashboard-ring-size\);[^}]*height:\s*var\(--dashboard-ring-size\);/s);
  assert.match(styles, /\.chat-reason-ring\s*\{[^}]*width:\s*var\(--dashboard-ring-size\);/s);
});

test("OCR accuracy value uses the same font size as its title", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");

  assert.match(html, /data-ocr-accuracy class="[^"]*text-\[12px\][^"]*"/);
  assert.match(html, /class="font-semibold text-\[12px\][^"]*"[^>]*>OCR 추출 정확도<\/p>/);
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

  assert.match(html, /style="color:#2563eb;">좋아요<\/p>/);
  assert.match(html, /style="color:#dc2626;">싫어요<\/p>/);
});
