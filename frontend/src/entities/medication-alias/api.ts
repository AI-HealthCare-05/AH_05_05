import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockUpdateEpisodeAlias } from './api.mock';

export async function updateEpisodeAlias(recordId: number, alias: string | null): Promise<void> {
  const normalized = alias?.trim() || null;
  if (USE_MOCK) {
    await mockDelay();
    mockUpdateEpisodeAlias(recordId, normalized);
    return;
  }
  await http.patch<void>(`/v1/med/episodes/${recordId}/alias`, { alias: normalized });
}
