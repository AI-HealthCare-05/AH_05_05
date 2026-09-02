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
import type {
  DoseRecord,
  DoseRecordRange,
  MedicationOverview,
  MedicationOverviewRange,
  MedicationSchedule,
  SaveDoseTakenPayload,
  SaveMedicationSchedulePayload,
  SaveMedicationScheduleResponse,
} from './types';

let hasRegisteredMedication = true;
const cancelledMedicationRecordIds = new Set<number>();
let doseRecords: DoseRecord[] = [
  { date: '2026-08-22', slot: 'morning', taken: true },
  { date: '2026-08-22', slot: 'evening', taken: true },
  { date: '2026-08-23', slot: 'morning', taken: true },
  { date: '2026-08-23', slot: 'evening', taken: true },
  { date: '2026-08-24', slot: 'morning', taken: true },
];

export function resetMockMedicationForNewAccount(): void {
  hasRegisteredMedication = false;
  cancelledMedicationRecordIds.clear();
  doseRecords = [];
}

function primaryMedicationOverview(): MedicationOverview {
  const startDate = '2026-08-22';
  const medications = hasRegisteredMedication ? [
    { medicationId: 301, name: '셀레콕시브', dose: '200mg', days: 7, daysRemaining: 3, slots: ['morning', 'evening'] as const, asNeeded: false },
    { medicationId: 302, name: '리바록사반', dose: '10mg', days: 10, daysRemaining: 10, slots: ['evening'] as const, asNeeded: false, untilComplete: true },
    { medicationId: 304, name: '파모티딘', dose: '20mg', days: 7, daysRemaining: 3, slots: ['morning', 'evening'] as const, asNeeded: false },
    { medicationId: 303, name: '아세트아미노펜', dose: '650mg', days: 7, daysRemaining: null, slots: [] as const, asNeeded: true },
  ] : [];
  return {
    recordId: 12,
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: startDate, slot: 'morning' },
    endDate: medicationEndDate(startDate, medications),
    daysRemaining: 3,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: medications.map((medication) => ({
      ...medication,
      slots: [...medication.slots],
    })),
  };
}

function secondaryMedicationOverview(): MedicationOverview {
  const startDate = '2026-08-24';
  const medications = [
    {
      medicationId: 501,
      name: '아목시실린',
      dose: '500mg',
      days: 5,
      daysRemaining: 3,
      slots: ['morning', 'lunch', 'evening'] as const,
      asNeeded: false,
    },
  ];
  return {
    recordId: 24,
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: startDate, slot: 'morning' },
    endDate: medicationEndDate(startDate, medications),
    daysRemaining: 3,
    isFinished: true,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: medications.map((medication) => ({
      ...medication,
      slots: [...medication.slots],
    })),
  };
}

export function mockMedicationOverviews(range: MedicationOverviewRange = {}): MedicationOverview[] {
  if (!hasRegisteredMedication) return [];
  return [primaryMedicationOverview(), secondaryMedicationOverview()].filter(
    (overview) =>
      !cancelledMedicationRecordIds.has(overview.recordId) &&
      (!range.from || overview.start.date >= range.from) &&
      (!range.to || overview.start.date <= range.to),
  );
}

export function mockMedicationOverview(recordId = 12): MedicationOverview {
  const overview = mockMedicationOverviews().find((item) => item.recordId === recordId);
  if (overview) return overview;
  throw new Error('복약 기록을 찾지 못했어요.');
}

function medicationEndDate(
  startDate: string,
  medications: Array<{ days: number }>,
): string {
  const longestDays = Math.max(1, ...medications.map((medication) => medication.days));
  const date = new Date(`${startDate}T00:00:00`);
  date.setDate(date.getDate() + longestDays - 1);
  return localISODate(date);
}

function localISODate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
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

export function mockSaveMedicationSchedule(
  _payload: SaveMedicationSchedulePayload,
): SaveMedicationScheduleResponse {
  hasRegisteredMedication = true;
  return { saved: true };
}

export function mockSaveDoseTaken(payload: SaveDoseTakenPayload): DoseRecord {
  doseRecords = doseRecords.filter(
    (record) => record.date !== payload.date || record.slot !== payload.slot,
  );
  if (payload.taken) doseRecords.push({ ...payload });
  return { ...payload };
}

export function mockGetDoseRecords({ from, to }: DoseRecordRange): DoseRecord[] {
  return doseRecords
    .filter(
      (record) =>
        record.taken &&
        record.date >= from &&
        record.date <= to,
    )
    .map((record) => ({ ...record }));
}

export function mockCancelMedication(recordId: number): void {
  cancelledMedicationRecordIds.add(recordId);
}
