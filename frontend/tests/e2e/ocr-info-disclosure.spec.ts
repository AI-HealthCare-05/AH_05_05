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
  test(`OCR compact cards align the pencil with the final name line and keep warnings beside names (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 812 });
    await openReview(page);
    const card = page.getByRole('article', { name: longName, exact: true });
    await expect(card).toBeVisible();
    await expect(card.locator('[aria-expanded]')).toHaveCount(0);
    await expect(card.getByText('확인 필요', { exact: true })).toBeVisible();
    await expect(card.getByText('함량', { exact: true })).toBeHidden();
    await card.scrollIntoViewIfNeeded();
    const edit = card.getByRole('button', { name: `${longName} 수정`, exact: true });
    await expect(edit).toHaveText('');
    const lastLine = await card.locator('strong').evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const rect = Array.from(range.getClientRects()).at(-1)!;
      return { x: rect.x, right: rect.right, center: rect.y + rect.height / 2 };
    });
    const icon = (await edit.locator('svg').boundingBox())!;
    const warning = (await card.getByText('확인 필요', { exact: true }).boundingBox())!;
    expect(Math.abs(icon.y + icon.height / 2 - lastLine.center)).toBeLessThanOrEqual(3);
    expect(warning.x).toBeGreaterThan(lastLine.x);
    expect(Math.abs(warning.y + warning.height / 2 - lastLine.center)).toBeLessThanOrEqual(3);
    const name = card.locator('strong');
    expect(await name.evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThan(30);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.getByRole('article').last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`ocr-compact-${width}.png`), animations: 'disabled' });
    await edit.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog').getByLabel('약품명')).toHaveValue(longName);
  });
}

test('연필은 원본 값을 편집하고 확인한 경고를 제거한다', async ({ page }) => {
  await openReview(page);
  const card = page.getByRole('article', { name: longName, exact: true });
  await card.getByRole('button', { name: `${longName} 수정`, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('함량', { exact: true })).toHaveValue('100mg');
  await expect(dialog.getByLabel('1회 투약량', { exact: true })).toHaveValue('1.50정');
  await dialog.getByLabel('함량', { exact: true }).fill('150mg');
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(card.getByText('확인 필요', { exact: true })).toHaveCount(0);
  await card.getByRole('button', { name: `${longName} 수정`, exact: true }).click();
  await expect(dialog.getByLabel('함량', { exact: true })).toHaveValue('150mg');
});

test('저장된 읽기 전용 OCR은 접기 없이 미추출과 필요 시 정보를 보존한다', async ({ page }) => {
  await openReview(page, true);
  await expect(page.getByRole('button', { name: / 수정$/ })).toHaveCount(0);
  const prn = page.getByRole('article', { name: '필요시복용약', exact: true });
  await expect(prn.locator('[aria-expanded]')).toHaveCount(0);
  await expect(prn.locator('dl > div')).toHaveText(['함량미추출', '1회 투약량미추출', '1일 횟수필요 시', '투약일수미추출']);
  await expect(prn.getByText('확인 권장')).toBeVisible();
  const missing = page.getByRole('article', { name: '추출하지못한약', exact: true });
  await expect(missing.locator('dl > div')).toHaveText(['함량미추출', '1회 투약량미추출', '1일 횟수미추출', '투약일수미추출']);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
