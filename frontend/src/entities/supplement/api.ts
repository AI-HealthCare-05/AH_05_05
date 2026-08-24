import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockAddSupplement, mockSupplements } from './api.mock';
import type { AddSupplementPayload, Supplement } from './types';

export async function getSupplements(): Promise<Supplement[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSupplements();
  }
  return http.get<Supplement[]>('/supplements');
}

export async function addSupplement(payload: AddSupplementPayload): Promise<Supplement> {
  if (USE_MOCK) {
    await mockDelay();
    return mockAddSupplement(payload);
  }
  return http.post<Supplement>('/supplements', payload);
}
