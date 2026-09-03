import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../../static/templates/common-code-management.html", import.meta.url);
const moduleUrl = new URL("../../static/js/common-code-management.js", import.meta.url);

test("common code management exposes category-aware split lists and edit dialogs", async () => {
  const html = await readFile(pageUrl, "utf8");

  assert.match(html, /name="category"/);
  assert.match(html, /data-group-list/);
  assert.match(html, /data-code-list/);
  assert.match(html, /data-group-pagination/);
  assert.match(html, /data-code-pagination/);
  assert.match(html, /data-group-dialog/);
  assert.match(html, /data-code-dialog/);
  assert.match(html, /common-code-management\.js/);
});

test("common code helpers normalize uppercase codes and build paging queries", async () => {
  const { buildGroupQuery, isValidCodeInput, normalizeCodeInput } = await import(moduleUrl);

  assert.equal(normalizeCodeInput(" chat_reason "), "CHAT_REASON");
  assert.equal(isValidCodeInput("CHAT_REASON"), true);
  assert.equal(isValidCodeInput("CHAT-REASON"), false);
  assert.deepEqual(
    buildGroupQuery({
      category: "chat",
      groupCode: "p_reason",
      groupName: "긍정",
      isActive: "true",
      page: 2,
      size: 20,
    }),
    {
      category: "CHAT",
      group_code: "P_REASON",
      group_name: "긍정",
      is_active: "true",
      offset: 20,
      limit: 20,
    },
  );
});

test("group edit mode locks category and group code fields", async () => {
  const script = await readFile(moduleUrl, "utf8");

  assert.match(script, /elements\.category\.disabled = Boolean\(group\)/);
  assert.match(script, /elements\.group_code\.disabled = Boolean\(group\)/);
});

test("group edit payload omits immutable category and group code", async () => {
  const { buildGroupPayload } = await import(moduleUrl);
  const values = {
    category: "CHAT",
    groupCode: "P_REASON",
    groupName: "긍정 사유",
    description: "설명",
    isActive: true,
  };

  assert.deepEqual(buildGroupPayload(values, true), {
    group_name: "긍정 사유",
    description: "설명",
    is_active: true,
  });
  assert.deepEqual(buildGroupPayload(values, false), {
    category: "CHAT",
    group_code: "P_REASON",
    group_name: "긍정 사유",
    description: "설명",
    is_active: true,
  });
});

test("sort order input removes every non-digit character", async () => {
  const { sanitizeSortOrderInput } = await import(moduleUrl);

  assert.equal(sanitizeSortOrderInput("1e+2-3"), "123");
  assert.equal(sanitizeSortOrderInput(" 45가 "), "45");
});

test("sort order parser rejects an empty value and accepts zero or positive integers", async () => {
  const { parseSortOrder } = await import(moduleUrl);

  assert.equal(parseSortOrder(""), null);
  assert.equal(parseSortOrder("0"), 0);
  assert.equal(parseSortOrder("0012"), 12);
});
