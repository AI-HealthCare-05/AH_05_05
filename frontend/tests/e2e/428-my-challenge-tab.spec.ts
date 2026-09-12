import { expect, test } from 'playwright/test';

import { waitForVisibleImages } from './helpers/visibleImages';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'challenge-tab-fixture');
    sessionStorage.setItem('poke.account-principal', 'challenge-tab@example.com');
  });
  await page.route(url => /^\/(api|media)(\/|$)/.test(url.pathname),
    route => route.fulfill({ status: 503, json: { message: 'Fixture not defined' } }));
  for (const path of ['challenges', 'badges']) {
    await page.route(`**/api/v1/user/${path}`, route => route.fulfill({ json: { items: [], total_count: 0 } }));
  }
  for (const path of ['custom-challenge-participations', 'custom-challenge-recommendations', 'custom-challenges/badges']) {
    await page.route(`**/api/v1/user/${path}`, route => route.fulfill({ json: { items: [], totalCount: 0 } }));
  }
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [], total_count: 0, offset: 0, limit: 100 },
  }));
});

for (const base of ['/challenges', '/dev/challenges']) {
  for (const width of [320, 390, 1280]) {
    test(`${base} 나의 챌린지 탭이 경로와 선택 상태를 유지한다 (${width}px)`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(base);
      const tabs = page.getByRole('navigation', { name: '챌린지 보기', exact: true });
      await expect(tabs).toBeVisible({ timeout: 60_000 });
      const my = tabs.getByRole('link', { name: '나의 챌린지', exact: true });
      const browse = tabs.getByRole('link', { name: '둘러보기', exact: true });
      await expect(my).toBeVisible();
      await expect(my).toHaveAttribute('href', base);
      await expect(my).toHaveAttribute('aria-current', 'page');
      await expect(browse).toHaveAttribute('href', `${base}/browse`);
      await expect(browse).not.toHaveAttribute('aria-current', 'page');
      await expect(tabs.getByRole('link', { name: '마이', exact: true })).toHaveCount(0);
      await expect(page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '마이', exact: true })).toBeVisible();
      expect(await tabs.evaluate(nav => [...nav.querySelectorAll('a')].every(link =>
        link.scrollWidth <= link.clientWidth && link.scrollHeight <= link.clientHeight,
      ) && nav.scrollWidth <= nav.clientWidth)).toBe(true);
      await waitForVisibleImages(page);
      await page.screenshot({ path: testInfo.outputPath(`my-${width}.png`), animations: 'disabled' });

      await browse.click();
      await expect(page).toHaveURL(`${base}/browse`);
      await expect(my).toBeVisible();
      await expect(my).not.toHaveAttribute('aria-current', 'page');
      await expect(browse).toHaveAttribute('aria-current', 'page');
      await expect(tabs.getByRole('link', { name: '마이', exact: true })).toHaveCount(0);
      expect(await tabs.evaluate(nav => nav.scrollWidth <= nav.clientWidth)).toBe(true);
      await waitForVisibleImages(page);
      await page.screenshot({ path: testInfo.outputPath(`browse-${width}.png`), animations: 'disabled' });

      await my.click();
      await expect(page).toHaveURL(base);
      await expect(my).toHaveAttribute('aria-current', 'page');
    });
  }
}
