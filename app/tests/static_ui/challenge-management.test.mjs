import test from "node:test";
import assert from "node:assert/strict";

import * as management from "../../static/js/challenge-management.js";

test("official challenges resolve the STANDARD badge type", () => {
  assert.equal(management.CHALLENGE_BADGE_TYPE_PATH, "/common-codes/CHL/BDG_TYPE");
  assert.equal(
    management.standardBadgeTypeId([
      { id: 34, detail_code: "STANDARD" },
      { id: 35, detail_code: "CUSTOM" },
    ]),
    34,
  );
});

test("challenge row disables delete when participants exist", () => {
  assert.equal(
    management.challengeActionMarkup(17, false),
    '<button type="button" class="ui-link-button" data-edit-challenge="17">수정</button> '
      + '<button type="button" class="ui-link-button ui-link-button-danger" data-delete-challenge="17" disabled aria-disabled="true" title="참여자가 있는 챌린지는 삭제할 수 없습니다.">삭제</button>',
  );
});

test("challenge edit action changes from save to participation confirmation", () => {
  assert.deepEqual(management.challengePrimaryActionState(0), {
    type: "submit",
    label: "저장",
    opensParticipants: false,
  });
  assert.deepEqual(management.challengePrimaryActionState(3), {
    type: "button",
    label: "챌린지 참여 확인",
    opensParticipants: true,
  });
});

test("challenge participation paging uses 20 records per page", () => {
  assert.deepEqual(management.challengeParticipantPagination(41, 2), {
    currentPage: 2,
    totalPages: 3,
    pages: [1, 2, 3],
    hasPrevious: true,
    hasNext: true,
    pageSize: 20,
  });
});
