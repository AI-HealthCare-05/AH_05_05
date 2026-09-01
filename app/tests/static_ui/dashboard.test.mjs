import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  accountTotal,
  buildAlarmTrendItems,
  buildTrendItems,
  changeBadge,
  periodValue,
  selectPeriod,
  shareOfTotal,
  signupsLabel,
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
  assert.match(ocrCard, /OCR 추출 정확도/);
  assert.doesNotMatch(ocrCard, /[▲▼—]/);
});

test("OCR accuracy uses the shared RxVita accent tokens", async () => {
  const html = await readFile(new URL("../../static/templates/dashboard.html", import.meta.url), "utf8");
  const accuracyIndex = html.indexOf("OCR 추출 정확도");
  const accuracyCard = html.slice(Math.max(0, accuracyIndex - 900), accuracyIndex + 200);

  assert.match(accuracyCard, /border:6px solid var\(--brand-primary\)/);
  assert.match(accuracyCard, /color:var\(--brand-primary-strong\)/);
  assert.doesNotMatch(accuracyCard, /#1c64f2/);
});
