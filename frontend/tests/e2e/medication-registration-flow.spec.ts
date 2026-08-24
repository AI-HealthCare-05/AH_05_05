import { expect, test } from 'playwright/test';

test('약봉투 입력은 촬영과 갤러리 모두 이미지 한 장만 받는다', async ({ page }) => {
  await page.goto('/dev/document-upload');

  const inputs = page.locator('input[type="file"]');
  await expect(inputs).toHaveCount(2);
  await expect(inputs.nth(0)).toHaveAttribute('accept', 'image/*');
  await expect(inputs.nth(0)).toHaveAttribute('capture', 'environment');
  await expect(inputs.nth(0)).not.toHaveAttribute('multiple', '');
  await expect(inputs.nth(1)).toHaveAttribute('accept', 'image/*');
  await expect(inputs.nth(1)).not.toHaveAttribute('capture', /.+/);
  await expect(inputs.nth(1)).not.toHaveAttribute('multiple', '');
});

test('선택한 약봉투를 같은 화면에서 미리보고 바로 판독 화면으로 보낸다', async ({ page }) => {
  await page.goto('/dev/document-upload');
  await page.locator('input[type="file"]').nth(1).setInputFiles({
    name: '조제약봉투_01.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake-png-for-ui-preview'),
  });

  await expect(page.getByRole('img', { name: '선택한 약봉투 미리보기' })).toBeVisible();
  await expect(page.getByText('조제약봉투_01.png')).toBeVisible();
  await page.getByRole('button', { name: '등록하기' }).click();
  await expect(page).toHaveURL(/\/ocr-review$/);
});

test('OCR 확인 항목 수와 배지와 저장 전 모달 개수가 같고 제거 필드는 보이지 않는다', async ({
  page,
}) => {
  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByText('1곳만 확인해주세요')).toBeVisible();
  await expect(page.getByText('확인 필요', { exact: true })).toHaveCount(1);
  await expect(page.getByText('확인됨', { exact: true })).toHaveCount(0);
  await expect(page.getByText('진단명', { exact: true })).toHaveCount(0);
  await expect(page.getByText('수술명', { exact: true })).toHaveCount(0);
  await expect(page.getByText('퇴원일', { exact: true })).toHaveCount(0);
  await expect(page.getByText('의료진 권고사항', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: '저장하고 복약 시간 설정' }).click();
  const confirm = page.getByRole('dialog');
  await expect(confirm).toContainText('1개 항목 확인 필요');
});

test('조제일을 스케줄 시작일로 넘기고 저장 후 홈으로 교체 이동한다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await expect(page.getByLabel('조제일')).toHaveValue('2026-08-22');

  await page.getByRole('button', { name: '저장하고 복약 시간 설정' }).click();
  await page.getByRole('button', { name: '확인 후 저장' }).click();
  await expect(page).toHaveURL(/\/medication-schedule$/);
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');

  await page.getByRole('button', { name: '기본 시간으로 건너뛰기' }).click();
  await expect(page).toHaveURL(/\/home$/);
  await page.goBack();
  await expect(page).not.toHaveURL(/\/medication-schedule$/);
});
