/**
 * 복약 목업 데이터.
 *
 * 07(OCR 결과 확인) 목업은 약품명을 OCR 원문(영문)으로 두지만, 이 화면은 저장이 끝난 뒤
 * 서버가 돌려주는 값을 받는 자리라 정리된 한글 약품명을 씁니다. 명세 5-3 예시와
 * Figma `09` 프레임 둘 다 한글 표기입니다.
 *
 * times 가 빈 배열인 것은 "아직 저장한 적 없음"(최초 진입)입니다. 마이페이지에서
 * 재설정으로 들어오는 `09-B 기존 저장 시각 프리필` 은 여기에 값이 채워져 옵니다.
 */
import type { MedicationSchedule, SaveMedicationScheduleResponse } from './types';

export function mockMedicationSchedule(): MedicationSchedule {
  return {
    startPeriod: null,
    medications: [
      { medicationId: 301, name: '셀레콕시브', dose: '200mg', timesPerDay: 2, timing: '아침·저녁 식후', times: [] },
      { medicationId: 302, name: '리바록사반', dose: '10mg', timesPerDay: 1, timing: '저녁 식후', times: [] },
      { medicationId: 303, name: '아세트아미노펜', dose: '650mg', timesPerDay: null, timing: '6시간 이상 간격', times: [] },
      { medicationId: 304, name: '파모티딘', dose: '20mg', timesPerDay: 2, timing: '아침·저녁 식후', times: [] },
    ],
  };
}

export function mockSaveMedicationSchedule(): SaveMedicationScheduleResponse {
  return { saved: true };
}
