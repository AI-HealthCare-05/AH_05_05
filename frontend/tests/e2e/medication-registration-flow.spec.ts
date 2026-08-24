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

test('미래 조제일은 저장할 수 없다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await page.getByLabel('조제일').fill('2099-01-01');

  await expect(page.getByText('조제일은 오늘까지만 고를 수 있어요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '저장하고 복약 시간 설정' })).toBeDisabled();
});

test('OCR 약 카드를 누르면 선택한 약 하나만 편집하는 시트가 열린다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await page.getByRole('button', { name: /리바록사반 10mg/ }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('heading', { name: '리바록사반 수정' })).toBeVisible();
  await expect(sheet.getByLabel('약품명')).toHaveValue('리바록사반');
  await expect(sheet.getByLabel('용량')).toHaveValue('10mg');
  await expect(sheet.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '약 추가' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '저장', exact: true })).toHaveCount(1);
});

test('약 삭제는 편집 시트의 텍스트 동작을 거쳐 확인 화면에서만 실행한다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await page.getByRole('button', { name: /리바록사반 10mg/ }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('button', { name: '삭제', exact: true })).toHaveCount(0);
  await sheet.getByRole('button', { name: '이 약 삭제' }).click();
  await expect(sheet.getByRole('heading', { name: '이 약을 지울까요?' })).toBeVisible();
  await sheet.getByRole('button', { name: '삭제', exact: true }).click();

  await expect(page.getByRole('button', { name: /리바록사반 10mg/ })).toHaveCount(0);
});

test('빠진 약 직접 추가는 목록 편집을 거치지 않고 빈 약 추가 시트를 연다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await page.getByRole('button', { name: '빠진 약 직접 추가' }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('heading', { name: '약 추가' })).toBeVisible();
  await expect(sheet.getByLabel('약품명')).toHaveValue('');
  await expect(sheet.getByText('추출 내용을 수정')).toHaveCount(0);
});

test('봉투 원문에 시간대가 모두 있으면 복약 시간 설정은 시간과 날짜 두 블록만 보여준다', async ({
  page,
}) => {
  await page.goto('/dev/medication-schedule');

  await expect(page.getByText('어느 시간에 알람을 드릴까요?')).toBeVisible();
  await expect(page.getByText('처음 약을 언제부터 드셨나요?')).toBeVisible();
  await expect(page.getByRole('region', { name: '자동 배정 시간 확인' })).toHaveCount(0);
  await expect(page.getByText('약마다 언제 먹는지 확인해주세요')).toHaveCount(0);
});

test('시간대가 없는 약은 자동 배정 확인 블록에 그 약만 보여준다', async ({ page }) => {
  await page.goto('/dev/medication-schedule-auto-assigned');

  const confirmation = page.getByRole('region', { name: '자동 배정 시간 확인' });
  await expect(confirmation).toBeVisible();
  await expect(confirmation.getByText('이 약들은 언제 먹는지 봉투에 없었어요')).toBeVisible();
  await expect(confirmation.getByText('저희가 정한 시간입니다. 맞는지 확인해주세요.')).toBeVisible();
  await expect(confirmation.getByText('리바록사반 10mg')).toBeVisible();
  await expect(confirmation.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(confirmation.getByText('파모티딘 20mg')).toHaveCount(0);
  await expect(confirmation.getByText('아세트아미노펜 650mg')).toHaveCount(0);
});

test('OCR 확인 화면은 새로 열어도 저장된 약봉투 원본 한 장을 보여준다', async ({ page }) => {
  await page.goto('/dev/ocr-review');

  const image = page.getByRole('img', { name: '등록한 약봉투 원본' });
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute('src', '/mock/medication-envelope.svg');
  await expect(page.getByRole('region', { name: '약 4개' }).getByRole('img')).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toBeVisible();
});

test('약봉투 원본은 전체화면으로 확대하고 확대 제스처를 막지 않는다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await page.getByRole('button', { name: '등록한 약봉투 원본 크게 보기' }).click();

  const viewer = page.getByRole('dialog', { name: '약봉투 원본 크게 보기' });
  const enlargedImage = viewer.getByRole('img', { name: '확대한 약봉투 원본' });
  await expect(viewer).toBeVisible();
  expect(await enlargedImage.evaluate((element) => getComputedStyle(element).touchAction)).not.toBe(
    'none',
  );
  await viewer.getByRole('button', { name: '닫기' }).click();
  await expect(viewer).toHaveCount(0);
});
