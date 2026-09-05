import { ApiError, restoreAccountPrincipal } from '@/shared/api/client';
import { SLOT_ORDER } from '@/shared/model/mealSlot';
import { mockOwnedSupplement, mockSupplements } from './api.mock';
import type { SupplementDoseRecord } from './types';

const memory = new Map<string, SupplementDoseRecord[]>();
function scope() {
  return `rxvita.supplement-doses:${encodeURIComponent(restoreAccountPrincipal() ?? 'guest')}`;
}
function readRecords(): SupplementDoseRecord[] {
  try {
    const raw = localStorage.getItem(scope());
    if (raw) return JSON.parse(raw) as SupplementDoseRecord[];
  } catch { /* The memory fallback remains scoped to the same account. */ }
  return memory.get(scope()) ?? [];
}
function validateDate(date: string) {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date());
  const age = (Date.parse(today) - Date.parse(date)) / 86_400_000;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isInteger(age) || age < 0 || age > 365
    || new Date(date).toISOString().slice(0, 10) !== date) {
    throw new ApiError(422, 'INVALID_SUPPLEMENT_DOSE_DATE', '복용 날짜를 확인해주세요.');
  }
}

export function mockGetSupplementDoses(date: string): SupplementDoseRecord[] {
  validateDate(date);
  return readRecords().filter(item => item.date === date).map(item => ({ ...item }));
}

export function mockSaveSupplementDose(payload: SupplementDoseRecord): SupplementDoseRecord {
  const registration = mockOwnedSupplement(payload.supplementId);
  if (!registration) throw new ApiError(404, 'SUPPLEMENT_NOT_FOUND', '영양제를 찾지 못했어요.');
  validateDate(payload.date);
  if (!SLOT_ORDER.includes(payload.slot) || (payload.taken && (
    !mockSupplements().some(item => item.supplementId === payload.supplementId)
    || !registration.slots.includes(payload.slot)
    || (registration.startDate && payload.date < registration.startDate)
    || (registration.endDate && payload.date > registration.endDate)
  ))) {
    throw new ApiError(422, 'INVALID_SUPPLEMENT_DOSE', '등록한 복용 기간과 시간대를 확인해주세요.');
  }
  const next = readRecords().filter(item => !(
    item.supplementId === payload.supplementId && item.date === payload.date && item.slot === payload.slot
  ));
  if (payload.taken) next.push({ ...payload });
  memory.set(scope(), next);
  try { localStorage.setItem(scope(), JSON.stringify(next)); } catch { /* Account-scoped memory fallback. */ }
  return { ...payload };
}
