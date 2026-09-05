import { expect, test, type Page } from 'playwright/test';

test.beforeEach(async ({ page }) => {
  // These layout tests seed a local session, so all authenticated API dependencies
  // must use fixtures rather than sending the synthetic token to the real server.
  for (const path of [
    '**/api/v1/medications',
    '**/api/v1/medications/doses?**',
  ]) {
    await page.route(path, (route) => route.fulfill({ json: [] }));
  }
  for (const path of [
    '**/api/v1/med/user-suppl-nutr?**',
    '**/api/v1/user/follow-up-visits?**',
  ]) {
    await page.route(path, (route) =>
      route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } }),
    );
  }
  await page.route('**/api/v1/users/me', (route) =>
    route.fulfill({
      json: { name: '테스트 사용자', phoneNumber: '01012345678', birthDate: '1990-01-01', gender: 'female' },
    }),
  );
  await page.route('**/api/v1/med/nutr/sp-001', (route) =>
    route.fulfill({
      json: {
        id: 1,
        name: '센트룸 실버 우먼',
        serving_desc: '1정',
        serving_size: '90정',
        daily_freq: '1일 1회',
        target: null,
        rating_average: null,
        review_count: 0,
      },
    }),
  );
  await page.route('**/api/v1/med/nutr/*/reviews?**', (route) =>
    route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } }),
  );
  await page.route('**/api/v1/me/settings', (route) =>
    route.fulfill({
      json: {
        notifyMedication: false,
        notifySupplement: false,
        notifySchedule: false,
        notifyConsentedAt: null,
        morningMedicationTime: '08:00',
        lunchMedicationTime: '13:00',
        eveningMedicationTime: '19:00',
        bedtimeMedicationTime: '22:00',
      },
    }),
  );
});

async function seedAuthenticatedSession(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'e2e-tabbar-token');
    sessionStorage.setItem('poke.account-principal', 'patient@example.com');
  });
}

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
  await seedAuthenticatedSession(page);
  await page.goto('/dev/my-authenticated');
  await page.goto('/dev/my-profile');

  await expectTabbarWithoutOverlap(page, '마이');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/dev\/my-authenticated$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/dev\/my-profile$/);
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test('진료일정 화면은 마이 탭을 유지하며 다른 탭으로 이동한다', async ({ page }) => {
  await seedAuthenticatedSession(page);
  await page.goto('/dev/my-authenticated');
  await page.goto('/dev/my-visits');

  await expectTabbarWithoutOverlap(page, '마이');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/dev\/my-authenticated$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/dev\/my-visits$/);
  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page).toHaveURL(/\/supplements$/);
});

test('영양제 제품 상세 화면은 영양제 탭을 유지하며 다른 탭으로 이동한다', async ({ page }) => {
  await seedAuthenticatedSession(page);
  await page.goto('/dev/supplements?tab=browse');
  await page.goto('/dev/supplements/product/sp-001');

  await expectTabbarWithoutOverlap(page, '영양제');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/dev\/supplements\/product\/sp-001$/);
  await page.getByRole('button', { name: '복약', exact: true }).click();
  await expect(page).toHaveURL(/\/medications$/);
});

test('진행 중 흐름 화면에는 하단 탭바를 표시하지 않고 알림 시간은 마이페이지에서 연다', async ({ page }) => {
  for (const path of [
    '/dev/document-upload',
    '/dev/ocr-review',
    '/dev/medication-schedule',
    '/',
  ]) {
    await page.goto(path);
    await expect(page.getByRole('navigation', { name: '주요 화면' })).toHaveCount(0);
  }

  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await expect(page.getByRole('dialog', { name: '알림 시간' })).toBeVisible();
});
