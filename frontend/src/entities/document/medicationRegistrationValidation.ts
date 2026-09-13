import type { EditableOcrMedication } from './types';

export type ConfirmedOcrMedication = EditableOcrMedication & {
  days: number;
  timesPerDay: number | null;
};

/** OCR 원본은 빈 값을 허용하지만, 사용자가 확정하는 복약 정보는 완결되어야 합니다. */
export function isValidMedicationRegistrationDays(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 365;
}

/** null은 사용자가 명시적으로 고른 '필요 시'이며, undefined는 미추출 상태입니다. */
export function isValidMedicationRegistrationFrequency(
  value: unknown,
): value is number | null {
  return value === null ||
    (typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 6);
}

export function isReadyForMedicationRegistration(
  medication: EditableOcrMedication,
): medication is ConfirmedOcrMedication {
  return Boolean(medication.name.trim()) &&
    isValidMedicationRegistrationDays(medication.days) &&
    isValidMedicationRegistrationFrequency(medication.timesPerDay);
}
