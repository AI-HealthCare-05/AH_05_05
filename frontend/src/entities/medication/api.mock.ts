/**
 * 복약 목업 데이터.
 *
 * 07(OCR 결과 확인) 목업은 약품명을 OCR 원문(영문)으로 두지만, 이 화면은 저장이 끝난 뒤
 * 서버가 돌려주는 값을 받는 자리라 정리된 한글 약품명을 씁니다.
 *
 * start·mealTimes 가 null, slots 가 빈 배열인 것은 "아직 저장한 적 없음"(최초 진입)입니다.
 * 마이페이지에서 재설정으로 들어오는 `09-B 기존 저장 시각 프리필` 은 여기에 값이 채워져 옵니다.
 *
 * 파모티딘은 "1일 2회 아침·저녁 식후"가 아니라 "1일 1회 취침 전"입니다. 취침 슬롯이
 * 자동 배정되는 경로를 목업에서 확인할 수 있어야 하기 때문입니다(위장약을 취침 전에
 * 주는 처방은 실제로 흔합니다).
 *
 * 이 목업의 자동 배정 기대값 — 육안 검증 기준:
 *   셀레콕시브(2회, "아침·저녁 식후")   → 아침 · 저녁   (문구에서 2개 = 횟수 일치)
 *   리바록사반(1회, "저녁 식후")        → 저녁          (문구에서 1개 = 횟수 일치)
 *   아세트아미노펜(필요 시)             → 없음, 토글 미표시
 *   파모티딘(1회, "취침 전")            → 취침 전       (문구에서 bedtime 1개 = 횟수 일치)
 * → 점심 슬롯을 쓰는 약이 하나도 없으므로 점심 행만 흐리게 표시되어야 합니다.
 */
import type { MedicationOverview, MedicationSchedule, SaveMedicationScheduleResponse } from './types';

export function mockMedicationOverview(): MedicationOverview {
  return {
    recordId: 12,
    startDate: '2026-08-22',
    daysRemaining: 3,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [
      { medicationId: 301, name: '셀레콕시브', dose: '200mg', daysRemaining: 3, slots: ['morning', 'evening'], asNeeded: false },
      { medicationId: 302, name: '리바록사반', dose: '10mg', daysRemaining: 10, slots: ['evening'], asNeeded: false, untilComplete: true },
      { medicationId: 304, name: '파모티딘', dose: '20mg', daysRemaining: 3, slots: ['morning', 'evening'], asNeeded: false },
      { medicationId: 303, name: '아세트아미노펜', dose: '650mg', daysRemaining: null, slots: [], asNeeded: true },
    ],
  };
}

export function mockMedicationSchedule(): MedicationSchedule {
  return {
    start: null,
    mealTimes: null,
    medications: [
      { medicationId: 301, name: '셀레콕시브', dose: '200mg', timesPerDay: 2, timing: '아침·저녁 식후', slots: [] },
      { medicationId: 302, name: '리바록사반', dose: '10mg', timesPerDay: 1, timing: '저녁 식후', slots: [] },
      { medicationId: 303, name: '아세트아미노펜', dose: '650mg', timesPerDay: null, timing: '6시간 이상 간격', slots: [] },
      { medicationId: 304, name: '파모티딘', dose: '20mg', timesPerDay: 1, timing: '취침 전', slots: [] },
    ],
  };
}

export function mockMedicationScheduleWithAutoAssigned(): MedicationSchedule {
  const schedule = mockMedicationSchedule();
  return {
    ...schedule,
    medications: schedule.medications.map((medication) =>
      medication.medicationId === 302
        ? { ...medication, timing: '' }
        : medication,
    ),
  };
}

export function mockSaveMedicationSchedule(): SaveMedicationScheduleResponse {
  return { saved: true };
}
