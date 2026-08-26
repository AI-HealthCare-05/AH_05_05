import { ApiError, post, session } from "./api.js";
import { showToast } from "./overlay.js";

const REMEMBERED_LOGIN_ID_KEY = "rememberedLoginId";

export function validateCredentials(loginId, password) {
  const errors = {};

  if (!loginId.trim()) {
    errors.loginId = "관리자 ID를 입력해주세요.";
  }

  if (!password) {
    errors.password = "비밀번호를 입력해주세요.";
  }

  return { valid: Object.keys(errors).length === 0, errors };
}

export function setRememberedLoginId(storage, loginId, remember) {
  if (remember) {
    storage.setItem(REMEMBERED_LOGIN_ID_KEY, loginId.trim());
    return;
  }

  storage.removeItem(REMEMBERED_LOGIN_ID_KEY);
}

function setFieldError(input, errorElement, message = "") {
  input.setAttribute("aria-invalid", String(Boolean(message)));
  errorElement.textContent = message;
}

function initializeLoginForm() {
  const form = document.querySelector("[data-login-form]");
  if (!form) return;

  const loginIdInput = form.elements.loginId;
  const passwordInput = form.elements.password;
  const rememberInput = form.elements.remember;
  const loginIdError = document.querySelector("[data-error-for='loginId']");
  const passwordError = document.querySelector("[data-error-for='password']");
  const passwordToggle = document.querySelector("[data-password-toggle]");
  const submitButton = form.querySelector("[type='submit']");
  const rememberedLoginId = window.localStorage.getItem(REMEMBERED_LOGIN_ID_KEY);

  if (rememberedLoginId) {
    loginIdInput.value = rememberedLoginId;
    rememberInput.checked = true;
  }

  passwordToggle?.addEventListener("click", () => {
    const isVisible = passwordInput.type === "text";
    passwordInput.type = isVisible ? "password" : "text";
    passwordToggle.setAttribute("aria-pressed", String(!isVisible));
    passwordToggle.setAttribute("aria-label", isVisible ? "비밀번호 표시" : "비밀번호 숨기기");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const result = validateCredentials(loginIdInput.value, passwordInput.value);
    setFieldError(loginIdInput, loginIdError, result.errors.loginId);
    setFieldError(passwordInput, passwordError, result.errors.password);

    if (!result.valid) return;

    const originalLabel = submitButton?.textContent;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "로그인 중…";
    }

    try {
      // 폼 필드명은 loginId 지만 API 는 email 을 받는다. 라벨·필드명은 화면 그대로 둔다.
      const body = await post("/admin/auth/login", {
        email: loginIdInput.value.trim(),
        password: passwordInput.value,
      });

      setRememberedLoginId(window.localStorage, loginIdInput.value, rememberInput.checked);
      session.save(body.accessToken, body.admin);

      if (body.mustChangePassword) {
        // 임시 비밀번호로 로그인한 상태다(계정 상태와는 무관).
        // 비밀번호를 바꾸기 전에는 다른 관리자 API 가 전부 403 이라 대시보드로 보내면
        // 빈 화면만 보게 된다. 자체 비밀번호 변경 화면이 아직 없어 여기서 멈춘다.
        session.clear();
        showToast("임시 비밀번호입니다. 비밀번호를 변경한 뒤 이용해 주세요.", "error");
        return;
      }

      window.location.href = form.dataset.dashboardUrl;
    } catch (error) {
      // 401 은 "계정 없음"과 "비밀번호 오류"를 구분하지 않는다.
      // 서버 문구를 그대로 띄운다 — 프론트가 구분 문구를 만들면 이메일 존재 여부가 새어나간다.
      const message = error instanceof ApiError ? error.message : "로그인에 실패했습니다.";
      showToast(message, "error");
      setFieldError(passwordInput, passwordError, message);
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel;
      }
    }
  });
}

if (typeof document !== "undefined") {
  initializeLoginForm();
}
