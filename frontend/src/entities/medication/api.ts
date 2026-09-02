/**
 * 복약 API. 화면은 이 함수들만 부릅니다.
 * 목업 ↔ 실서버 전환 규칙은 entities/document/api.ts 와 같습니다.
 */
import { ApiError, http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockCancelMedication,
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
  MedicationOverviewRange,
  MedicationSchedule,
  SaveMedicationSchedulePayload,
  SaveMedicationScheduleResponse,
  SaveDoseTakenPayload,
} from './types';

type MedicationOverviewResponse =
  | MedicationOverview
  | MedicationOverview[]
  | { episodes: MedicationOverview[] };

export async function getMedicationOverviews(
  range: MedicationOverviewRange = {},
): Promise<MedicationOverview[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockMedicationOverviews(range);
  }
  const query = new URLSearchParams();
  if (range.from) query.set('from', range.from);
  if (range.to) query.set('to', range.to);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : '';
  try {
    const response = await http.get<MedicationOverviewResponse>(`/v1/medications${suffix}`);
    if (Array.isArray(response)) return response;
    if ('episodes' in response) return response.episodes;
    return [response];
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return [];
    throw error;
  }
}

export async function getMedicationDocumentImageUrl(documentImageUrl: string): Promise<string> {
  if (USE_MOCK) return documentImageUrl;
  const apiPath = documentImageUrl.startsWith('/api')
    ? documentImageUrl.slice('/api'.length)
    : documentImageUrl;
  return URL.createObjectURL(await http.getBlob(apiPath));
}

export function releaseMedicationDocumentImageUrl(url: string): void {
  if (url.startsWith('blob:')) URL.revokeObjectURL(url);
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
    from: range.from,
    to: range.to,
  });
  return http.get<DoseRecord[]>(`/v1/medications/doses?${query.toString()}`);
}

export async function cancelMedication(recordId: number): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    mockCancelMedication(recordId);
    return;
  }
  await http.delete<void>(`/v1/medications/${recordId}`);
}
