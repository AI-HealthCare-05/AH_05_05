import type { MedicationNote, MedicationNoteDraft } from './types';

const STORAGE_KEY = 'rxvita.medication-notes';

const SEED_NOTES: MedicationNote[] = [
  {
    id: 'seed-1',
    recordId: 12,
    medicationId: 301,
    prescriptionLabel: '2026년 8월 22일 처방',
    medicineLabel: '셀레콕시브 200mg',
    takenAt: '2026-09-02T08:00',
    experience: '속이 편했어요.',
  },
  {
    id: 'seed-2',
    recordId: 12,
    medicationId: 302,
    prescriptionLabel: '2026년 8월 22일 처방',
    medicineLabel: '리바록사반 10mg',
    takenAt: '2026-09-01T19:00',
    experience: '저녁에 먹으니 잊지 않았어요.',
  },
  {
    id: 'seed-3',
    recordId: 24,
    medicationId: 501,
    prescriptionLabel: '2026년 8월 24일 처방',
    medicineLabel: '아목시실린 500mg',
    takenAt: '2026-08-28T13:00',
    experience: '복용 뒤 조금 졸렸어요.',
  },
];

let memoryNotes = [...SEED_NOTES];

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function clone(notes: MedicationNote[]): MedicationNote[] {
  return notes.map((note) => ({ ...note }));
}

function readNotes(): MedicationNote[] {
  if (!canUseStorage()) return clone(memoryNotes);
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(SEED_NOTES));
      return clone(SEED_NOTES);
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return clone(memoryNotes);
    return parsed.filter(isMedicationNote).map((note) => ({ ...note }));
  } catch {
    return clone(memoryNotes);
  }
}

function writeNotes(notes: MedicationNote[]): void {
  memoryNotes = clone(notes);
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
  } catch {
    // 사생활 보호 설정 등으로 storage가 막힌 경우 메모리 어댑터로 계속 동작합니다.
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

export function listMedicationNotes(): MedicationNote[] {
  return readNotes().sort((a, b) => b.takenAt.localeCompare(a.takenAt));
}

export function getMedicationNote(noteId: string): MedicationNote | null {
  return readNotes().find((note) => note.id === noteId) ?? null;
}

export function createMedicationNote(draft: MedicationNoteDraft): MedicationNote {
  const note: MedicationNote = {
    id: newId(),
    recordId: draft.recordId,
    medicationId: draft.medicationId,
    prescriptionLabel: draft.prescriptionLabel ?? '선택한 처방',
    medicineLabel: draft.medicineLabel ?? '선택한 약',
    takenAt: draft.takenAt,
    experience: draft.experience,
  };
  writeNotes([...readNotes(), note]);
  return { ...note };
}

export function updateMedicationNote(
  noteId: string,
  draft: MedicationNoteDraft,
): MedicationNote | null {
  const notes = readNotes();
  const index = notes.findIndex((note) => note.id === noteId);
  if (index < 0) return null;
  const next: MedicationNote = {
    ...notes[index],
    ...draft,
    prescriptionLabel: draft.prescriptionLabel ?? notes[index].prescriptionLabel,
    medicineLabel: draft.medicineLabel ?? notes[index].medicineLabel,
  };
  notes[index] = next;
  writeNotes(notes);
  return { ...next };
}

export function deleteMedicationNote(noteId: string): boolean {
  const notes = readNotes();
  const next = notes.filter((note) => note.id !== noteId);
  if (next.length === notes.length) return false;
  writeNotes(next);
  return true;
}
