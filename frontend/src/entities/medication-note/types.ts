export interface MedicationNote {
  id: number;
  careEpisodeId: number;
  careEpisodeAlias: string | null;
  careEpisodeStartDate: string | null;
  careEpisodeStatus: MedicationNoteEpisodeStatus;
  availableMedications: MedicationNoteMedication[];
  medicationId: number | null;
  medication: MedicationNoteMedication | null;
  /** 사용자가 지정한 복용 시각(ISO 문자열). 작성 시각과 다를 수 있습니다. */
  dosedAt: string;
  body: string;
  createdAt: string;
  updatedAt: string | null;
}

export interface MedicationNoteMedication {
  id: number;
  name: string;
  dose: string | null;
}

export interface MedicationNotePage {
  items: MedicationNote[];
  total: number;
  nextCursor: string | null;
}

export type MedicationNoteEpisodeStatus = 'ACTIVE' | 'COMPLETED' | 'CANCELLED';

export interface MedicationNoteEpisode {
  careEpisodeId: number;
  alias: string | null;
  startDate: string | null;
  status: MedicationNoteEpisodeStatus;
  representativeMedicationName?: string | null;
  medicationCount?: number;
  /** includeWithoutNotes=true일 때만 내려오는 사용자 소유 메모 수 */
  noteCount?: number;
  /** includeWithoutNotes=true일 때만 내려오는 작성 대상 약 목록 */
  medications?: MedicationNoteMedication[];
}

export interface MedicationNoteListParams {
  episodeId?: number;
  limit?: number;
  cursor?: string;
}

export interface CreateMedicationNotePayload {
  careEpisodeId: number;
  medicationId?: number | null;
  dosedAt: string;
  body: string;
}

export interface UpdateMedicationNotePayload {
  medicationId?: number | null;
  dosedAt?: string;
  body?: string;
}
