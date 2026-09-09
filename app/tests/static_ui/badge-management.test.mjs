import test from "node:test";
import assert from "node:assert/strict";

import * as management from "../../static/js/badge-management.js";

test("badge row actions place delete immediately after edit", () => {
  assert.equal(
    management.badgeActionMarkup(17),
    '<button type="button" class="ui-link-button" data-edit-badge="17">수정</button> '
      + '<button type="button" class="ui-link-button ui-link-button-danger" data-delete-badge="17">삭제</button>',
  );
});

test("badge row actions disable delete for a badge in use", () => {
  assert.equal(
    management.badgeActionMarkup(17, false),
    '<button type="button" class="ui-link-button" data-edit-badge="17">수정</button> '
      + '<button type="button" class="ui-link-button ui-link-button-danger" data-delete-badge="17" disabled aria-disabled="true" title="사용 중인 배지는 삭제할 수 없습니다.">삭제</button>',
  );
});
