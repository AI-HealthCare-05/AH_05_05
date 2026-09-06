import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';
import { formatMedicationLabel } from '../../src/shared/lib/medicationLabel';

test('약명에 포함된 동일 함량만 생략하고 다른 함량은 보존한다', () => {
  expect(formatMedicationLabel('독시사이클린캡슐100mg', '100mg')).toBe('독시사이클린캡슐100mg');
  expect(formatMedicationLabel('클린다마이신외용액1%', '1%')).toBe('클린다마이신외용액1%');
  expect(formatMedicationLabel('약 100 MG', '100mg')).toBe('약 100 MG');
  expect(formatMedicationLabel('약500mg', '5mg')).toBe('약500mg 5mg');
  expect(formatMedicationLabel('약', '100mg')).toBe('약 100mg');
});

test('OCR 결과는 함량을 제목에 중복하지 않고 누락 필드를 확인하도록 표시한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'ocr-display-fixture');
    sessionStorage.setItem('poke.account-principal', 'display@example.com');
  });
  await page.route('**/api/v1/ocr/jobs/501', route => route.fulfill({ json: {
    batchId: '501', ocrStatus: 'ready_for_review', documentImageUrl: '',
    fields: { dispensedDate: { value: '2026-09-05', confidence: 'high' } },
    medications: [
      { tempId: '1', name: '독시사이클린캡슐100mg', strength: '100mg', doseQuantity: '1', timesPerDay: 2, days: 7, confidence: 'high' },
      { tempId: '2', name: '클린다마이신외용액1%', strength: '1%', timesPerDay: 2, days: 14, confidence: 'high' },
      { tempId: '3', name: '세라마이드보습크림', doseQuantity: '1', timesPerDay: 2, days: 14, confidence: 'high' },
    ], lowConfidenceCount: 0,
  } }));
  await page.route('**/api/v1/ocr/jobs/501/**', route => route.fulfill({ status: 404 }));
  await page.goto('/ocr-review?batchId=501');
  await expect(page.locator('strong').filter({ hasText: '독시사이클린' })).toHaveText('독시사이클린캡슐100mg');
  await expect(page.locator('strong').filter({ hasText: '클린다마이신' })).toHaveText('클린다마이신외용액1%');
  await expect(page.getByText('확인 필요', { exact: true })).toHaveCount(2);
  await page.screenshot({ path: process.env.OCR_REVIEW_SCREENSHOT ?? 'test-results-ocr-display/ocr-strength-fixed.png', fullPage: true });
});
