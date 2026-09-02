import { expect, test, type Page } from 'playwright/test';

async function expectTabbarWithoutOverlap(page: Page, activeTab: string) {
  const navigation = page.getByRole('navigation', { name: '주요 화면' });
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole('button')).toHaveCount(5);
  await expect(
    navigation.getByRole('button', { name: activeTab, exact: true }),
  ).toHaveAttribute('aria-current', 'page');

  const layout = await page.evaluate(async () => {
    const main = document.querySelector('main');
    const navigationElement = document.querySelector('nav[aria-label="주요 화면"]');
    if (!(main instanceof HTMLElement) || !(navigationElement instanceof HTMLElement)) {
      throw new Error('페이지 본문과 하단 탭바를 찾지 못했습니다.');
    }

    main.scrollTop = main.scrollHeight;
    window.scrollTo(0, document.documentElement.scrollHeight);
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

    const lastContent = main.lastElementChild;
    if (!(lastContent instanceof HTMLElement)) {
      throw new Error('페이지 본문의 마지막 콘텐츠를 찾지 못했습니다.');
    }

    const navigationRect = navigationElement.getBoundingClientRect();
    return {
      lastContentBottom: lastContent.getBoundingClientRect().bottom,
      navigationBottom: navigationRect.bottom,
      navigationTop: navigationRect.top,
      scrollWidth: document.documentElement.scrollWidth,
      viewportHeight: window.innerHeight,
      viewportWidth: window.innerWidth,
    };
  });

  expect(layout.viewportWidth).toBe(375);
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.navigationTop).toBeGreaterThanOrEqual(0);
  expect(layout.navigationBottom).toBeLessThanOrEqual(layout.viewportHeight + 1);
  expect(layout.lastContentBottom).toBeLessThanOrEqual(layout.navigationTop + 1);
}

test('기본정보 수정 화면은 마이 탭을 유지하며 다른 탭으로 이동한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.goto('/my/profile');

  await expectTabbarWithoutOverlap(page, '마이');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/dev\/my-authenticated$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/my\/profile$/);
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test('진료일정 화면은 마이 탭을 유지하며 다른 탭으로 이동한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.goto('/my/visits');

  await expectTabbarWithoutOverlap(page, '마이');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/dev\/my-authenticated$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/my\/visits$/);
  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page).toHaveURL(/\/supplements$/);
});

test('영양제 제품 상세 화면은 영양제 탭을 유지하며 다른 탭으로 이동한다', async ({ page }) => {
  await page.goto('/dev/supplements?tab=browse');
  await page.goto('/supplements/product/sp-001');

  await expectTabbarWithoutOverlap(page, '영양제');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/supplements\/product\/sp-001$/);
  await page.getByRole('button', { name: '복약', exact: true }).click();
  await expect(page).toHaveURL(/\/medications$/);
});

test('진행 중 흐름 화면에는 하단 탭바를 표시하지 않는다', async ({ page }) => {
  for (const path of [
    '/dev/document-upload',
    '/dev/ocr-review',
    '/dev/medication-schedule',
    '/dev/medication-alarm-times',
    '/',
  ]) {
    await page.goto(path);
    await expect(page.getByRole('navigation', { name: '주요 화면' })).toHaveCount(0);
  }
});
