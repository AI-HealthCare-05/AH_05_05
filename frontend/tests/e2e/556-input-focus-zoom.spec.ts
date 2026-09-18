import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
test.use({ isMobile: true, hasTouch: true, locale: 'ko-KR' });

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'focus-556-test');
    sessionStorage.setItem('poke.account-principal', 'focus-556@example.invalid');
  });
});

for (const width of [375, 390, 393, 414, 430]) {
  test(`메모 입력은 ${width}px에서 iOS 확대 유발 작은 글자를 사용하지 않는다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 852 });
    await page.goto('/medications/notes/new');
    await page.getByLabel('처방', { exact: true }).selectOption({ index: 1 });
    for (const name of ['처방', '복용 일시', '건강상태 기록']) {
      const control = page.getByLabel(name, { exact: true });
      await control.focus();
      // WebKit iOS focus scaling uses standardFontSize / fontSize.
      // This validates rendered CSS, not the actual iOS keyboard or scale.
      expect(await control.evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    }
  });
}
