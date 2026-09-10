import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.use({ viewport: { width: 390, height: 844 } });
test.setTimeout(30_000);

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '369-home-clay-fixture');
    sessionStorage.setItem('poke.account-principal', '369-home-clay@example.invalid');
  });
  // This suite uses in-memory dev fixtures; never forward an API request to a DB.
  await page.route('**/api/v1/**', route => route.abort());
  // Keep this isolated UI fixture independent of the external font stylesheet.
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.goto('/dev/home-multiple-episodes');
});

test('active tab has an inset mint surface without hiding labels or changing tab geometry', async ({ page }, testInfo) => {
  const nav = page.getByRole('navigation', { name: '주요 화면' });
  const buttons = nav.getByRole('button');
  await expect(buttons).toHaveText(['홈', '복약', '영양제', '챗봇', '마이']);
  const originalBoxes = await buttons.evaluateAll(items => items.map(item => {
    const { x, width, height } = item.getBoundingClientRect();
    return { x, width, height };
  }));
  expect(originalBoxes.map(box => box.width)).toEqual([78, 78, 78, 78, 78]);
  expect(originalBoxes.every(box => box.height >= 44)).toBe(true);
  await expect(nav).toHaveCSS('height', '64px');
  await page.screenshot({ path: testInfo.outputPath('369-home-clay-390.png') });
  const active = nav.getByRole('button', { name: '홈', exact: true });
  await expect(active).toHaveAttribute('aria-current', 'page');
  expect(await active.evaluate(element => getComputedStyle(element, '::before').backgroundColor)).toBe('rgb(221, 244, 241)');
  await active.focus();
  await page.keyboard.press('Tab');
  await expect(nav.getByRole('button', { name: '복약', exact: true })).toBeFocused();
  await nav.getByRole('button', { name: '챗봇', exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
  const chatNav = page.getByRole('navigation', { name: '주요 화면' });
  await expect(chatNav.getByRole('button')).toHaveText(['홈', '복약', '영양제', '챗봇', '마이']);
  await expect(chatNav.getByRole('button', { name: '챗봇', exact: true })).toHaveAttribute('aria-current', 'page');
  expect(await chatNav.getByRole('button').evaluateAll(items => items.map(item => {
    const { x, width, height } = item.getBoundingClientRect();
    return { x, width, height };
  }))).toEqual(originalBoxes);
});

test('clay selection stays distinct from completion and does not move the medication row', async ({ page }, testInfo) => {
  const morning = page.getByRole('group', { name: '아침약 상세', exact: true });
  const row = morning.locator('[data-episode-row]').first();
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  const title = await row.getByRole('heading').innerText();
  const before = await row.boundingBox();
  await row.click();
  await expect(row).toHaveAttribute('aria-pressed', 'true');
  await expect(row.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(row).toHaveCSS('box-shadow', /inset/);
  await expect(row.getByRole('heading')).toHaveText(title);
  expect(await row.boundingBox()).toEqual(before);
  const point = await row.boundingBox();
  await page.mouse.move(point!.x + 10, point!.y + 10);
  await page.mouse.down();
  await expect(row).toHaveCSS('transform', 'none');
  await page.mouse.up();
  await row.click();
  await morning.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(row.locator('[data-episode-completed-badge]')).toHaveText('복용 완료');
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await page.screenshot({ path: testInfo.outputPath('369-home-clay-complete-390.png') });
});

test('home primary card and raw memo action share the same rounded light-clay depth', async ({ page }) => {
  const medication = page.getByRole('region', { name: '오늘의 복약', exact: true });
  const primaryCard = medication.getByRole('group', { name: '아침약 상세', exact: true }).locator('..');
  await expect(primaryCard.locator(':scope > div:first-child > p')).toHaveCSS('color', 'rgb(0, 44, 104)');
  const cardShadow = await primaryCard.evaluate(element => getComputedStyle(element).boxShadow);
  expect((cardShadow.match(/inset/g) ?? []).length).toBeGreaterThanOrEqual(2);
  expect(cardShadow).toMatch(/0px -[4-9]px [6-9]px/);

  const memo = page.getByRole('button', { name: '복약 메모', exact: true });
  const memoAppearance = await memo.evaluate(element => {
    const style = getComputedStyle(element);
    return { backgroundImage: style.backgroundImage, boxShadow: style.boxShadow };
  });
  expect(memoAppearance.backgroundImage).not.toBe('none');
  expect((memoAppearance.boxShadow.match(/inset/g) ?? []).length).toBeGreaterThanOrEqual(2);
});

test('challenge tracks keep every title and percentage readable with reduced motion', async ({ page }, testInfo) => {
  const summary = page.getByRole('region', { name: '챌린지', exact: true });
  const links = summary.getByRole('link', { name: /% 달성, 상세 보기$/ });
  await expect(links.first()).toBeVisible();
  expect(await links.count()).toBeGreaterThan(1);
  const text = await links.allTextContents();
  const names = await links.evaluateAll(items => items.map(item => item.getAttribute('aria-label')));
  const track = links.first().locator('[aria-hidden]').last();
  await expect(track).toHaveCSS('box-shadow', /inset/);
  await expect(track).toHaveCSS('height', '8px');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(links).toHaveText(text);
  expect(await links.evaluateAll(items => items.map(item => item.getAttribute('aria-label')))).toEqual(names);
  const row = page.locator('[data-episode-row]').first();
  await expect(row).toHaveCSS('transition-duration', '0s');
  const activeTab = page.getByRole('navigation', { name: '주요 화면' }).locator('[aria-current]');
  expect(await activeTab.evaluate(element => getComputedStyle(element, '::before').transitionDuration)).toBe('0s');
  expect(await page.locator('main').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await summary.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('369-home-clay-challenges-reduced-390.png') });
});
