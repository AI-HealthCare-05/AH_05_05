import { ApiError, patch, post, session } from "./api.js";
import { closeOverlay, openOverlay, showToast } from "./overlay.js";

const REMEMBERED_LOGIN_ID_KEY = "rememberedLoginId";

const PASSWORD_FIELDS = ["currentPassword", "newPassword", "newPasswordConfirm"];

/**
 * 실패 코드를 입력칸에 매핑한다.
 *
 * message 문자열로 분기하면 서버 문구가 바뀔 때 화면이 조용히 깨진다.
 * 표시하는 문구는 항상 서버가 준 message 를 그대로 쓴다.
 */
const FIELD_BY_ERROR_CODE = {
  INVALID_PASSWORD: "currentPassword",
  SAME_AS_CURRENT: "newPassword",
};

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

/**
 * 비밀번호 변경 폼의 프론트 검증.
 *
 * 정책(8자·대소문자·숫자·특수문자)은 서버가 판정한다. 여기서 같은 규칙을 다시 구현하면
 * 서버 정책이 바뀔 때 두 곳이 어긋난다. 비어 있는지와 확인 값이 맞는지만 본다.
 */
export function validatePasswordChange(currentPassword, newPassword, newPasswordConfirm) {
  const errors = {};

  if (!currentPassword) {
    errors.currentPassword = "현재 비밀번호를 입력해주세요.";
  }

  if (!newPassword) {
    errors.newPassword = "새 비밀번호를 입력해주세요.";
  }

  if (!newPasswordConfirm) {
    errors.newPasswordConfirm = "새 비밀번호를 한 번 더 입력해주세요.";
  } else if (newPassword && newPassword !== newPasswordConfirm) {
    errors.newPasswordConfirm = "새 비밀번호가 일치하지 않습니다.";
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

/**
 * 오버레이가 DOM 에서 사라지는 순간을 잡는다.
 *
 * 배경 클릭·ESC·취소 버튼은 모두 overlay.js 의 closeOverlay() 로 들어가고, 그중 ESC 는
 * document 리스너라 openOverlay 의 options 로는 가로챌 수 없다. 닫는 경로마다 처리를
 * 붙이는 대신 "패널이 제거됐다"는 결과 하나만 본다. overlay.js 는 건드리지 않는다.
 */
function whenOverlayClosed(host, handler) {
  const observer = new MutationObserver(() => {
    if (host.isConnected) return;
    observer.disconnect();
    handler();
  });
  observer.observe(document.body, { childList: true });
  return observer;
}

/**
 * 임시 비밀번호로 로그인한 관리자에게 비밀번호 변경을 받는다. (REQ-ADMIN-009)
 *
 * 변경 전에는 다른 관리자 API 가 전부 403 이라, 이 오버레이를 통과하지 못하면
 * 콘솔에 들어갈 수 없다. 그래서 어떤 방식으로 닫든 세션을 비우고 로그인 화면으로 되돌린다.
 */
async function requestPasswordChange({ onCancel, onSuccess }) {
  let settled = false;

  const overlay = await openOverlay("overlay-password-change.html", {
    onConfirm: async (panel) => {
      const valueOf = (field) => panel.querySelector(`[name='${field}']`)?.value ?? "";
      const setPanelError = (field, message = "") => {
        const input = panel.querySelector(`[name='${field}']`);
        const errorElement = panel.querySelector(`[data-error-for='${field}']`);
        input?.setAttribute("aria-invalid", String(Boolean(message)));
        if (errorElement) errorElement.textContent = message;
      };

      const currentPassword = valueOf("currentPassword");
      const newPassword = valueOf("newPassword");

      const result = validatePasswordChange(currentPassword, newPassword, valueOf("newPasswordConfirm"));
      PASSWORD_FIELDS.forEach((field) => setPanelError(field, result.errors[field]));
      if (!result.valid) return;

      const confirmButton = panel.querySelector("[data-overlay-confirm]");
      const originalLabel = confirmButton?.textContent;
      if (confirmButton) {
        confirmButton.disabled = true;
        confirmButton.textContent = "변경 중…";
      }

      try {
        // 확인 칸은 보내지 않는다. API 는 currentPassword·newPassword 만 받는다.
        await patch("/admin/accounts/password", { currentPassword, newPassword });
        settled = true;
        closeOverlay();
        onSuccess();
      } catch (error) {
        if (!(error instanceof ApiError)) {
          showToast("비밀번호를 변경하지 못했습니다.", "error");
          return;
        }
        // 422 는 공통 핸들러가 field 를 함께 준다. 없으면 코드로 칸을 찾는다.
        const field = FIELD_BY_ERROR_CODE[error.code] ?? (PASSWORD_FIELDS.includes(error.field) ? error.field : null);
        if (field) setPanelError(field, error.message);
        else showToast(error.message, "error");
      } finally {
        if (confirmButton) {
          confirmButton.disabled = false;
          confirmButton.textContent = originalLabel;
        }
      }
    },
  });

  whenOverlayClosed(overlay, () => {
    if (settled) return;
    onCancel();
  });
}

function initializeLoginForm() {
  const form = document.querySelector("[data-login-form]");
  if (!form) return;

  const loginIdInput = form.elements.loginId;
  const passwordInput = form.elements.password;
  const loginIdError = document.querySelector("[data-error-for='loginId']");
  const passwordError = document.querySelector("[data-error-for='password']");
  const passwordToggle = document.querySelector("[data-password-toggle]");
  const submitButton = form.querySelector("[type='submit']");

  // 체크박스가 사라져 다시 저장할 방법이 없다. 예전에 저장된 값이 남아 있으면
  // 지울 수도 없이 계속 채워지므로 여기서 한 번 비운다.
  window.localStorage.removeItem(REMEMBERED_LOGIN_ID_KEY);

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

      session.save(body.accessToken, body.admin);

      if (body.mustChangePassword) {
        // 임시 비밀번호로 로그인한 상태다(계정 상태와는 무관).
        // 여기서 세션을 비우면 안 된다 — 변경 API 도 Bearer 토큰을 요구한다.
        // PENDING 계정도 그 엔드포인트만은 통과한다(get_current_admin_allow_pending).
        await requestPasswordChange({
          onCancel: () => {
            session.clear();
            passwordInput.value = "";
            showToast("비밀번호를 변경해야 콘솔을 이용할 수 있습니다.", "error");
          },
          onSuccess: () => {
            // 변경과 함께 이 브라우저의 리프레시 쿠키가 지워진다. 남은 액세스 토큰으로
            // 들어가면 만료 뒤 갱신하지 못해 튕기므로, 새 비밀번호로 다시 로그인시킨다.
            session.clear();
            passwordInput.value = "";
            showToast("비밀번호를 변경했습니다. 새 비밀번호로 다시 로그인해 주세요.");
            passwordInput.focus();
          },
        });
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
