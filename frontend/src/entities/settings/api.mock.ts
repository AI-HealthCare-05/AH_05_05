import type { NotifySettings, UpdateNotifySettingsPayload } from './types';

let settings: NotifySettings = {
  notifyMedication: false,
  notifySupplement: false,
  notifyConsentedAt: null,
};

export function mockGetNotifySettings(): NotifySettings {
  return { ...settings };
}

export function mockUpdateNotifySettings(payload: UpdateNotifySettingsPayload): NotifySettings {
  settings = {
    ...settings,
    ...payload,
    // 실 API도 최초 선택 요청을 받은 서버 시각으로 기록합니다. 프론트는 시각을 보내지 않습니다.
    notifyConsentedAt: settings.notifyConsentedAt ?? new Date().toISOString(),
  };
  return { ...settings };
}
