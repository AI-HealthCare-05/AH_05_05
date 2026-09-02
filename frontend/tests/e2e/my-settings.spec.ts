import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

async function chooseTime(page: Page, hour: string, minute: string) {
  const sheet = page.getByRole('dialog', { name: '시간 선택' });
  await sheet.getByLabel('시').click();
  await page.getByRole('option', { name: `${hour}시`, exact: true }).click();
  await sheet.getByLabel('분').click();
  await page.getByRole('option', { name: `${minute}분`, exact: true }).click();
}

test('마이페이지 알림 카드에 사용자 공통 복약 시간 네 개를 보여준다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('button', { name: /아침 08:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /점심 13:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /저녁 19:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /자기전 22:00/ })).toBeVisible();
});

test('마이페이지에서 한 시간을 바꾸면 응답의 네 설정값으로 화면을 갱신한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: /아침 08:00/ }).click();
  await chooseTime(page, '12', '30');
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page.getByRole('button', { name: /아침 12:30/ })).toBeVisible();
  await expect(page.getByText('알림 시간을 바꿨어요.')).toBeVisible();

  await page.getByRole('button', { name: /아침 12:30/ }).click();
  await chooseTime(page, '08', '00');
  await page.getByRole('button', { name: '이 시간 적용' }).click();
  await expect(page.getByRole('button', { name: /아침 08:00/ })).toBeVisible();
});

test('마이페이지에서 순서가 겹치는 시간은 적용하지 않고 선택 시트를 유지한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: /점심 13:00/ }).click();
  await chooseTime(page, '19', '00');
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page.getByRole('heading', { name: '시간을 적용할 수 없어요' })).toBeVisible();
  await expect(
    page.getByText('복약 시간은 아침약 → 점심약 → 저녁약 → 취침약 순서로 설정해주세요.'),
  ).toBeVisible();
  await page.getByRole('button', { name: '확인' }).click();
  await expect(page.getByRole('heading', { name: '시간 선택' })).toBeVisible();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('button', { name: /점심 13:00/ })).toBeVisible();
});

test('마이페이지 알림 시간 행은 375px에서 가로로 넘치지 않는다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await expect(page.getByRole('button', { name: /자기전 22:00/ })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
