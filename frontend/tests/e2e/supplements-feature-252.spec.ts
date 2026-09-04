import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('등록 영양제는 상세에서 내 기록을 보여주고 별점 수정과 복용 중단을 제공한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const list = page.getByRole('region', { name: '먹고 있는 영양제' });
  await list.getByRole('button', { name: /오메가3/ }).click();

  await expect(page.getByRole('heading', { name: '내 영양제' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '내 기록' })).toBeVisible();
  const record = page.getByRole('region', { name: '내 기록' });
  await expect(record.getByText('내 별점', { exact: true })).toBeVisible();
  await expect(record.getByText('내 메모', { exact: true })).toBeVisible();
  await expect(record.getByText('아침 식후에 먹기', { exact: true })).toBeVisible();
  await expect(record.getByText('내 후기', { exact: true })).toBeVisible();
  await expect(record.getByText('꾸준히 챙겨 먹기 편해요.', { exact: true })).toBeVisible();
  await expect(record.getByRole('button', { name: '제품 정보 보기' })).toBeVisible();

  await page.getByRole('button', { name: '별점 수정' }).click();
  const ratingSheet = page.getByRole('dialog', { name: '별점 수정' });
  await expect(ratingSheet).toBeVisible();
  await ratingSheet.getByRole('button', { name: '별 5점' }).click();
  await ratingSheet.getByRole('button', { name: '저장' }).click();
  await expect(ratingSheet).toBeHidden();
  await expect(record.getByText('★★★★★', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '복용 중단하기' }).click();
  const stopDialog = page.getByRole('dialog', { name: '오메가3 복용을 중단할까요?' });
  await expect(stopDialog).toBeVisible();
  await expect(stopDialog.getByText('오메가3 · 1정 · 아침 · 저녁', { exact: true })).toBeVisible();
  await stopDialog.getByRole('button', { name: '중단하기' }).click();
  await expect(page.getByRole('heading', { name: '내 영양제' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '먹고 있는 영양제' }).getByText('오메가3')).toHaveCount(0);
});
