import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(60_000);
const widths = [320, 390, 768, 1280, 1440];

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '369-responsive-fixture');
    sessionStorage.setItem('poke.account-principal', '369-responsive@example.invalid');
  });
  await page.route('**/api/v1/**', route => route.abort());
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
});

async function expectNoOverflow(page: Page) {
  const overflowing = await page.locator('html, main, header, nav[aria-label="주요 화면"], [role="dialog"]').evaluateAll(elements =>
    elements.filter(element => element.scrollWidth > element.clientWidth + 1)
      .map(element => ({ tag: element.tagName, label: element.getAttribute('aria-label'), width: element.clientWidth, scroll: element.scrollWidth })),
  );
  expect.soft(overflowing).toEqual([]);
}

test('resizing home expands usable content and reflows supporting sections without changing mobile order', async ({ page }, testInfo) => {
  await page.goto('/dev/home-multiple-episodes');
  await expect(page.getByRole('region', { name: '오늘의 복약', exact: true })).toBeVisible();
  const metrics = [];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    const shell = await page.locator('.rx-home').boundingBox();
    const header = await page.locator('header').boundingBox();
    const nav = page.getByRole('navigation', { name: '주요 화면' });
    const navBox = await nav.boundingBox();
    const medication = await page.getByRole('region', { name: '오늘의 복약', exact: true }).boundingBox();
    const challenge = await page.getByRole('region', { name: '챌린지', exact: true }).boundingBox();
    metrics.push({ width, shell, medication, challenge });
    await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`) });
    expect.soft(shell!.width).toBeGreaterThanOrEqual(width < 1024 ? width - 32 : 1000);
    expect.soft(header!.x).toBeCloseTo(shell!.x, 0);
    expect.soft(header!.width).toBeCloseTo(shell!.width, 0);
    expect.soft(navBox!.x).toBeCloseTo(shell!.x, 0);
    expect.soft(navBox!.width).toBeCloseTo(shell!.width, 0);
    await expect(nav.getByRole('button')).toHaveText(['홈', '복약', '영양제', '챌린지', '마이']);
    if (width >= 1024) {
      expect.soft(challenge!.x).toBeGreaterThanOrEqual(medication!.x + medication!.width);
      expect.soft(Math.abs(challenge!.y - medication!.y)).toBeLessThan(2);
    } else {
      expect.soft(challenge!.y).toBeGreaterThan(medication!.y);
    }
    await expectNoOverflow(page);
  }
  await testInfo.attach('viewport-metrics', { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
});

test('badge collection uses additional columns on tablet and desktop', async ({ page }, testInfo) => {
  await page.goto('/dev/challenges/badges');
  const badges = page.getByRole('list', { name: '챌린지 배지' });
  await expect(badges).toBeVisible();
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    const columns = await badges.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length);
    expect.soft(columns).toBeGreaterThanOrEqual(width >= 1024 ? 4 : width >= 768 ? 3 : 2);
    await expectNoOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`badges-${width}.png`) });
  }
});

test('dialogs and sheets fit narrow screens and retain centered readable widths on desktop', async ({ page }, testInfo) => {
  await page.goto('/tests/harness/ui-motion.html');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const width of widths) {
    await page.setViewportSize({ width, height: 700 });
    for (const kind of ['확인창', '시트']) {
      const trigger = page.getByRole('button', { name: `${kind} 열기`, exact: true });
      await trigger.click();
      const dialog = page.getByRole('dialog', { name: kind, exact: true });
      const box = (await dialog.boundingBox())!;
      expect.soft(box.x).toBeGreaterThanOrEqual(0);
      expect.soft(box.x + box.width).toBeLessThanOrEqual(width);
      expect.soft(box.x + box.width / 2).toBeCloseTo(width / 2, 0);
      expect.soft(box.width).toBeLessThanOrEqual(640);
      if (width >= 768) expect.soft(box.width).toBeGreaterThan(390);
      await expect(dialog).toHaveCSS('animation-name', 'none');
      await expectNoOverflow(page);
      await page.screenshot({ path: testInfo.outputPath(`${kind}-${width}.png`) });
      await page.keyboard.press('Escape');
      await expect(trigger).toBeFocused();
    }
  }
});

for (const route of ['/home', '/dev/medications', '/dev/supplements', '/dev/chat-history', '/dev/my-authenticated', '/login']) {
  test(`${route} remains usable at mobile, tablet and desktop widths`, async ({ page }, testInfo) => {
    await page.goto(route);
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('[role="status"][aria-label*="불러오는 중"]')).toHaveCount(0);
    if (route === '/dev/supplements') await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      await expectNoOverflow(page);
      const main = (await page.locator('main').boundingBox())!;
      expect.soft(main.x).toBeGreaterThanOrEqual(0);
      expect.soft(main.x + main.width).toBeLessThanOrEqual(width + 1);
      if (width >= 768) expect.soft(main.width).toBeGreaterThan(600);
      await page.screenshot({ path: testInfo.outputPath(`page-${width}.png`) });
    }
  });
}

test('expanded home medication stays readable while resizing and reduced motion stays static', async ({ page }) => {
  await page.goto('/dev/home-multiple-episodes');
  const morning = page.getByRole('group', { name: '아침약 상세', exact: true });
  await morning.getByRole('button', { name: /처방 펼치기$/ }).first().click();
  const article = morning.locator('article').first();
  const expandedText = await article.textContent();
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    expect(await article.textContent()).toBe(expandedText);
    expect(await article.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expectNoOverflow(page);
  }
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('[data-episode-row]').first()).toHaveCSS('transition-duration', '0s');
});
