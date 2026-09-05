import { ApiError, http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockCreateMedicationNote,
  mockDeleteMedicationNote,
  mockGetMedicationNote,
  mockListMedicationNotes,
  mockUpdateMedicationNote,
} from './api.mock';
import type {
  CreateMedicationNotePayload,
  MedicationNote,
  MedicationNoteListParams,
  UpdateMedicationNotePayload,
} from './types';

type MedicationNoteListResponse = MedicationNote[] | { items: MedicationNote[] };

function notePath(noteId: number | string): string {
  return `/v1/med/notes/${encodeURIComponent(String(noteId))}`;
}

export async function listMedicationNotes(
  params: MedicationNoteListParams = {},
): Promise<MedicationNote[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockListMedicationNotes(params);
  }
  const query = new URLSearchParams();
  if (params.episodeId !== undefined) query.set('episodeId', String(params.episodeId));
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.cursor) query.set('cursor', params.cursor);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  const response = await http.get<MedicationNoteListResponse>(`/v1/med/notes${suffix}`);
  return Array.isArray(response) ? response : response.items;
}

export async function getMedicationNote(noteId: number | string): Promise<MedicationNote | null> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetMedicationNote(noteId);
  }
  try {
    return await http.get<MedicationNote>(notePath(noteId));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function createMedicationNote(
  payload: CreateMedicationNotePayload,
): Promise<MedicationNote> {
  if (USE_MOCK) {
    await mockDelay();
    return mockCreateMedicationNote(payload);
  }
  return http.post<MedicationNote>('/v1/med/notes', payload);
}

export async function updateMedicationNote(
  noteId: number | string,
  payload: UpdateMedicationNotePayload,
): Promise<MedicationNote> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateMedicationNote(noteId, payload);
  }
  return http.patch<MedicationNote>(notePath(noteId), payload);
}

export async function deleteMedicationNote(noteId: number | string): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    mockDeleteMedicationNote(noteId);
    return;
  }
  await http.delete<void>(notePath(noteId));
}
