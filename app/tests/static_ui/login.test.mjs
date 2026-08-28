import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  PASSWORD_HELP_MESSAGE,
  setRememberedLoginId,
  validateCredentials,
  validatePasswordChange,
} from "../../static/js/login.js";

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

test("login page loads the API-connected login script", async () => {
  const templateUrl = new URL("../../static/templates/login.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  // ?v= 쿼리는 더 이상 쓰지 않는다. 서버가 Cache-Control: no-cache 를 주므로
  // 캐시 무효화는 app/tests/test_static_cache_headers.py 가 검증한다.
  assert.match(html, /src="\.\.\/js\/login\.js"/);
});

test("password help link is wired for the script to hook", async () => {
  const templateUrl = new URL("../../static/templates/login.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /data-password-help/);
});

test("password help points to the super admin instead of self-service reset", () => {
  // 자가 재설정은 만들지 않았다. 문구가 "직접 재설정" 쪽으로 바뀌면 없는 기능을 안내하게 된다.
  assert.match(PASSWORD_HELP_MESSAGE, /최고관리자/);
});

test("login script reads isFirstLogin, not the removed mustChangePassword", async () => {
  // 백엔드가 필드를 개명했다. 옛 이름을 읽으면 undefined 라 에러 없이 조용히 프롬프트가
  // 안 뜬다. 그 회귀를 여기서 잡는다.
  const scriptUrl = new URL("../../static/js/login.js", import.meta.url);
  const source = await readFile(scriptUrl, "utf8");

  assert.match(source, /body\.isFirstLogin/);
  assert.doesNotMatch(source, /mustChangePassword/);
});
