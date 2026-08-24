// REQ-CARE-003 / 통합 슬롯 재설계 (2026-08-14 기획 결정)
//
// 시각은 약마다 두지 않고 사용자의 시간대 4개에만 둡니다. 약은 "어느 시간대에 먹는지"만
// 가집니다. 약을 같이 먹는 게 현실이므로 시각을 약마다 따로 둘 이유가 없습니다.
// 이전 모델(약별 times: string[])은 폐기됐습니다.
//
// 노션 API 명세 5-3 교체가 필요합니다(전달_통합슬롯_계약변경.md 참고).

/** 통합 시간대. 4개로 확정(2026-08-14 기획 결정). */
export type MealSlot = 'morning' | 'lunch' | 'evening' | 'bedtime';

/**
 * 복용을 시작한 시점. 전체 약물 공통 1개.
 *
 * 시간대만으로는 "며칠부터"를 알 수 없어 날짜를 함께 받습니다("8월 14일 점심약부터").
 * 사용자에게는 과거 시점을 묻는 질문("처음 약을 언제부터 드셨나요?")이라 날짜가
 * 오늘보다 이전일 수 있습니다.
 *
 * 이전 모델(`startPeriod: MealSlot` 하나)은 폐기됐습니다 — 노션 명세 5-3 교체 필요.
 */
export interface MedicationStartPoint {
  /** YYYY-MM-DD */
  date: string;
  slot: MealSlot;
}

/** 사용자가 정한 시간대별 시각. 30분 단위(분은 00 또는 30)만 허용합니다. */
export interface MealTimes {
  morning: string;
  lunch: string;
  evening: string;
  bedtime: string;
}

export interface ScheduleMedication {
  medicationId: number;
  name: string;
  dose: string;
  /** null이면 "필요 시 복용" — 시간대를 지정하지 않고 알림 대상도 아닙니다. */
  timesPerDay: number | null;
  /** OCR에서 온 복용 시점 문구. 예: "아침·저녁 식후", "취침 전", "필요 시" */
  timing: string;
  /** 저장된 시간대. 최초 진입에는 빈 배열 → 프론트가 자동 배정합니다. */
  slots: MealSlot[];
}

export interface MedicationSchedule {
  /** 최초 진입에는 null → 사용자가 날짜·시간대를 직접 고릅니다. */
  start: MedicationStartPoint | null;
  /** 최초 진입에는 null → 프론트가 DEFAULT_MEAL_TIMES 로 채웁니다. */
  mealTimes: MealTimes | null;
  medications: ScheduleMedication[];
}

export interface SaveMedicationSchedulePayload {
  recordId: number;
  start: MedicationStartPoint;
  mealTimes: MealTimes;
  /** 필요 시 복용 약(timesPerDay === null)은 제외하고 보냅니다. */
  medications: Array<{ medicationId: number; slots: MealSlot[] }>;
}

export interface SaveMedicationScheduleResponse {
  saved: boolean;
}

export interface MedicationOverviewItem {
  medicationId: number;
  name: string;
  dose: string;
  daysRemaining: number | null;
  slots: MealSlot[];
  asNeeded: boolean;
  untilComplete?: boolean;
}

export interface MedicationOverview {
  recordId: number;
  start: MedicationStartPoint;
  daysRemaining: number;
  mealTimes: MealTimes;
  medications: MedicationOverviewItem[];
}
