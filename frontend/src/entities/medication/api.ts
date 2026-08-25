/**
 * 복약 API. 화면은 이 함수들만 부릅니다.
 * 목업 ↔ 실서버 전환 규칙은 entities/document/api.ts 와 같습니다.
 */
import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockMedicationOverview,
  mockMedicationSchedule,
  mockSaveMedicationSchedule,
  resetMockMedicationForNewAccount,
} from './api.mock';
import type {
  MedicationOverview,
  MedicationSchedule,
  SaveMedicationSchedulePayload,
  SaveMedicationScheduleResponse,
} from './types';

export async function getMedicationOverview(): Promise<MedicationOverview> {
  if (USE_MOCK) {
    await mockDelay();
    return mockMedicationOverview();
  }
  return http.get<MedicationOverview>('/medications');
}

export function prepareMedicationStateForNewAccount(): void {
  if (USE_MOCK) resetMockMedicationForNewAccount();
}

/** REQ-CARE-003 — GET /medications/schedule?recordId=... · 명세 5-3 */
export async function getMedicationSchedule(recordId: number): Promise<MedicationSchedule> {
  if (USE_MOCK) {
    await mockDelay();
    return mockMedicationSchedule();
  }
  return http.get<MedicationSchedule>(`/medications/schedule?recordId=${recordId}`);
}

/** REQ-CARE-003 — PUT /medications/schedule · 명세 5-3 */
export async function saveMedicationSchedule(
  payload: SaveMedicationSchedulePayload,
): Promise<SaveMedicationScheduleResponse> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSaveMedicationSchedule(payload);
  }
  return http.put<SaveMedicationScheduleResponse>('/medications/schedule', payload);
}
