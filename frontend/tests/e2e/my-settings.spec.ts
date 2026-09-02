import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

async function chooseTime(
  page: Page,
  slotLabel: string,
  hour: string,
  minute: string,
) {
  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await sheet.getByLabel(slotLabel + ' 시').click();
  await page.getByRole('option', { name: hour + '시', exact: true }).click();
  await sheet.getByLabel(slotLabel + ' 분').click();
  await page.getByRole('option', { name: minute + '분', exact: true }).click();
}

test('마이페이지 알림 카드는 시간 값 없이 단일 설정 행에서 네 슬롯 시트를 연다', async ({
  page,
}) => {
  await page.goto('/dev/my-authenticated');

  const openButton = page.getByRole('button', { name: '알림 시간 설정' });
  await expect(openButton).toBeVisible();
  await expect(page.getByText('예약된 알림')).toHaveCount(0);
  await expect(page.getByText('받은 알림 보기')).toHaveCount(0);
  await expect(page.getByText('08:00', { exact: true })).toHaveCount(0);

  await openButton.click();
  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByLabel('아침 시')).toContainText('08');
  await expect(sheet.getByLabel('점심 시')).toContainText('13');
  await expect(sheet.getByLabel('저녁 시')).toContainText('19');
  await expect(sheet.getByLabel('자기전 시')).toContainText('22');
  await expect(page.getByRole('dialog', { name: '시간 선택' })).toHaveCount(0);
});

test('마이페이지에서 네 시간을 고친 뒤 저장하면 한 번에 반영한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();

  await chooseTime(page, '아침', '07', '30');
  await chooseTime(page, '점심', '12', '30');
  await chooseTime(page, '저녁', '18', '30');
  await chooseTime(page, '자기전', '23', '30');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect(page.getByRole('dialog', { name: '알림 시간' })).toHaveCount(0);
  await expect(page.getByText('알림 시간을 바꿨어요.')).toBeVisible();

  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  const savedSheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(savedSheet.getByLabel('아침 시')).toContainText('07');
  await expect(savedSheet.getByLabel('아침 분')).toContainText('30');
  await expect(savedSheet.getByLabel('자기전 시')).toContainText('23');
  await expect(savedSheet.getByLabel('자기전 분')).toContainText('30');

  await chooseTime(page, '아침', '08', '00');
  await chooseTime(page, '점심', '13', '00');
  await chooseTime(page, '저녁', '19', '00');
  await chooseTime(page, '자기전', '22', '00');
  await page.getByRole('button', { name: '저장', exact: true }).click();
});

test('시간 순서가 어긋나면 저장하지 않고 시트 안에 안내한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await chooseTime(page, '아침', '14', '00');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(sheet).toBeVisible();
  await expect(
    sheet.getByText('아침 < 점심 < 저녁 < 자기전 순서로 정해주세요'),
  ).toBeVisible();
  await expect(sheet.getByLabel('아침 시')).toContainText('14');
});

test('취소하면 고른 값을 버리고 시트를 열 때의 값으로 복원한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await chooseTime(page, '아침', '07', '30');
  await page.getByRole('button', { name: '취소', exact: true }).click();

  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(sheet.getByLabel('아침 시')).toContainText('08');
  await expect(sheet.getByLabel('아침 분')).toContainText('00');
});

test('알림 시간 설정 시트는 375px에서 가로로 넘치지 않는다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await expect(page.getByRole('dialog', { name: '알림 시간' })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
