import test from "node:test";
import assert from "node:assert/strict";

import * as management from "../../static/js/custom-challenge-template-management.js";

test("resetCustomTemplateFilters clears a dynamically selected check type", () => {
  const checkType = { value: "29" };
  const form = {
    elements: {
      template_id: { value: "15" },
      name: { value: "걷기" },
      check_type_id: checkType,
      is_active: { value: "true" },
    },
  };

  management.resetCustomTemplateFilters(form);

  assert.equal(checkType.value, "");
  assert.equal(form.elements.template_id.value, "");
  assert.equal(form.elements.name.value, "");
  assert.equal(form.elements.is_active.value, "");
});
