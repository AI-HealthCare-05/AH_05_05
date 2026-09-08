import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';
test.skip(IS_REAL_API, MOCK_ONLY_REASON);
test.setTimeout(60_000);

for (const width of [390, 1280]) {
  test(`home ${width}px: hides only scrollbar and keeps wheel and keyboard scrolling`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', 'scrollbar-test-token');
      sessionStorage.setItem('poke.account-principal', 'scrollbar@example.com');
    });
    await page.goto('/home');
    const content = page.getByRole('main');
    await expect(content).toBeVisible();
    await expect(page.getByRole('heading', { name: '챌린지', exact: true })).toBeVisible();
    const style = await content.evaluate(element => ({ width: getComputedStyle(element).scrollbarWidth, gutter: getComputedStyle(element).scrollbarGutter, scrollable: element.scrollHeight > element.clientHeight }));
    expect(style).toEqual({ width: 'none', gutter: 'auto', scrollable: true });
    await content.hover();
    await page.mouse.wheel(0, 400);
    await expect.poll(() => content.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await content.evaluate(element => { element.scrollTop = 0; });
    await content.focus();
    await page.keyboard.press('End');
    await expect.poll(() => content.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
