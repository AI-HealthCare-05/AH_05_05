import { getAuthGeneration, http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockGetSupplementDoses, mockSaveSupplementDose } from './dose.api.mock';
import type { SupplementDoseRecord } from './types';

export async function getSupplementDoses(date: string): Promise<SupplementDoseRecord[]> {
  const generation = getAuthGeneration();
  if (USE_MOCK) {
    await mockDelay();
    if (generation !== getAuthGeneration()) throw new Error('로그인 상태가 바뀌었어요.');
    return mockGetSupplementDoses(date);
  }
  const result = await http.get<SupplementDoseRecord[]>(`/v1/med/supplement-doses?${new URLSearchParams({ date })}`);
  if (generation !== getAuthGeneration()) throw new Error('로그인 상태가 바뀌었어요.');
  return result;
}

export async function saveSupplementDose(payload: SupplementDoseRecord): Promise<SupplementDoseRecord> {
  const generation = getAuthGeneration();
  if (USE_MOCK) {
    await mockDelay();
    if (generation !== getAuthGeneration()) throw new Error('로그인 상태가 바뀌었어요.');
    return mockSaveSupplementDose(payload);
  }
  const result = await http.put<SupplementDoseRecord>('/v1/med/supplement-doses', payload);
  if (generation !== getAuthGeneration()) throw new Error('로그인 상태가 바뀌었어요.');
  return result;
}
