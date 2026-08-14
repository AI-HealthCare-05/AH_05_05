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

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const result = validateCredentials(loginIdInput.value, passwordInput.value);
    setFieldError(loginIdInput, loginIdError, result.errors.loginId);
    setFieldError(passwordInput, passwordError, result.errors.password);

    if (!result.valid) return;

    setRememberedLoginId(window.localStorage, loginIdInput.value, rememberInput.checked);
    window.sessionStorage.setItem("adminAuthenticated", "true");
    window.location.href = form.dataset.dashboardUrl;
  });
}

if (typeof document !== "undefined") {
  initializeLoginForm();
}
