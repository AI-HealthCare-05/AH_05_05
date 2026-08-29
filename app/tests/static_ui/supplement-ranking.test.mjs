import test from "node:test";
import assert from "node:assert/strict";

import {
  buildRankDisplayPayload,
  renderRankDisplayRows,
  renderSupplementRanking,
  toDefaultRankItems,
  validateRankDisplayInput,
} from "../../static/js/supplement-ranking.js";

test("toDefaultRankItems uses the five most popular supplements in response order", () => {
  const supplements = Array.from({ length: 7 }, (_, index) => ({
    id: index + 1,
    name: `영양제 ${index + 1}`,
    userCount: 100 - index,
  }));

  assert.deepEqual(toDefaultRankItems(supplements), [
    { id: 1, name: "영양제 1" },
    { id: 2, name: "영양제 2" },
    { id: 3, name: "영양제 3" },
    { id: 4, name: "영양제 4" },
    { id: 5, name: "영양제 5" },
  ]);
});

test("renderSupplementRanking shows rank, supplement ID and escaped name", () => {
  const tbody = { innerHTML: "" };

  renderSupplementRanking(tbody, [
    { id: 17, name: "비타민 <D>" },
    { id: 23, name: "철분" },
  ]);

  assert.match(tbody.innerHTML, /<td>1<\/td>/);
  assert.match(tbody.innerHTML, /<td>17<\/td>/);
  assert.match(tbody.innerHTML, /비타민 &lt;D&gt;/);
  assert.match(tbody.innerHTML, /<td>2<\/td>/);
  assert.match(tbody.innerHTML, /<td>23<\/td>/);
});

test("validateRankDisplayInput validates period and a contiguous unique ranking", () => {
  assert.equal(
    validateRankDisplayInput({
      title: "9월 랭킹",
      startAt: "2026-09-01T00:00",
      endAt: "2026-09-30T23:59",
      items: [
        { id: 1, rankNo: 1 },
        { id: 2, rankNo: 2 },
      ],
    }),
    "",
  );
  assert.match(
    validateRankDisplayInput({
      title: "9월 랭킹",
      startAt: "2026-09-30T00:00",
      endAt: "2026-09-01T00:00",
      items: [{ id: 1, rankNo: 1 }],
    }),
    /종료 일시/,
  );
  assert.match(
    validateRankDisplayInput({
      title: "9월 랭킹",
      startAt: "2026-09-01T00:00",
      endAt: "2026-09-30T00:00",
      items: [
        { id: 1, rankNo: 1 },
        { id: 1, rankNo: 2 },
      ],
    }),
    /중복/,
  );
});

test("buildRankDisplayPayload maps selected products to API camelCase items", () => {
  assert.deepEqual(
    buildRankDisplayPayload({
      title: "  9월 랭킹  ",
      startAt: "2026-09-01T00:00",
      endAt: "2026-09-30T23:59",
      isEnabled: true,
      items: [
        { id: 4, name: "비타민 D" },
        { id: 8, name: "철분" },
      ],
    }),
    {
      title: "9월 랭킹",
      startAt: "2026-09-01T00:00",
      endAt: "2026-09-30T23:59",
      isEnabled: true,
      items: [
        { supplementNutrientId: 4, rankNo: 1 },
        { supplementNutrientId: 8, rankNo: 2 },
      ],
    },
  );
});

test("renderRankDisplayRows shows display state, item count and admin actions", () => {
  const tbody = { innerHTML: "" };
  renderRankDisplayRows(
    tbody,
    [
      {
        display_id: 11,
        title: "추천 <랭킹>",
        start_at: "2026-09-01T00:00:00+09:00",
        end_at: "2026-09-30T23:59:00+09:00",
        is_enabled: true,
        item_count: 5,
      },
    ],
    true,
  );
  assert.match(tbody.innerHTML, /추천 &lt;랭킹&gt;/);
  assert.match(tbody.innerHTML, /활성/);
  assert.match(tbody.innerHTML, /5개/);
  assert.match(tbody.innerHTML, /data-edit-display="11"/);
  assert.match(tbody.innerHTML, /data-delete-display="11"/);
});

test("renderRankDisplayRows shows edit and delete actions to STAFF", () => {
  const tbody = { innerHTML: "" };

  renderRankDisplayRows(
    tbody,
    [
      {
        display_id: 12,
        title: "STAFF 조회 전시",
        start_at: "2026-09-01T00:00:00+09:00",
        end_at: "2026-09-30T23:59:00+09:00",
        is_enabled: false,
        item_count: 3,
      },
    ],
    false,
  );

  assert.match(tbody.innerHTML, /data-edit-display="12"/);
  assert.match(tbody.innerHTML, /data-delete-display="12"/);
});
