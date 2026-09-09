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
