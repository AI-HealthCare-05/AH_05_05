/**
 * 복약 메모는 현재 서버 계약이 없어, 화면에서만 사용하는 작은 로컬 모델입니다.
 * 서버 URL이나 임의의 HTTP 엔드포인트를 만들지 않고 localStorage 어댑터로 보관합니다.
 */
export interface MedicationNote {
  id: string;
  recordId: number;
  medicationId: number;
  /** 작성 당시 선택한 처방/약 이름을 보존해 목록을 바로 그릴 수 있게 합니다. */
  prescriptionLabel: string;
  medicineLabel: string;
  takenAt: string;
  experience: string;
}

export type MedicationNoteDraft = Omit<
  MedicationNote,
  'id' | 'prescriptionLabel' | 'medicineLabel'
> & {
  prescriptionLabel?: string;
  medicineLabel?: string;
};
