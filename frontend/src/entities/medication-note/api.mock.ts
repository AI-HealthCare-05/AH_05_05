import { restoreAccountPrincipal } from '@/shared/api/client';
import { mockMedicationOverviews } from '@/entities/medication/api.mock';
import type {
  CreateMedicationNotePayload,
  MedicationNote,
  MedicationNoteMedication,
  MedicationNoteListParams,
  MedicationNotePage,
  UpdateMedicationNotePayload,
} from './types';

const SESSION_KEY = 'rxvita.mock.medication-notes';
const FAIL_CREATE_ONCE_KEY = `${SESSION_KEY}:fail-create-once`;
const memoryNotesByScope = new Map<string, MedicationNote[]>();

function resolveScope(): string {
  return restoreAccountPrincipal()?.trim().toLowerCase() || 'anonymous';
}

function storageKey(): string {
  return `${SESSION_KEY}:${encodeURIComponent(resolveScope())}`;
}

function clone(note: MedicationNote): MedicationNote {
  return {
    ...note,
    availableMedications: note.availableMedications.map((medication) => ({ ...medication })),
    medication: note.medication ? { ...note.medication } : null,
  };
}

function readNotes(): MedicationNote[] {
  const scope = resolveScope();
  try {
    const raw = sessionStorage.getItem(storageKey());
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const notes = parsed.filter(isMedicationNote).map(clone);
        memoryNotesByScope.set(scope, notes);
        return notes;
      }
    }
  } catch {
    // session storage is optional for the mock adapter.
  }
  return (memoryNotesByScope.get(scope) ?? []).map(clone);
}

function writeNotes(notes: MedicationNote[]): void {
  const scope = resolveScope();
  const next = notes.map(clone);
  memoryNotesByScope.set(scope, next);
  try {
    sessionStorage.setItem(storageKey(), JSON.stringify(next));
  } catch {
    // Keep the in-memory mock usable when storage is disabled.
  }
}

function consumeCreateFailure(): boolean {
  try {
    if (sessionStorage.getItem(FAIL_CREATE_ONCE_KEY) !== '1') return false;
    sessionStorage.removeItem(FAIL_CREATE_ONCE_KEY);
    return true;
  } catch {
    return false;
  }
}

function isMedicationNote(value: unknown): value is MedicationNote {
  if (!value || typeof value !== 'object') return false;
  const note = value as Partial<MedicationNote>;
  return (
    typeof note.id === 'number' &&
    typeof note.careEpisodeId === 'number' &&
    typeof note.careEpisodeTitle === 'string' &&
    (typeof note.careEpisodeAlias === 'string' || note.careEpisodeAlias === null) &&
    (typeof note.careEpisodeStartDate === 'string' || note.careEpisodeStartDate === null) &&
    typeof note.careEpisodeStatus === 'string' &&
    Array.isArray(note.availableMedications) &&
    (typeof note.medicationId === 'number' || note.medicationId === null) &&
    (typeof note.medication === 'object' || note.medication === null) &&
    typeof note.dosedAt === 'string' &&
    typeof note.body === 'string' &&
    typeof note.createdAt === 'string' &&
    (typeof note.updatedAt === 'string' || note.updatedAt === null)
  );
}

function episodeMetadata(careEpisodeId: number): {
  title: string;
  alias: string | null;
  startDate: string | null;
  status: string;
  medications: MedicationNoteMedication[];
} {
  const overview = mockMedicationOverviews().find((item) => item.recordId === careEpisodeId);
  const medications = overview?.medications.map((medication) => ({
    id: medication.medicationId,
    name: medication.name,
    dose: medication.dose || null,
  })) ?? [];
  return {
    title: overview ? `${overview.start.date} 조제약 복약안내` : `${careEpisodeId} 처방`,
    alias: overview?.alias ?? null,
    startDate: overview?.start.date ?? null,
    status: overview?.isFinished ? 'COMPLETED' : 'ACTIVE',
    medications,
  };
}

function hydrateNote(note: MedicationNote): MedicationNote {
  const metadata = episodeMetadata(note.careEpisodeId);
  const hasCurrentEpisode = metadata.startDate !== null;
  const availableMedications = hasCurrentEpisode
    ? metadata.medications
    : note.availableMedications.length > 0
      ? note.availableMedications
      : metadata.medications;
  const medication = note.medicationId === null
    ? null
    : availableMedications.find((item) => item.id === note.medicationId) ?? null;
  return {
    ...clone(note),
    careEpisodeTitle: hasCurrentEpisode ? metadata.title : note.careEpisodeTitle || metadata.title,
    careEpisodeAlias: hasCurrentEpisode ? metadata.alias : note.careEpisodeAlias,
    careEpisodeStartDate: hasCurrentEpisode ? metadata.startDate : note.careEpisodeStartDate,
    careEpisodeStatus: hasCurrentEpisode ? metadata.status : note.careEpisodeStatus || metadata.status,
    availableMedications,
    medication,
  };
}

function newId(): number {
  return Date.now() * 1000 + Math.floor(Math.random() * 1000);
}

export function mockListMedicationNotes({ episodeId, limit = 20, cursor }: MedicationNoteListParams = {}): MedicationNotePage {
  const filtered = readNotes()
    .filter((note) => episodeId === undefined || note.careEpisodeId === episodeId)
    .sort((a, b) => b.dosedAt.localeCompare(a.dosedAt) || b.id - a.id);
  const start = cursor && /^\d+$/.test(cursor) ? Number(cursor) : 0;
  const items = filtered.slice(start, start + limit);
  const nextCursor = start + limit < filtered.length ? String(start + limit) : null;
  return {
    items: items.map(hydrateNote),
    total: filtered.length,
    nextCursor,
  };
}

export function mockGetMedicationNote(noteId: number | string): MedicationNote | null {
  const id = Number(noteId);
  const note = readNotes().find((item) => item.id === id);
  return note ? hydrateNote(note) : null;
}

export function mockCreateMedicationNote(payload: CreateMedicationNotePayload): MedicationNote {
  if (consumeCreateFailure()) throw new Error('잠시 후 다시 시도해주세요.');
  const now = new Date().toISOString();
  const metadata = episodeMetadata(payload.careEpisodeId);
  const medication = payload.medicationId === undefined || payload.medicationId === null
    ? null
    : metadata.medications.find((item) => item.id === payload.medicationId) ?? null;
  const note: MedicationNote = {
    id: newId(),
    careEpisodeId: payload.careEpisodeId,
    careEpisodeTitle: metadata.title,
    careEpisodeAlias: metadata.alias,
    careEpisodeStartDate: metadata.startDate,
    careEpisodeStatus: metadata.status,
    availableMedications: metadata.medications,
    medicationId: payload.medicationId ?? null,
    medication,
    dosedAt: payload.dosedAt,
    body: payload.body.trim(),
    createdAt: now,
    updatedAt: null,
  };
  writeNotes([...readNotes(), note]);
  return hydrateNote(note);
}

export function mockUpdateMedicationNote(
  noteId: number | string,
  payload: UpdateMedicationNotePayload,
): MedicationNote {
  const id = Number(noteId);
  const notes = readNotes();
  const index = notes.findIndex((note) => note.id === id);
  if (index < 0) throw new Error('복약 메모를 찾지 못했어요.');
  const current = notes[index];
  const next: MedicationNote = {
    ...current,
    ...(Object.prototype.hasOwnProperty.call(payload, 'medicationId')
      ? { medicationId: payload.medicationId ?? null }
      : {}),
    ...(payload.dosedAt !== undefined ? { dosedAt: payload.dosedAt } : {}),
    ...(payload.body !== undefined ? { body: payload.body.trim() } : {}),
    updatedAt: new Date().toISOString(),
  };
  notes[index] = next;
  writeNotes(notes);
  return hydrateNote(next);
}

export function mockDeleteMedicationNote(noteId: number | string): void {
  const id = Number(noteId);
  const notes = readNotes();
  if (!notes.some((note) => note.id === id)) throw new Error('복약 메모를 찾지 못했어요.');
  writeNotes(notes.filter((note) => note.id !== id));
}
