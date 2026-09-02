import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockCreateFollowUpVisit,
  mockDeleteFollowUpVisit,
  mockListFollowUpVisits,
  mockUpdateFollowUpVisit,
} from './api.mock';
import type {
  FollowUpVisit,
  FollowUpVisitInput,
  FollowUpVisitListParams,
} from './types';

interface FollowUpVisitApiResponse {
  id: number;
  user_id: number;
  visit_date: string;
  visit_time: string | null;
  hospital: string | null;
  created_at: string;
  updated_at: string | null;
}

interface FollowUpVisitListApiResponse {
  items: FollowUpVisitApiResponse[];
  total: number;
  offset: number;
  limit: number;
}

function mapFollowUpVisit(response: FollowUpVisitApiResponse): FollowUpVisit {
  return {
    id: response.id,
    visitDate: response.visit_date,
    visitTime: response.visit_time?.slice(0, 5) ?? null,
    hospital: response.hospital,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  };
}

function serializeFollowUpVisit(input: FollowUpVisitInput) {
  return {
    visit_date: input.visitDate,
    visit_time: input.visitTime,
    hospital: input.hospital,
  };
}

export async function listFollowUpVisits(
  params?: FollowUpVisitListParams,
): Promise<FollowUpVisit[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockListFollowUpVisits(params);
  }
  const query = new URLSearchParams({ offset: '0', limit: '100' });
  if (params?.startDate) query.set('start_date', params.startDate);
  if (params?.endDate) query.set('end_date', params.endDate);
  const response = await http.get<FollowUpVisitListApiResponse>(
    `/v1/user/follow-up-visits?${query.toString()}`,
  );
  return response.items.map(mapFollowUpVisit);
}

export async function createFollowUpVisit(input: FollowUpVisitInput): Promise<FollowUpVisit> {
  if (USE_MOCK) {
    await mockDelay();
    return mockCreateFollowUpVisit(input);
  }
  return mapFollowUpVisit(
    await http.post<FollowUpVisitApiResponse>(
      '/v1/user/follow-up-visits',
      serializeFollowUpVisit(input),
    ),
  );
}

export async function updateFollowUpVisit(
  visitId: number,
  input: FollowUpVisitInput,
): Promise<FollowUpVisit> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateFollowUpVisit(visitId, input);
  }
  return mapFollowUpVisit(
    await http.patch<FollowUpVisitApiResponse>(
      `/v1/user/follow-up-visits/${visitId}`,
      serializeFollowUpVisit(input),
    ),
  );
}

export async function deleteFollowUpVisit(visitId: number): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    mockDeleteFollowUpVisit(visitId);
    return;
  }
  await http.delete<void>(`/v1/user/follow-up-visits/${visitId}`);
}
