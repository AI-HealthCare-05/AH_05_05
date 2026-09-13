import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-02T12:00:00+09:00'));
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
});

test('복약 선택 진입·선택·취소 중에도 상단 제목을 유지한다', async ({ page }, testInfo) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/medications');

  const title = page.getByRole('heading', { name: '복약', exact: true });
  await expect(title).toBeVisible();

  await page.getByRole('button', { name: '선택', exact: true }).click();
  await expect(title).toBeVisible();
  await page.getByRole('checkbox', { name: /처방 선택/ }).first().check();
  await expect(title).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('medications-selection-title.png'),
    fullPage: true,
    animations: 'disabled',
  });

  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(title).toBeVisible();
  await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
});

test('영양제 삭제 편집 모드에서도 상단 제목은 영양제다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/supplements');

  const title = page.getByRole('heading', { name: '영양제', exact: true });
  await expect(title).toBeVisible();
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(title).toBeVisible();
  await expect(page.getByRole('button', { name: '완료', exact: true })).toBeVisible();
});
