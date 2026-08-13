// REQ-CARE-003 / 노션 API 명세 5-3 기준 타입

/** 복용을 시작한 시점. 전체 약물 공통 1개(스펙 5-3). */
export type StartPeriod = 'morning' | 'lunch' | 'evening';

export interface ScheduleMedication {
  medicationId: number;
  name: string;
  dose: string;
  /** null이면 "필요 시 복용" — 시각을 지정하지 않습니다(스펙 5-3). */
  timesPerDay: number | null;
  /** OCR에서 온 복용 시점 문구. 예: "아침·저녁 식후", "필요 시" */
  timing: string;
  /** 저장된 복용 시각. 최초 진입에는 빈 배열, 재설정 진입에는 저장값이 채워져 옵니다. */
  times: string[];
}

export interface MedicationSchedule {
  /** 최초 진입에는 null, 재설정 진입에는 저장값. */
  startPeriod: StartPeriod | null;
  medications: ScheduleMedication[];
}

export interface SaveMedicationSchedulePayload {
  recordId: number;
  startPeriod: StartPeriod;
  /** times는 30분 단위(분은 00 또는 30)만 보냅니다. 필요 시 복용 약은 제외합니다. */
  medications: Array<{ medicationId: number; times: string[] }>;
}

export interface SaveMedicationScheduleResponse {
  saved: boolean;
}
