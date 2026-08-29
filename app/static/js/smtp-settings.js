import { ApiError, get, put } from "./api.js";
import { closeOverlay, openOverlay, showToast } from "./overlay.js";

const SMTP_SETTINGS_URL = "/admin/settings/smtp";
const SMTP_SETTINGS_OVERLAY_URL = "overlay-smtp-settings.html";

function field(panel, name) {
  return panel.querySelector(`[name='${name}']`);
}

export function populateSmtpSettingsForm(panel, settings) {
  field(panel, "smtpHost").value = settings.smtpHost ?? "";
  field(panel, "smtpPort").value = String(settings.smtpPort ?? 587);
  field(panel, "smtpUser").value = settings.smtpUser ?? "";
  field(panel, "smtpPassword").value = "";
  field(panel, "smtpFromEmail").value = settings.smtpFromEmail ?? "";
  const passwordHint = panel.querySelector("[data-smtp-password-hint]");
  if (passwordHint) {
    passwordHint.textContent = settings.smtpPasswordConfigured
      ? "저장된 비밀번호가 있습니다. 변경할 때만 입력해 주세요."
      : "최초 저장 시 비밀번호를 입력해 주세요.";
  }
}

export function buildSmtpSettingsPayload(panel) {
  const payload = {
    smtpHost: field(panel, "smtpHost").value.trim(),
    smtpPort: Number(field(panel, "smtpPort").value),
    smtpUser: field(panel, "smtpUser").value.trim(),
    smtpFromEmail: field(panel, "smtpFromEmail").value.trim(),
  };
  const smtpPassword = field(panel, "smtpPassword").value.trim();
  if (smtpPassword) payload.smtpPassword = smtpPassword;
  return payload;
}

export async function openSmtpSettings() {
  try {
    const settings = await get(SMTP_SETTINGS_URL);
    const overlay = await openOverlay(SMTP_SETTINGS_OVERLAY_URL, {
      onConfirm: async (panel) => {
        const form = panel.querySelector("form");
        if (form && !form.reportValidity()) return;
        const saveButton = panel.querySelector("[data-overlay-confirm]");
        if (saveButton) saveButton.disabled = true;
        try {
          await put(SMTP_SETTINGS_URL, buildSmtpSettingsPayload(panel));
          closeOverlay();
          showToast("SMTP 설정을 저장했습니다.");
        } catch (error) {
          const message = error instanceof ApiError ? error.message : "SMTP 설정을 저장하지 못했습니다.";
          showToast(message, "error");
          if (saveButton) saveButton.disabled = false;
        }
      },
    });
    populateSmtpSettingsForm(overlay, settings);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "SMTP 설정을 불러오지 못했습니다.";
    showToast(message, "error");
  }
}
