import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const longName = '아스피린프로텍트정100밀리그람긴이름의약품정보줄바꿈확인';

async function openReview(page: Page, confirmed = false) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'ocr-disclosure-fixture');
    sessionStorage.setItem('poke.account-principal', 'ocr-disclosure@example.com');
  });
  await page.route('**/api/v1/ocr/jobs/501', route => route.fulfill({ json: {
    batchId: '501', ocrStatus: confirmed ? 'complete' : 'ready_for_review', documentImageUrl: '',
    fields: { dispensedDate: { value: '2026-09-10', confidence: 'high' } },
    medications: [
      { tempId: '1', name: longName, strength: '100mg', doseQuantity: '1.50정', timesPerDay: 3, days: 30, confidence: 'low' },
      { tempId: '2', name: '필요시복용약', timesPerDay: null, confidence: 'medium' },
      { tempId: '3', name: '추출하지못한약', confidence: 'high' },
    ], lowConfidenceCount: 1,
  } }));
  await page.route('**/api/v1/ocr/jobs/501/**', route => route.fulfill({ status: 404 }));
  await page.goto(`/ocr-review?batchId=501${confirmed ? '&mode=confirmed&recordId=91' : ''}`);
}

test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));

for (const width of [320, 390]) {
  test(`OCR 약 상세는 기본 접힘이고 펼치면 항목별 줄바꿈하며 이름과 경고는 유지한다 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    await openReview(page);
    const card = page.getByRole('article', { name: longName, exact: true });
    const toggle = card.getByRole('button', { name: `${longName} 약 정보`, exact: true });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(card.getByText('확인 필요', { exact: true })).toBeVisible();
    await expect(card.getByText('함량', { exact: true })).toBeHidden();
    await card.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `test-results-ocr-disclosure/ocr-collapsed-${width}.png` });
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const rows = card.locator('dl > div');
    await expect(rows).toHaveText(['함량100mg', '1회 투약량1.5정', '1일 횟수3회', '투약일수30일']);
    const bounds = await rows.evaluateAll(elements => elements.map(element => {
      const rect = element.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom };
    }));
    for (let i = 1; i < bounds.length; i += 1) expect(bounds[i].top).toBeGreaterThanOrEqual(bounds[i - 1].bottom);
    const name = card.locator('strong');
    expect(await name.evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThan(30);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await card.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `test-results-ocr-disclosure/ocr-expanded-${width}.png` });
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(card.getByText('확인 필요', { exact: true })).toBeVisible();
  });
}

test('별도 수정 버튼은 원본 값을 편집하고 수정 후에도 정보를 접었다 펼칠 수 있다', async ({ page }) => {
  await openReview(page);
  const card = page.getByRole('article', { name: longName, exact: true });
  await card.getByRole('button', { name: `${longName} 수정`, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('함량', { exact: true })).toHaveValue('100mg');
  await expect(dialog.getByLabel('1회 투약량', { exact: true })).toHaveValue('1.50정');
  await dialog.getByLabel('함량', { exact: true }).fill('150mg');
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(card.getByText('확인 필요', { exact: true })).toHaveCount(0);
  await card.getByRole('button', { name: `${longName} 약 정보`, exact: true }).click();
  await expect(card.locator('dl > div').first()).toHaveText('함량150mg');
});

test('저장된 읽기 전용 OCR도 상세를 열 수 있고 미추출과 필요 시를 구분한다', async ({ page }) => {
  await openReview(page, true);
  await expect(page.getByRole('button', { name: / 수정$/ })).toHaveCount(0);
  const prn = page.getByRole('article', { name: '필요시복용약', exact: true });
  await prn.getByRole('button', { name: '필요시복용약 약 정보', exact: true }).click();
  await expect(prn.locator('dl > div')).toHaveText(['함량미추출', '1회 투약량미추출', '1일 횟수필요 시', '투약일수미추출']);
  await expect(prn.getByText('확인 필요')).toBeVisible();
  const missing = page.getByRole('article', { name: '추출하지못한약', exact: true });
  await missing.getByRole('button', { name: '추출하지못한약 약 정보', exact: true }).click();
  await expect(missing.locator('dl > div')).toHaveText(['함량미추출', '1회 투약량미추출', '1일 횟수미추출', '투약일수미추출']);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
