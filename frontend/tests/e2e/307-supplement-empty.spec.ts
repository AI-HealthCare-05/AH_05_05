import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => test.skip(IS_REAL_API, MOCK_ONLY_REASON));
// Includes Vite cold start on the WSL-mounted checkout.
test.setTimeout(60_000);

test('모든 영양제를 선택 삭제하면 등록 안내만 보여주고 성분 합계는 완전히 숨긴다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'empty-list-test');
    sessionStorage.setItem('poke.account-principal', 'empty-list@example.com');
  });
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [], totalCount: 0 } }));
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });

  await page.getByRole('button', { name: '선택', exact: true }).click();
  for (const checkbox of await supplementList.getByRole('checkbox').all()) await checkbox.check();
  await page.getByRole('button', { name: '삭제 3개', exact: true }).click();

  await expect(
    page.getByRole('heading', { name: '영양제를 등록하고 관리하기', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: '성분 합계', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '성분 합계' })).toHaveCount(0);

  await supplementList.getByRole('button', { name: '영양제 추가', exact: true }).click();
  await expect(page.getByRole('searchbox', { name: '영양제 제품 검색' })).toBeVisible();
});

test('등록한 영양제가 있으면 기존 성분 합계를 계속 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');

  await expect(page.getByRole('region', { name: '성분 합계' })).toBeVisible();
});
