import { expect, test, type Page } from 'playwright/test';

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8+QAAAABJRU5ErkJggg==',
  'base64',
);

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'feature-carousel-e2e-token');
    window.sessionStorage.setItem('poke.account-principal', 'feature-carousel@example.com');
  });
}

test('홈 기능 배너는 compact 가로 레이아웃과 한 문장 제목을 사용한다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const carousel = page.getByRole('region', { name: 'RxVita 기능 소개' });
  const firstCard = carousel.locator('article').first();
  const carouselBox = await carousel.boundingBox();

  expect(carouselBox).not.toBeNull();
  expect(carouselBox!.height).toBeGreaterThanOrEqual(168);
  expect(carouselBox!.height).toBeLessThanOrEqual(180);
  expect(await firstCard.evaluate((element) => getComputedStyle(element).flexDirection)).toBe(
    'row',
  );
  expect(await firstCard.getByRole('heading').textContent()).toBe(
    '약봉투를 찍으면 먹을 시간을 알려드려요',
  );
  expect(
    await firstCard.locator('p').evaluate((element) => getComputedStyle(element).webkitLineClamp),
  ).toBe('1');
  await expect(carousel.locator('[aria-label^="현재 배너"]')).toHaveAttribute(
    'aria-label',
    '현재 배너 2 / 3',
    { timeout: 4_500 },
  );
});

test('OCR 읽는 중 기능 배너는 기본 full 높이와 세로 레이아웃을 유지한다', async ({ page }) => {
  await authenticate(page);
  await page.goto('/document-upload');
  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
    name: 'medication-envelope.png',
    mimeType: 'image/png',
    buffer: ONE_PIXEL_PNG,
  });
  await page.getByRole('button', { name: '등록하기' }).click();

  await expect(page.getByRole('heading', { name: '약봉투를 읽고 있어요' })).toBeVisible();
  const carousel = page.getByRole('region', { name: 'RxVita 기능 소개' });
  const carouselBox = await carousel.boundingBox();

  expect(carouselBox).not.toBeNull();
  expect(carouselBox!.height).toBeGreaterThanOrEqual(336);
  expect(
    await carousel
      .locator('article')
      .first()
      .evaluate((element) => getComputedStyle(element).flexDirection),
  ).toBe('column');
});
