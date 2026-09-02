import { expect, test } from 'playwright/test';

test('제품 상세는 공개 후기 10개를 표시하고 더 보기로 이어 붙인다', async ({ page }) => {
  await page.goto('/dev/supplements/product/mock-501');

  const reviews = page.getByRole('region', { name: '후기' });
  await expect(reviews.getByRole('article')).toHaveCount(10);
  await expect(reviews.getByRole('article', { name: '김*훈 후기' })).toHaveCount(2);
  await expect(reviews.getByText('박*', { exact: true })).toBeVisible();
  await expect(reviews.getByText('남**훈', { exact: true })).toBeVisible();
  await expect(reviews.getByText('K***g', { exact: true })).toBeVisible();
  await expect(reviews.getByText('내 후기', { exact: true })).toBeVisible();
  await expect(reviews.getByText('개인의 경험이며 효능을 보장하지 않습니다')).toHaveCount(1);

  await reviews.getByRole('button', { name: '더 보기' }).click();
  await expect(reviews.getByRole('article')).toHaveCount(12);
  await expect(reviews.getByText('개인의 경험이며 효능을 보장하지 않습니다')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('신고 성공은 카드를 제거하고 실패는 그대로 둔다', async ({ page }) => {
  await page.goto('/dev/supplements/product/mock-501');
  const reviews = page.getByRole('region', { name: '후기' });

  const successCard = reviews.getByRole('article', { name: '박* 후기' });
  await successCard.getByRole('button', { name: '신고' }).click();
  const successConfirm = page.getByRole('dialog', { name: '이 후기를 신고할까요?' });
  await successConfirm.getByRole('button', { name: '신고하기' }).click();
  await expect(page.getByText('신고했어요')).toBeVisible();
  await expect(successCard).toHaveCount(0);

  const failureCard = reviews.getByRole('article', { name: '남**훈 후기' });
  await failureCard.getByRole('button', { name: '신고' }).click();
  const failureConfirm = page.getByRole('dialog', { name: '이 후기를 신고할까요?' });
  await failureConfirm.getByRole('button', { name: '신고하기' }).click();
  await expect(page.getByText('잠시 후 다시 시도해주세요')).toBeVisible();
  await expect(failureCard).toBeVisible();
});
