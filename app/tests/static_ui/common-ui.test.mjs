import test from "node:test";
import assert from "node:assert/strict";

import {
  buildQuery,
  escapeHtml,
  formatDate,
  roleLabel,
  roleValue,
  statusBadgeClass,
  statusLabel,
  statusValue,
} from "../../static/js/api.js";
import { getNavigationTarget } from "../../static/js/navigation.js";
import { serializeCsv } from "../../static/js/overlay.js";

test("getNavigationTarget maps each sidebar section to its page", () => {
  assert.equal(getNavigationTarget("dashboard"), "dashboard.html");
  assert.equal(getNavigationTarget("users"), "user-management.html");
  assert.equal(getNavigationTarget("admins"), "screen-4-admin-management.html");
  assert.equal(getNavigationTarget("tasks"), "screen-5-task-management.html");
  assert.equal(getNavigationTarget("common-codes"), "common-code-management.html");
  assert.equal(getNavigationTarget("supplement-ranking"), "supplement-ranking.html");
  assert.equal(getNavigationTarget("logout"), "login.html");
});

test("getNavigationTarget returns the dashboard for an unknown section", () => {
  assert.equal(getNavigationTarget("unknown"), "dashboard.html");
});

test("statusBadgeClass separates active, suspended and pending", () => {
  assert.equal(statusBadgeClass("ACTIVE"), "active");
  assert.equal(statusBadgeClass("SUSPENDED"), "stopped");
  assert.equal(statusBadgeClass("PENDING"), "processing");
});

test("statusBadgeClass keeps suspended grey, not the danger colour", () => {
  // 정지는 오류가 아니라 관리자가 의도한 상태다. 빨강은 파괴적 동작 버튼이 쓴다.
  assert.notEqual(statusBadgeClass("SUSPENDED"), "failed");
});

test("statusBadgeClass falls back to grey for statuses the screens do not handle", () => {
  assert.equal(statusBadgeClass("WITHDRAWN"), "stopped");
  assert.equal(statusBadgeClass(undefined), "stopped");
});

test("serializeCsv quotes commas and double quotes", () => {
  assert.equal(
    serializeCsv([[
      "이름",
      "메모",
    ], [
      "Dr. Sarah Connor",
      "서울, 강남 \"센터\"",
    ]]),
    '\uFEFF이름,메모\r\nDr. Sarah Connor,"서울, 강남 ""센터"""',
  );
});

/* ---------------------------------------------------------------- escapeHtml
 *
 * 사용자 입력이 관리자 화면의 innerHTML 로 들어가는 유일한 통로다.
 * 회원 관리·관리자 관리·공통코드·영양제 순위·작업 관리 다섯 화면이 여기에 의존한다.
 */

test("escapeHtml neutralises every character that can break out of markup", () => {
  assert.equal(escapeHtml("&"), "&amp;");
  assert.equal(escapeHtml("<"), "&lt;");
  assert.equal(escapeHtml(">"), "&gt;");
  assert.equal(escapeHtml('"'), "&quot;");
  assert.equal(escapeHtml("'"), "&#39;");
});

test("escapeHtml defuses an injected script tag", () => {
  assert.equal(
    escapeHtml("<script>alert(1)</script>"),
    "&lt;script&gt;alert(1)&lt;/script&gt;",
  );
  assert.doesNotMatch(escapeHtml("<script>alert(1)</script>"), /<script>/);
});

test("escapeHtml defuses an attribute break-out", () => {
  assert.equal(
    escapeHtml('" onerror="alert(1)'),
    "&quot; onerror=&quot;alert(1)",
  );
});

test("escapeHtml replaces the ampersand first so entities are not double-escaped away", () => {
  // & 를 나중에 바꾸면 자기가 만든 &lt; 의 & 까지 다시 바꿔 &amp;lt; 가 된다.
  // 반대로 사용자가 정말 "&lt;" 라고 적었다면 그 텍스트는 &amp;lt; 로 남아야 맞다.
  assert.equal(escapeHtml("&lt;"), "&amp;lt;");
  assert.equal(escapeHtml("a & b < c"), "a &amp; b &lt; c");
});

test("escapeHtml turns nullish input into an empty string", () => {
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(""), "");
});

test("escapeHtml stringifies non-string input instead of dropping it", () => {
  // 0 과 false 는 nullish 가 아니라 그대로 문자열이 된다.
  assert.equal(escapeHtml(0), "0");
  assert.equal(escapeHtml(false), "false");
  assert.equal(escapeHtml(42), "42");
});

test("escapeHtml leaves ordinary text untouched", () => {
  assert.equal(escapeHtml("홍길동"), "홍길동");
  assert.equal(escapeHtml("user@example.com"), "user@example.com");
});

/* ------------------------------------------------- statusLabel / statusValue
 *
 * 화면은 한글로 보여주고 API 에는 enum 을 보낸다. 두 방향이 어긋나면 필터가
 * 조용히 빈 결과를 낸다.
 */

test("statusLabel translates every account status the screens show", () => {
  assert.equal(statusLabel("ACTIVE"), "활성");
  assert.equal(statusLabel("SUSPENDED"), "정지");
  assert.equal(statusLabel("PENDING"), "대기");
  assert.equal(statusLabel("WITHDRAWN"), "탈퇴");
});

test("statusLabel passes an unknown status through unchanged", () => {
  // 새 상태가 생겨도 빈칸이 아니라 원문이 보여 무엇이 왔는지 알 수 있다.
  assert.equal(statusLabel("ARCHIVED"), "ARCHIVED");
});

test("statusLabel returns an empty string for nullish input", () => {
  assert.equal(statusLabel(undefined), "");
  assert.equal(statusLabel(null), "");
  assert.equal(statusLabel(""), "");
});

test("statusValue translates the Korean label back into the API enum", () => {
  assert.equal(statusValue("활성"), "ACTIVE");
  assert.equal(statusValue("정지"), "SUSPENDED");
  assert.equal(statusValue("대기"), "PENDING");
  assert.equal(statusValue("탈퇴"), "WITHDRAWN");
});

test("statusValue maps the 전체 placeholder to an empty filter", () => {
  // 빈 값은 buildQuery 가 쿼리에서 빼낸다. status="" 를 보내면 422 가 난다.
  assert.equal(statusValue("전체"), "");
});

test("statusValue returns an empty string for nullish or unknown labels", () => {
  assert.equal(statusValue(undefined), "");
  assert.equal(statusValue(null), "");
  assert.equal(statusValue(""), "");
  assert.equal(statusValue("없는상태"), "");
});

test("statusLabel and statusValue round-trip every known status", () => {
  for (const value of ["ACTIVE", "SUSPENDED", "PENDING", "WITHDRAWN"]) {
    assert.equal(statusValue(statusLabel(value)), value);
  }
});

/* ----------------------------------------------------- roleLabel / roleValue */

test("roleLabel translates both admin roles", () => {
  assert.equal(roleLabel("ADMIN"), "최고 관리자");
  assert.equal(roleLabel("STAFF"), "일반 관리자");
});

test("roleLabel passes an unknown role through and empties nullish input", () => {
  assert.equal(roleLabel("OWNER"), "OWNER");
  assert.equal(roleLabel(undefined), "");
  assert.equal(roleLabel(null), "");
});

test("roleValue translates the Korean label back into the API enum", () => {
  assert.equal(roleValue("최고 관리자"), "ADMIN");
  assert.equal(roleValue("일반 관리자"), "STAFF");
});

test("roleValue maps the 전체 placeholder to an empty filter", () => {
  assert.equal(roleValue("전체"), "");
});

test("roleValue returns an empty string for nullish or unknown labels", () => {
  assert.equal(roleValue(undefined), "");
  assert.equal(roleValue(null), "");
  assert.equal(roleValue(""), "");
  assert.equal(roleValue("관리자"), "");
});

test("roleLabel and roleValue round-trip both roles", () => {
  for (const value of ["ADMIN", "STAFF"]) {
    assert.equal(roleValue(roleLabel(value)), value);
  }
});

/* ----------------------------------------------------------------- buildQuery
 *
 * 빈 값은 쿼리에서 뺀다. status="" 를 그대로 보내면 서버가 422 를 낸다.
 */

test("buildQuery drops undefined, null and empty-string values", () => {
  assert.equal(
    buildQuery({ status: "", role: undefined, name: null, page: 1 }),
    "page=1",
  );
});

test("buildQuery keeps zero and false because only nullish and empty string are dropped", () => {
  // 0 과 false 는 「값이 없음」이 아니다. offset=0 이 빠지면 첫 페이지를 못 부른다.
  assert.equal(buildQuery({ offset: 0 }), "offset=0");
  assert.equal(buildQuery({ isActive: false }), "isActive=false");
});

test("buildQuery returns an empty string when nothing survives", () => {
  assert.equal(buildQuery({}), "");
  assert.equal(buildQuery({ status: "", role: undefined }), "");
});

test("buildQuery percent-encodes values so Korean search terms survive", () => {
  assert.equal(buildQuery({ name: "김" }), "name=%EA%B9%80");
  assert.equal(buildQuery({ q: "a b" }), "q=a+b");
});

test("buildQuery keeps every surviving key", () => {
  assert.equal(
    buildQuery({ role: "STAFF", status: "ACTIVE", page: 2 }),
    "role=STAFF&status=ACTIVE&page=2",
  );
});

/* ----------------------------------------------------------------- formatDate */

test("formatDate renders an ISO datetime as the dotted screen format", () => {
  // 오프셋 없는 문자열은 실행 환경의 지역 시간으로 해석되므로 어느 기계에서도 같다.
  assert.equal(formatDate("2024-11-02T10:00:00"), "2024.11.02");
});

test("formatDate zero-pads single-digit months and days", () => {
  assert.equal(formatDate("2024-01-05T00:30:00"), "2024.01.05");
  assert.equal(formatDate("2024-09-09T23:59:59"), "2024.09.09");
});

test("formatDate returns an empty string for nullish or blank input", () => {
  assert.equal(formatDate(""), "");
  assert.equal(formatDate(undefined), "");
  assert.equal(formatDate(null), "");
});

test("formatDate returns an empty string instead of Invalid Date", () => {
  assert.equal(formatDate("not-a-date"), "");
  assert.equal(formatDate("2024-13-45T00:00:00"), "");
});

test("formatDate cuts the day in the local timezone, not in UTC", () => {
  // UTC 자정 근처 값은 지역 시간대에 따라 날짜가 하루 밀린다. 그 사실을 고정한다.
  const iso = "2024-11-02T23:30:00Z";
  const local = new Date(iso);
  const expected =
    `${local.getFullYear()}.` +
    `${String(local.getMonth() + 1).padStart(2, "0")}.` +
    `${String(local.getDate()).padStart(2, "0")}`;

  assert.equal(formatDate(iso), expected);
});
