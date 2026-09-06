import { restoreAccountPrincipal } from '@/shared/api/client';
import type { NotifySettings, UpdateNotifySettingsPayload } from './types';

const STORAGE_KEY_PREFIX = 'rxvita.notify-settings';
const DEFAULT_SETTINGS: NotifySettings = {
  notifyMedication: false,
  notifySupplement: false,
  notifySchedule: false,
  notifyConsentedAt: null,
  morningMedicationTime: '08:00',
  lunchMedicationTime: '13:00',
  eveningMedicationTime: '19:00',
  bedtimeMedicationTime: '22:00',
};
const memorySettingsByScope = new Map<string, NotifySettings>();

function principalScope(): string {
  return restoreAccountPrincipal()?.trim().toLowerCase() || 'anonymous';
}

function storageKey(scope: string): string {
  return `${STORAGE_KEY_PREFIX}:${encodeURIComponent(scope)}`;
}

function readStoredSettings(): NotifySettings {
  const scope = principalScope();
  const memorySettings = memorySettingsByScope.get(scope) ?? DEFAULT_SETTINGS;
  if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') {
    return { ...memorySettings };
  }
  try {
    const raw = window.localStorage.getItem(storageKey(scope));
    if (!raw) return { ...memorySettings };
    const parsed = JSON.parse(raw) as Partial<NotifySettings>;
    const next = { ...memorySettings, ...parsed };
    memorySettingsByScope.set(scope, next);
    return { ...next };
  } catch {
    // localStorage를 사용할 수 없는 환경에서는 현재 탭 메모리를 사용합니다.
    return { ...memorySettings };
  }
}

function writeStoredSettings(next: NotifySettings): void {
  const scope = principalScope();
  memorySettingsByScope.set(scope, { ...next });
  if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') return;
  try {
    window.localStorage.setItem(storageKey(scope), JSON.stringify(next));
  } catch {
    // 저장소가 막혀도 설정 API 목업은 현재 탭 메모리로 계속 동작합니다.
  }
}

export function mockGetNotifySettings(): NotifySettings {
  return readStoredSettings();
}

export function mockUpdateNotifySettings(payload: UpdateNotifySettingsPayload): NotifySettings {
  const previous = readStoredSettings();
  const next: NotifySettings = {
    ...previous,
    ...payload,
    // 실 API도 최초 선택 요청을 받은 서버 시각으로 기록합니다. 프론트는 시각을 보내지 않습니다.
    notifyConsentedAt: previous.notifyConsentedAt ?? new Date().toISOString(),
  };
  writeStoredSettings(next);
  return { ...next };
}
