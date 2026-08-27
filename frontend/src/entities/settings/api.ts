import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockGetNotifySettings, mockUpdateNotifySettings } from './api.mock';
import type { NotifySettings, UpdateNotifySettingsPayload } from './types';

export async function getNotifySettings(): Promise<NotifySettings> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetNotifySettings();
  }
  return http.get<NotifySettings>('/v1/me/settings');
}

export async function updateNotifySettings(
  payload: UpdateNotifySettingsPayload,
): Promise<NotifySettings> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateNotifySettings(payload);
  }
  return http.patch<NotifySettings>('/v1/me/settings', payload);
}
