import test from "node:test";
import assert from "node:assert/strict";

import { setRememberedLoginId, validateCredentials, validatePasswordChange } from "../../static/js/login.js";

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

test("validatePasswordChange rejects blank password fields", () => {
  assert.deepEqual(validatePasswordChange("", "", ""), {
    valid: false,
    errors: {
      currentPassword: "현재 비밀번호를 입력해주세요.",
      newPassword: "새 비밀번호를 입력해주세요.",
      newPasswordConfirm: "새 비밀번호를 한 번 더 입력해주세요.",
    },
  });
});

test("validatePasswordChange rejects a mismatched confirmation", () => {
  assert.deepEqual(validatePasswordChange("Temp1234!", "NewPass1!", "NewPass2!"), {
    valid: false,
    errors: { newPasswordConfirm: "새 비밀번호가 일치하지 않습니다." },
  });
});

test("validatePasswordChange leaves the policy to the server", () => {
  // 8자 미만이지만 프론트는 막지 않는다. 정책 판정은 서버 몫이다.
  assert.deepEqual(validatePasswordChange("Temp1234!", "short", "short"), { valid: true, errors: {} });
});

test("validatePasswordChange accepts a matching confirmation", () => {
  assert.deepEqual(validatePasswordChange("Temp1234!", "NewPass1!", "NewPass1!"), { valid: true, errors: {} });
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
