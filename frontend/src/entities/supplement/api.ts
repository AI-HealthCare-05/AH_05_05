import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockAddSupplement,
  mockSearchSupplementProducts,
  mockSupplements,
} from './api.mock';
import type {
  AddSupplementPayload,
  SearchSupplementProductsParams,
  Supplement,
  SupplementSearchPage,
} from './types';

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
