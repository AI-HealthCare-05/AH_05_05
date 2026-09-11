import { expect, test } from 'playwright/test';

test.skip(process.env.VITE_USE_MOCK !== 'false', 'Uses isolated public ranking responses.');
test.setTimeout(45_000);

for (const ranked of [false, true]) {
  test(`guest cards share a readable aligned column with ranking ${ranked ? 'visible' : 'absent'} across viewport changes`, async ({ page }, testInfo) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/api/v1/display/med/nutr/rank', route => route.fulfill({
      status: ranked ? 200 : 404,
      json: ranked ? {
        display_id: 369, title: '현재 인기 영양제', start_at: '2026-09-01T00:00:00+09:00',
        end_at: '2026-09-30T23:59:59+09:00', is_enabled: true, created_by_admin_id: 1,
        created_at: '2026-09-01T00:00:00+09:00', updated_at: null,
        items: [{ supplement_nutrient_id: 11, name: '전시 비타민', rank_no: 1 }],
      } : { code: 'SUPPLEMENT_RANK_DISPLAY_NOT_FOUND' },
    }));
    const loaded = page.waitForResponse('**/api/v1/display/med/nutr/rank');
    await page.goto('/home');
    await loaded;
    const prompt = page.getByRole('region', { name: '오늘의 복약', exact: true });
    const carousel = page.getByRole('region', { name: 'RxVita 기능 소개' });
    const ranking = page.getByRole('region', { name: '영양제 랭킹' });
    await expect(ranking).toHaveCount(ranked ? 1 : 0);
    for (const width of [1488, 1024, 1920, 390, 768]) {
      await page.setViewportSize({ width, height: 1000 });
      const a = (await prompt.boundingBox())!;
      const b = (await carousel.boundingBox())!;
      expect.soft(Math.abs(a.x - b.x), `left alignment at ${width}`).toBeLessThan(2);
      expect.soft(Math.abs(a.width - b.width), `equal section widths at ${width}`).toBeLessThan(2);
      expect.soft(b.y).toBeGreaterThan(a.y + a.height);
      if (width >= 1024) {
        expect.soft(a.width).toBeLessThanOrEqual(640);
        expect.soft(Math.abs(a.x + a.width / 2 - width / 2)).toBeLessThan(2);
        const scroller = carousel.locator('div').first();
        const scrollBox = (await scroller.boundingBox())!;
        expect.soft(scrollBox.x + scrollBox.width).toBeLessThanOrEqual(a.x + a.width + 1);
      }
      if (ranked) {
        const r = (await ranking.boundingBox())!;
        expect.soft(Math.abs(a.x - r.x)).toBeLessThan(2);
        expect.soft(Math.abs(a.width - r.width)).toBeLessThan(2);
      }
      await expect(page.getByRole('navigation', { name: '주요 화면' })).toBeInViewport({ ratio: 1 });
      expect.soft(await page.locator('main').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`guest-${ranked}-${width}.png`) });
    }
    await page.getByRole('button', { name: '로그인하고 시작하기' }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
}
