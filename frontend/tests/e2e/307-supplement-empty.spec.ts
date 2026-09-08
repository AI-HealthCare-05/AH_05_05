import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => test.skip(IS_REAL_API, MOCK_ONLY_REASON));
// Includes Vite cold start on the WSL-mounted checkout and three stop flows.
test.setTimeout(60_000);

test('마지막 영양제를 중단하면 등록 안내만 보여주고 성분 합계는 완전히 숨긴다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });

  for (const name of ['오메가3', '종합비타민', '비타민 D']) {
    await supplementList.getByRole('button', { name: new RegExp(name) }).click();
    const editSheet = page.getByRole('dialog', { name });
    await editSheet.getByRole('button', { name: '복용 중단하기' }).click();
    const confirm = page.getByRole('dialog', { name: `${name} 복용을 중단할까요?` });
    await confirm.getByRole('button', { name: '중단하기' }).click();
  }

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
