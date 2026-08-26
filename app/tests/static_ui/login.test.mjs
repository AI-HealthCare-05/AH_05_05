import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { setRememberedLoginId, validateCredentials } from "../../static/js/login.js";

test("validateCredentials rejects blank login fields", () => {
  assert.deepEqual(validateCredentials("  ", ""), {
    valid: false,
    errors: {
      loginId: "관리자 ID를 입력해주세요.",
      password: "비밀번호를 입력해주세요.",
    },
  });
});

test("validateCredentials accepts non-empty login fields", () => {
  assert.deepEqual(validateCredentials(" admin_ops_01@ozcoding.ai ", "secret"), {
    valid: true,
    errors: {},
  });
});

test("setRememberedLoginId stores only the login ID when remember is enabled", () => {
  const values = new Map();
  const storage = {
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
  };

  setRememberedLoginId(storage, "admin@ozcoding.ai", true);

  assert.deepEqual([...values.entries()], [["rememberedLoginId", "admin@ozcoding.ai"]]);
});

test("setRememberedLoginId clears the saved ID when remember is disabled", () => {
  const values = new Map([["rememberedLoginId", "old@ozcoding.ai"]]);
  const storage = {
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
  };

  setRememberedLoginId(storage, "admin@ozcoding.ai", false);

  assert.equal(values.has("rememberedLoginId"), false);
});

test("login page cache-busts the API-connected login script", async () => {
  const templateUrl = new URL("../../static/templates/login.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /src="\.\.\/js\/login\.js\?v=\d{8}-\d+"/);
});
