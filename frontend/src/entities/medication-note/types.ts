export interface MedicationNote {
  id: number;
  careEpisodeId: number;
  medicationId: number | null;
  /** 사용자가 지정한 복용 시각(ISO 문자열). 작성 시각과 다를 수 있습니다. */
  dosedAt: string;
  body: string;
  createdAt: string;
  updatedAt: string | null;
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
