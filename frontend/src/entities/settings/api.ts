import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockGetNotifySettings, mockUpdateNotifySettings } from './api.mock';
import type { NotifySettings, UpdateNotifySettingsPayload } from './types';

interface NotifySettingsApiResponse {
  notifyMedication: boolean;
  notifySupplement: boolean;
  notifySchedule: boolean;
  notifyConsentedAt: string | null;
  morningMedicationTime: string;
  lunchMedicationTime: string;
  eveningMedicationTime: string;
  bedtimeMedicationTime: string;
}

function mapNotifySettings(response: NotifySettingsApiResponse): NotifySettings {
  return {
    ...response,
    morningMedicationTime: response.morningMedicationTime.slice(0, 5),
    lunchMedicationTime: response.lunchMedicationTime.slice(0, 5),
    eveningMedicationTime: response.eveningMedicationTime.slice(0, 5),
    bedtimeMedicationTime: response.bedtimeMedicationTime.slice(0, 5),
  };
}

export async function getNotifySettings(): Promise<NotifySettings> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetNotifySettings();
  }
  return mapNotifySettings(await http.get<NotifySettingsApiResponse>('/v1/me/settings'));
}

export async function updateNotifySettings(
  payload: UpdateNotifySettingsPayload,
): Promise<NotifySettings> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateNotifySettings(payload);
  }
  return mapNotifySettings(
    await http.patch<NotifySettingsApiResponse>('/v1/me/settings', payload),
  );
}
