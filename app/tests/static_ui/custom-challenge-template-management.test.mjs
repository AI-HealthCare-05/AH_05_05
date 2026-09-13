import test from "node:test";
import assert from "node:assert/strict";

import * as management from "../../static/js/custom-challenge-template-management.js";

test("custom challenge templates load check types from CST_CHK_TYPE", () => {
  assert.equal(management.CUSTOM_TEMPLATE_CHECK_TYPE_PATH, "/common-codes/CHL/CST_CHK_TYPE");
});

test("custom challenge templates load challenge types from CST_CHL_TYPE", () => {
  assert.equal(management.CUSTOM_TEMPLATE_CHALLENGE_TYPE_PATH, "/common-codes/CHL/CST_CHL_TYPE");
});

test("custom challenge templates resolve the CUSTOM badge type", () => {
  assert.equal(management.CUSTOM_TEMPLATE_BADGE_TYPE_PATH, "/common-codes/CHL/BDG_TYPE");
  assert.equal(
    management.customBadgeTypeId([
      { id: 11, detail_code: "STANDARD" },
      { id: 12, detail_code: "CUSTOM" },
    ]),
    12,
  );
});

test("resetCustomTemplateFilters clears a dynamically selected check type", () => {
  const checkType = { value: "29" };
  const form = {
    elements: {
      template_id: { value: "15" },
      name: { value: "걷기" },
      challenge_type: { value: "42" },
      check_type_id: checkType,
      is_active: { value: "true" },
    },
  };

  management.resetCustomTemplateFilters(form);

  assert.equal(checkType.value, "");
  assert.equal(form.elements.template_id.value, "");
  assert.equal(form.elements.name.value, "");
  assert.equal(form.elements.challenge_type.value, "");
  assert.equal(form.elements.is_active.value, "");
});

test("custom template delete is enabled only when the template is unused", () => {
  assert.equal(
    management.customTemplateActionMarkup({ id: 15, is_deletable: true }),
    '<span class="common-code-row-actions"><button type="button" class="ui-link-button" data-edit-custom-template="15">수정</button><button type="button" class="ui-link-button ui-link-button-danger" data-delete-custom-template="15">삭제</button></span>',
  );
  assert.equal(
    management.customTemplateActionMarkup({ id: 16, is_deletable: false }),
    '<span class="common-code-row-actions"><button type="button" class="ui-link-button" data-edit-custom-template="16">수정</button><button type="button" class="ui-link-button ui-link-button-danger" data-delete-custom-template="16" disabled aria-disabled="true" title="사용 중인 템플릿은 삭제할 수 없습니다.">삭제</button></span>',
  );
});
