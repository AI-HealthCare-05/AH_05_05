import { expect, test } from 'playwright/test';

test('영양제 기본 화면은 내 영양제이고 쿼리로 둘러보기를 연다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await expect(tabs.getByRole('button', { name: '내 영양제' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
  await expect(page.getByLabel('영양제 추가', { exact: true })).toBeVisible();

  await page.goto('/dev/supplements?tab=browse');

  await expect(tabs.getByRole('button', { name: '둘러보기' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByLabel('영양제 추가', { exact: true })).toBeVisible();
});

test('탭을 반복해서 바꿔도 replace 이동이라 브라우저 이력이 쌓이지 않는다', async ({ page }) => {
  await page.goto('/dev/gallery');
  await page.goto('/dev/supplements');

  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await tabs.getByRole('button', { name: '둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);
  await tabs.getByRole('button', { name: '내 영양제' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements$/);
  await tabs.getByRole('button', { name: '둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/dev\/gallery$/);
});

test('둘러보기에서 내 영양제로 돌아오면 기존 목록과 성분 합계가 그대로 보인다', async ({
  page,
}) => {
  await page.goto('/dev/supplements?tab=browse');

  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await tabs.getByRole('button', { name: '내 영양제' }).click();

  await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: '성분 합계' })).toBeVisible();
  await expect(page.getByText(/등록한 건강기능식품 .*개만 더한 값입니다/)).toBeVisible();
});
