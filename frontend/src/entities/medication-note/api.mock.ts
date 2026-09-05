import { restoreAccountPrincipal } from '@/shared/api/client';
import type {
  CreateMedicationNotePayload,
  MedicationNote,
  MedicationNoteListParams,
  UpdateMedicationNotePayload,
} from './types';

const SESSION_KEY = 'rxvita.mock.medication-notes';
const memoryNotesByScope = new Map<string, MedicationNote[]>();

function resolveScope(): string {
  return restoreAccountPrincipal()?.trim().toLowerCase() || 'anonymous';
}

function storageKey(): string {
  return `${SESSION_KEY}:${encodeURIComponent(resolveScope())}`;
}

function clone(note: MedicationNote): MedicationNote {
  return { ...note };
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

function isMedicationNote(value: unknown): value is MedicationNote {
  if (!value || typeof value !== 'object') return false;
  const note = value as Partial<MedicationNote>;
  return (
    typeof note.id === 'number' &&
    typeof note.careEpisodeId === 'number' &&
    (typeof note.medicationId === 'number' || note.medicationId === null) &&
    typeof note.dosedAt === 'string' &&
    typeof note.body === 'string' &&
    typeof note.createdAt === 'string' &&
    (typeof note.updatedAt === 'string' || note.updatedAt === null)
  );
}

function newId(): number {
  return Date.now() * 1000 + Math.floor(Math.random() * 1000);
}

export function mockListMedicationNotes({ episodeId }: MedicationNoteListParams = {}): MedicationNote[] {
  return readNotes()
    .filter((note) => episodeId === undefined || note.careEpisodeId === episodeId)
    .sort((a, b) => b.dosedAt.localeCompare(a.dosedAt) || b.id - a.id)
    .map(clone);
}

export function mockGetMedicationNote(noteId: number | string): MedicationNote | null {
  const id = Number(noteId);
  return readNotes().find((note) => note.id === id) ?? null;
}

export function mockCreateMedicationNote(payload: CreateMedicationNotePayload): MedicationNote {
  const now = new Date().toISOString();
  const note: MedicationNote = {
    id: newId(),
    careEpisodeId: payload.careEpisodeId,
    medicationId: payload.medicationId ?? null,
    dosedAt: payload.dosedAt,
    body: payload.body.trim(),
    createdAt: now,
    updatedAt: null,
  };
  writeNotes([...readNotes(), note]);
  return clone(note);
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
  return clone(next);
}

export function mockDeleteMedicationNote(noteId: number | string): void {
  const id = Number(noteId);
  const notes = readNotes();
  if (!notes.some((note) => note.id === id)) throw new Error('복약 메모를 찾지 못했어요.');
  writeNotes(notes.filter((note) => note.id !== id));
}
