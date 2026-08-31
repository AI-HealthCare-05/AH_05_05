/**
 * 복약 API. 화면은 이 함수들만 부릅니다.
 * 목업 ↔ 실서버 전환 규칙은 entities/document/api.ts 와 같습니다.
 */
import { ApiError, http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockMedicationOverview,
  mockMedicationOverviews,
  mockMedicationSchedule,
  mockGetDoseRecords,
  mockSaveDoseTaken,
  mockSaveMedicationSchedule,
  resetMockMedicationForNewAccount,
} from './api.mock';
import type {
  DoseRecord,
  DoseRecordRange,
  MedicationOverview,
  MedicationSchedule,
  SaveMedicationSchedulePayload,
  SaveMedicationScheduleResponse,
  SaveDoseTakenPayload,
} from './types';

type MedicationOverviewResponse =
  | MedicationOverview
  | MedicationOverview[]
  | { episodes: MedicationOverview[] };

export async function getMedicationOverviews(): Promise<MedicationOverview[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockMedicationOverviews();
  }
  try {
    const response = await http.get<MedicationOverviewResponse>('/v1/medications');
    if (Array.isArray(response)) return response;
    if ('episodes' in response) return response.episodes;
    return [response];
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return [];
    throw error;
  }
}

export async function getMedicationOverview(recordId?: number): Promise<MedicationOverview> {
  if (USE_MOCK) {
    await mockDelay();
    return mockMedicationOverview(recordId);
  }
  const overviews = await getMedicationOverviews();
  const overview = recordId === undefined
    ? overviews[0]
    : overviews.find((item) => item.recordId === recordId);
  if (!overview) throw new Error('복약 기록을 찾지 못했어요.');
  return overview;
}

export function prepareMedicationStateForNewAccount(): void {
  if (USE_MOCK) resetMockMedicationForNewAccount();
}

/** REQ-CARE-003 — GET /med/medication/schedule/{record_id} · 명세 5-3 */
export async function getMedicationSchedule(recordId: number): Promise<MedicationSchedule> {
  if (USE_MOCK) {
    await mockDelay();
    return mockMedicationSchedule();
  }
  return http.get<MedicationSchedule>(`/v1/med/medication/schedule/${recordId}`);
}

/** REQ-CARE-003 — PUT /med/medication/schedule/{record_id} · 명세 5-3 */
export async function saveMedicationSchedule(
  recordId: number,
  payload: SaveMedicationSchedulePayload,
): Promise<SaveMedicationScheduleResponse> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSaveMedicationSchedule(payload);
  }
  return http.put<SaveMedicationScheduleResponse>(`/v1/med/medication/schedule/${recordId}`, payload);
}

export async function saveDoseTaken(payload: SaveDoseTakenPayload): Promise<DoseRecord> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSaveDoseTaken(payload);
  }
  return http.post<DoseRecord>('/v1/medications/doses', payload);
}

export async function getDoseRecords(range: DoseRecordRange): Promise<DoseRecord[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetDoseRecords(range);
  }
  const query = new URLSearchParams({
    recordId: String(range.recordId),
    from: range.from,
    to: range.to,
  });
  return http.get<DoseRecord[]>(`/v1/medications/doses?${query.toString()}`);
}
