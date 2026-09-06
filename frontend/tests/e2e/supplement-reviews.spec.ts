import { expect, test } from 'playwright/test';

const IS_REAL_API = process.env.VITE_USE_MOCK === 'false';

test('제품 상세는 공개 후기 10개를 표시하고 더 보기로 이어 붙인다', async ({ page }) => {
  test.skip(IS_REAL_API, '고정 후기 목업의 10개 페이지 구성을 확인합니다.');
  await page.goto('/dev/supplements/product/mock-501');

  const reviews = page.getByRole('region', { name: '후기' });
  await expect(reviews.getByRole('article')).toHaveCount(10);
  await expect(reviews.getByRole('article', { name: '김*훈 후기' })).toHaveCount(2);
  await expect(reviews.getByText('박*', { exact: true })).toBeVisible();
  await expect(reviews.getByText('남**훈', { exact: true })).toBeVisible();
  await expect(reviews.getByText('K***g', { exact: true })).toBeVisible();
  await expect(reviews.getByText('내 후기', { exact: true })).toBeVisible();
  await expect(reviews.getByText('개인의 경험이며 효능을 보장하지 않아요')).toHaveCount(1);

  await reviews.getByRole('button', { name: '더 보기' }).click();
  await expect(reviews.getByRole('article')).toHaveCount(12);
  await expect(reviews.getByText('개인의 경험이며 효능을 보장하지 않아요')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('신고 성공은 카드를 제거하고 실패는 그대로 둔다', async ({ page }) => {
  test.skip(IS_REAL_API, '목업의 신고 성공·실패 상태를 확인합니다.');
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

test('실 API 모드는 후기 snake_case 응답을 표시하고 신고 POST를 보낸다', async ({ page }) => {
  test.skip(!IS_REAL_API, '실 API 모드의 후기 조회·신고 계약을 확인합니다.');
  let reportMethod = '';
  await page.route('**/api/v1/med/nutr/2048', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 2048, food_code: 'REVIEW-2048', name: '후기 제품', basis_qty: '500mg',
        energy_kcal: 0, water_g: null, protein_g: null, fat_g: null, ash_g: null,
        carb_g: null, sugar_g: null, fiber_g: null, calcium_mg: null, iron_mg: null,
        phosphorus_mg: null, potassium_mg: null, sodium_mg: null, vitamin_a_ug_rae: null,
        retinol_ug: null, beta_carotene_ug: null, thiamine_mg: null, riboflavin_mg: null,
        niacin_mg: null, vitamin_c_mg: null, vitamin_d_ug: null, cholesterol_mg: null,
        sat_fat_g: null, trans_fat_g: null, serving_desc: '1정', serving_size: '500mg',
        daily_freq: '1회', target: '성인', rating_average: '4.0', review_count: 1,
      }),
    }),
  );
  await page.route('**/api/v1/med/user-suppl-nutr?*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null }),
    }),
  );
  await page.route('**/api/v1/med/nutr/2048/reviews?*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          id: 77,
          author_label: '김*훈',
          score: 4,
          review_body: '실 API 공개 후기',
          updated_at: '2026-09-01T12:00:00+09:00',
          is_mine: false,
          reported_by_me: false,
        }],
        total: 1,
        offset: 0,
        limit: 10,
        rating_average: '4.0',
        review_count: 1,
      }),
    }),
  );
  await page.route('**/api/v1/med/nutr/reviews/77/report', (route) => {
    reportMethod = route.request().method();
    return route.fulfill({ status: 204 });
  });

  await page.goto('/dev/supplements/product/2048');
  const card = page.getByRole('article', { name: '김*훈 후기' });
  await expect(card).toContainText('실 API 공개 후기');
  await expect(card).not.toContainText('note');
  await card.getByRole('button', { name: '신고' }).click();
  await page.getByRole('dialog', { name: '이 후기를 신고할까요?' })
    .getByRole('button', { name: '신고하기' }).click();

  expect(reportMethod).toBe('POST');
  await expect(card).toHaveCount(0);
});
