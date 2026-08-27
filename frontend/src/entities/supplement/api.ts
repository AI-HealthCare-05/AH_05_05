import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockAddSupplement,
  mockSearchSupplementProducts,
  mockStopSupplement,
  mockSupplementRanking,
  mockSupplements,
  mockUpdateSupplement,
} from './api.mock';
import type {
  AddSupplementPayload,
  SearchSupplementProductsParams,
  Supplement,
  SupplementRanking,
  SupplementSearchPage,
  UpdateSupplementPayload,
} from './types';

export async function getSupplements(): Promise<Supplement[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSupplements();
  }
  return http.get<Supplement[]>('/supplements');
}

export async function getSupplementRanking(limit = 5): Promise<SupplementRanking> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSupplementRanking(limit);
  }
  return http.get<SupplementRanking>(`/v1/supplements/ranking?limit=${limit}`);
}

export async function addSupplement(payload: AddSupplementPayload): Promise<Supplement> {
  if (USE_MOCK) {
    await mockDelay();
    return mockAddSupplement(payload);
  }
  return http.post<Supplement>('/supplements', payload);
}

export async function updateSupplement(
  supplementId: number,
  payload: UpdateSupplementPayload,
): Promise<Supplement> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateSupplement(supplementId, payload);
  }
  return http.patch<Supplement>(`/v1/supplements/${supplementId}`, payload);
}

export async function stopSupplement(supplementId: number): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    mockStopSupplement(supplementId);
    return;
  }
  await http.patch<void>(`/v1/supplements/${supplementId}`, { status: 'completed' });
}

export async function searchSupplementProducts(
  params: SearchSupplementProductsParams,
): Promise<SupplementSearchPage> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSearchSupplementProducts(params);
  }
  const query = new URLSearchParams({
    query: params.query,
    offset: String(params.offset ?? 0),
    limit: String(params.limit ?? 20),
  });
  return http.get<SupplementSearchPage>(`/supplements/products/search?${query.toString()}`);
}
