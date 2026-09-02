import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('진료일정은 선택 입력의 빈 상태와 지난 일정 토글을 보여준다', async ({ page }) => {
  await page.goto('/dev/my-visits');

  await expect(page.getByRole('heading', { name: '진료일정' })).toBeVisible();
  await expect(page.getByText('시간 미정')).toBeVisible();
  await expect(page.getByText('병원 미정')).toBeVisible();
  await expect(page.getByText('지난 진료')).toHaveCount(0);
  await page.getByRole('button', { name: '지난 일정 보기' }).click();
  await expect(page.getByText('지난 진료')).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test('병원과 시간을 비운 새 진료일정을 등록한다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();

  const sheet = page.getByRole('dialog', { name: '진료일정 추가' });
  await sheet.getByLabel('진료일').fill('2026-09-20');
  await sheet.getByRole('button', { name: '저장' }).click();

  const created = page.getByRole('button', { name: /9월 20일.*병원 미정.*시간 미정/ });
  await expect(created).toBeVisible();
});

test('진료일정 수정에서 병원과 시간을 null로 지울 수 있다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: /9월 16일.*늘봄병원.*10:30/ }).click();

  const sheet = page.getByRole('dialog', { name: '진료일정 수정' });
  await sheet.getByLabel('병원').fill('');
  await sheet.getByLabel('진료 시간').fill('');
  await sheet.getByRole('button', { name: '저장' }).click();

  await expect(
    page.getByRole('button', { name: /9월 16일.*병원 미정.*시간 미정/ }),
  ).toBeVisible();
});

test('진료일정을 삭제하기 전에 연결된 알림 삭제를 안내한다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  const target = page.getByRole('button', { name: /9월 18일.*병원 미정.*14:30/ });
  await target.click();
  await page.getByRole('dialog', { name: '진료일정 수정' }).getByRole('button', { name: '삭제' }).click();

  const dialog = page.getByRole('dialog', { name: '진료일정 삭제' });
  await expect(dialog).toContainText('연결된 알림도 함께 삭제돼요.');
  await dialog.getByRole('button', { name: '삭제하기' }).click();
  await expect(target).toHaveCount(0);
});
