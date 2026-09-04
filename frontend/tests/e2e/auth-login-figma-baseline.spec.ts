import { expect, test } from 'playwright/test';

test('로그인 기본 화면은 Figma 모바일 기준 레이아웃을 제공한다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/login');

  await expect(page.getByRole('heading', { name: '로그인 · 회원가입' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '다시 만나서 반가워요' })).toBeVisible();
  await expect(
    page.getByText('로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.'),
  ).toBeVisible();
  await expect(page.getByLabel('이메일')).toBeVisible();
  await expect(page.getByLabel('비밀번호')).toBeVisible();
  await expect(page.getByRole('navigation', { name: '주요 화면' })).toHaveCount(0);
  await expect(page.getByAltText('RxVita')).toHaveCount(0);
  await expect(page.getByRole('link', { name: '이용약관' })).toBeVisible();
  await expect(page.getByRole('link', { name: '개인정보 처리 안내' })).toBeVisible();

  const headerBox = await page.getByRole('banner').boundingBox();
  const emailBox = await page.getByLabel('이메일').boundingBox();
  const passwordBox = await page.getByLabel('비밀번호').boundingBox();
  const loginButtonBox = await page
    .getByRole('button', { name: '로그인', exact: true })
    .last()
    .boundingBox();

  expect(headerBox?.height).toBe(64);
  expect(emailBox?.height).toBe(52);
  expect(passwordBox?.height).toBe(52);
  expect(loginButtonBox?.height).toBe(52);

  const appBox = await page.locator('#root > div').first().boundingBox();
  expect(appBox?.width).toBe(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect(await page.evaluate(() => document.body.scrollWidth)).toBe(390);
});
