import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('마이페이지의 예약된 알림 행에서 읽기 전용 목록으로 이동한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: /예약된 알림/ }).click();

  await expect(page).toHaveURL(/\/my\/alarms$/);
  await expect(page.getByRole('heading', { name: '예약된 알림' })).toBeVisible();
  await expect(page.getByRole('button', { name: /추가|수정|취소/ })).toHaveCount(0);
});

test('예약된 알림은 가까운 scheduledAt부터 보여준다', async ({ page }) => {
  await page.goto('/dev/my-alarms');

  const first = page.getByText('아침 복약 알림', { exact: true });
  const second = page.getByText('진료일정 알림', { exact: true });
  const firstBox = await first.boundingBox();
  const secondBox = await second.boundingBox();
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  expect(firstBox!.y).toBeLessThan(secondBox!.y);
});

test('활성 예약 알림이 없으면 정확한 빈 상태를 보여준다', async ({ page }) => {
  await page.goto('/dev/my-alarms-empty');

  await expect(page.getByText('예약된 알림이 없어요.')).toBeVisible();
});
