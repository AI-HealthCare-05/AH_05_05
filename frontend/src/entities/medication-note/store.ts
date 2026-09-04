import { restoreAccountPrincipal } from '@/shared/api/client';
import type { MedicationNote, MedicationNoteDraft } from './types';

const STORAGE_KEY_PREFIX = 'rxvita.medication-notes';

/**
 * 메모는 서버 계약이 없는 동안만 사용하는 로컬 어댑터입니다.
 *
 * scope를 화면에서 전달하면 SessionContext의 principalKey와 저장 범위를 정확히 맞출 수
 * 있고, 직접 호출하는 코드에는 현재 로그인 주체를 기본값으로 사용합니다. seedNotes는
 * 개발용 화면/테스트가 명시적으로 넘길 때만 쓰이며, 운영 첫 상태는 항상 빈 목록입니다.
 */
export interface MedicationNoteStoreOptions {
  scope?: string | null;
  seedNotes?: readonly MedicationNote[];
}

const memoryNotesByScope = new Map<string, MedicationNote[]>();

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function resolveScope(scope?: string | null): string {
  const principal = scope ?? restoreAccountPrincipal();
  return principal?.trim().toLowerCase() || 'anonymous';
}

function storageKey(scope?: string | null): string {
  return `${STORAGE_KEY_PREFIX}:${encodeURIComponent(resolveScope(scope))}`;
}

function clone(notes: readonly MedicationNote[]): MedicationNote[] {
  return notes.map((note) => ({ ...note }));
}

function readNotes(options: MedicationNoteStoreOptions = {}): MedicationNote[] {
  const scope = resolveScope(options.scope);
  const key = storageKey(scope);
  if (!canUseStorage()) {
    return clone(memoryNotesByScope.get(scope) ?? options.seedNotes ?? []);
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      const initial = clone(options.seedNotes ?? []);
      memoryNotesByScope.set(scope, initial);
      window.localStorage.setItem(key, JSON.stringify(initial));
      return clone(initial);
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return clone(memoryNotesByScope.get(scope) ?? []);
    const notes = parsed.filter(isMedicationNote).map((note) => ({ ...note }));
    memoryNotesByScope.set(scope, notes);
    return clone(notes);
  } catch {
    return clone(memoryNotesByScope.get(scope) ?? options.seedNotes ?? []);
  }
}

function writeNotes(notes: MedicationNote[], options: MedicationNoteStoreOptions = {}): void {
  const scope = resolveScope(options.scope);
  const next = clone(notes);
  memoryNotesByScope.set(scope, next);
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(storageKey(scope), JSON.stringify(next));
  } catch {
    // 사생활 보호 설정 등으로 storage가 막힌 경우 현재 탭 메모리로 계속 동작합니다.
  }
}

function isMedicationNote(value: unknown): value is MedicationNote {
  if (!value || typeof value !== 'object') return false;
  const note = value as Partial<MedicationNote>;
  return (
    typeof note.id === 'string' &&
    typeof note.recordId === 'number' &&
    typeof note.medicationId === 'number' &&
    typeof note.prescriptionLabel === 'string' &&
    typeof note.medicineLabel === 'string' &&
    typeof note.takenAt === 'string' &&
    typeof note.experience === 'string'
  );
}

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `note-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function listMedicationNotes(options: MedicationNoteStoreOptions = {}): MedicationNote[] {
  return readNotes(options).sort((a, b) => b.takenAt.localeCompare(a.takenAt));
}

export function getMedicationNote(
  noteId: string,
  options: MedicationNoteStoreOptions = {},
): MedicationNote | null {
  return readNotes(options).find((note) => note.id === noteId) ?? null;
}

export function createMedicationNote(
  draft: MedicationNoteDraft,
  options: MedicationNoteStoreOptions = {},
): MedicationNote {
  const note: MedicationNote = {
    id: newId(),
    recordId: draft.recordId,
    medicationId: draft.medicationId,
    prescriptionLabel: draft.prescriptionLabel ?? '선택한 처방',
    medicineLabel: draft.medicineLabel ?? '선택한 약',
    takenAt: draft.takenAt,
    experience: draft.experience,
  };
  writeNotes([...readNotes(options), note], options);
  return { ...note };
}

export function updateMedicationNote(
  noteId: string,
  draft: MedicationNoteDraft,
  options: MedicationNoteStoreOptions = {},
): MedicationNote | null {
  const notes = readNotes(options);
  const index = notes.findIndex((note) => note.id === noteId);
  if (index < 0) return null;
  const next: MedicationNote = {
    ...notes[index],
    ...draft,
    prescriptionLabel: draft.prescriptionLabel ?? notes[index].prescriptionLabel,
    medicineLabel: draft.medicineLabel ?? notes[index].medicineLabel,
  };
  notes[index] = next;
  writeNotes(notes, options);
  return { ...next };
}

export function deleteMedicationNote(
  noteId: string,
  options: MedicationNoteStoreOptions = {},
): boolean {
  const notes = readNotes(options);
  const next = notes.filter((note) => note.id !== noteId);
  if (next.length === notes.length) return false;
  writeNotes(next, options);
  return true;
}
