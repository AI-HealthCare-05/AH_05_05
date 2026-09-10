import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';
import { formatMedicationLabel, formatMedicationStrength } from '../../src/shared/lib/medicationLabel';

test('제목은 원래 약명만 사용하고 별도 함량 필드는 추가하지 않는다', () => {
  expect(formatMedicationLabel('독시사이클린캡슐100mg', '100mg')).toBe('독시사이클린캡슐100mg');
  expect(formatMedicationLabel('클린다마이신외용액1%', '1%')).toBe('클린다마이신외용액1%');
  expect(formatMedicationLabel('약 100 MG', '100mg')).toBe('약 100 MG');
  expect(formatMedicationLabel('약500mg', '5mg')).toBe('약500mg');
  expect(formatMedicationLabel('약', '100mg')).toBe('약');
  expect(formatMedicationLabel('아스피린프로텍트정100밀리그람', '100mg')).toBe('아스피린프로텍트정100밀리그람');
});

test('한글 단위의 제품명에도 동일 함량을 중복해서 덧붙이지 않는다', () => {
  expect(formatMedicationLabel('펙소나딘정120밀리그램', '120mg')).toBe('펙소나딘정120밀리그램');
  expect(formatMedicationLabel('시네츄라시럽(15mL)', '15밀리리터')).toBe('시네츄라시럽(15mL)');
  expect(formatMedicationLabel('약0.5마이크로그램', '0.5μg')).toBe('약0.5마이크로그램');
  expect(formatMedicationLabel('연고1퍼센트', '1%')).toBe('연고1퍼센트');
  expect(formatMedicationLabel('약120밀리그램', '20mg')).toBe('약120밀리그램');
  expect(formatMedicationLabel('약0.5밀리그램', '5mg')).toBe('약0.5밀리그램');
  expect(formatMedicationLabel('약120밀리그램', '120g')).toBe('약120밀리그램');
});

test('같은 함량의 단위 환산과 반복 표기를 중복으로 취급한다', () => {
  expect(formatMedicationLabel('글로덱시정300mg', '300mg 0.3g')).toBe('글로덱시정300mg');
  expect(formatMedicationLabel('글로덱시정300mg', '0.3g')).toBe('글로덱시정300mg');
  expect(formatMedicationLabel('약0.5mg', '500μg')).toBe('약0.5mg');
  expect(formatMedicationLabel('약', '300mg 0.3g')).toBe('약');
  expect(formatMedicationLabel('약300mg', '300mg · 1정')).toBe('약300mg');
  expect(formatMedicationLabel('복합정5/50mg', '5mg')).toBe('복합정5/50mg');
  expect(formatMedicationLabel('', '300mg 0.3g')).toBe('');
  expect(formatMedicationStrength('300mg 0.3g')).toBe('300mg');
  expect(formatMedicationStrength('300mg 300mg')).toBe('300mg');
  expect(formatMedicationStrength('300mg 0.5g')).toBe('300mg 0.5g');
  expect(formatMedicationStrength('5/50mg')).toBe('5/50mg');
  expect(formatMedicationStrength('5mg/mL 5mg')).toBe('5mg/mL 5mg');
});

test('호환·전각 단위도 중복을 제거하고 숫자 일부는 함량으로 오인하지 않는다', () => {
  expect(formatMedicationLabel('글로덱시정300㎎', '300mg')).toBe('글로덱시정300㎎');
  expect(formatMedicationLabel('글로덱시정３００ｍｇ', '300mg')).toBe('글로덱시정３００ｍｇ');
  expect(formatMedicationLabel('약300mg', '３００ｍｇ ０．３ｇ')).toBe('약300mg');
  expect(formatMedicationLabel('약.5g', '5g')).toBe('약.5g');
});

for (const width of [375, 1280]) {
  test(`OCR 제목에 별도 함량을 붙이지 않고 약명 원본과 함량 상세를 보존한다 (${width}px)`, async ({ page }) => {
    test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
    await page.setViewportSize({ width, height: 812 });
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
        { tempId: '4', name: '펙소나딘정120밀리그램', strength: '120mg', doseQuantity: '2.00', timesPerDay: 1, days: 5, confidence: 'high' },
        { tempId: '5', name: '글로덱시정300mg', strength: '300mg 0.3g', doseQuantity: '1.50정', timesPerDay: 3, days: 5, confidence: 'high' },
        { tempId: '6', name: '아스피린프로텍트정100밀리그람', strength: '100mg', doseQuantity: '1.00', timesPerDay: 1, days: 30, confidence: 'high' },
      ], lowConfidenceCount: 0,
    } }));
    await page.route('**/api/v1/ocr/jobs/501/**', route => route.fulfill({ status: 404 }));
    await page.goto('/ocr-review?batchId=501');
    await expect(page.locator('strong').filter({ hasText: '독시사이클린' })).toHaveText('독시사이클린캡슐100mg');
    await expect(page.locator('strong').filter({ hasText: '클린다마이신' })).toHaveText('클린다마이신외용액1%');
    await expect(page.locator('strong').filter({ hasText: '펙소나딘' })).toHaveText('펙소나딘정120밀리그램');
    await expect(page.locator('strong').filter({ hasText: '글로덱시' })).toHaveText('글로덱시정300mg');
    await expect(page.locator('strong').filter({ hasText: '아스피린' })).toHaveText('아스피린프로텍트정100밀리그람');
    for (const [name, values] of [
      ['아스피린프로텍트정100밀리그람', ['함량100mg', '1회 투약량1', '1일 횟수1회', '투약일수30일']],
      ['글로덱시정300mg', ['함량300mg', '1회 투약량1.5정', '1일 횟수3회', '투약일수5일']],
      ['펙소나딘정120밀리그램', ['함량120mg', '1회 투약량2', '1일 횟수1회', '투약일수5일']],
    ] as const) {
      const card = page.getByRole('article', { name, exact: true });
      await card.getByRole('button', { name: `${name} 약 정보`, exact: true }).click();
      await expect(card.locator('dl > div')).toHaveText([...values]);
    }
    await expect(page.getByText('확인 필요', { exact: true })).toHaveCount(2);
    await page.screenshot({ path: `test-results-ocr-display/ocr-strength-dedup-${width}.png`, fullPage: true });
    await page.getByRole('button', { name: '글로덱시정300mg 수정', exact: true }).click();
    await expect(page.getByRole('dialog').getByLabel('약품명')).toHaveValue('글로덱시정300mg');
    await expect(page.getByRole('dialog').getByLabel('함량', { exact: true })).toHaveValue('300mg 0.3g');
    await expect(page.getByRole('dialog').getByLabel('1회 투약량', { exact: true })).toHaveValue('1.50정');
  });
}
