import { expect, test, type ElementHandle, type Locator, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.skip(IS_REAL_API, MOCK_ONLY_REASON);
test.setTimeout(60_000);

type Viewport = { label: string; width: number; height: number };

const viewports: Viewport[] = [
  { label: 'mobile', width: 390, height: 480 },
  { label: 'desktop', width: 1280, height: 480 },
];

async function verticalScroller(
  page: Page,
  preferred: Locator,
): Promise<ElementHandle<HTMLElement>> {
  const preferredElement = await preferred.elementHandle();
  if (!preferredElement) throw new Error('The preferred scroll surface was not rendered.');

  const handle = await page.evaluateHandle((start) => {
    const candidates: Element[] = [];
    for (let current: Element | null = start; current; current = current.parentElement) {
      candidates.push(current);
    }

    const nested = Array.from(start.querySelectorAll('*'));
    const target = [...candidates, ...nested].find((element) => {
      const style = getComputedStyle(element);
      return (
        element.scrollHeight > element.clientHeight + 1 &&
        style.overflowY !== 'hidden' &&
        style.overflowY !== 'clip'
      );
    });

    return target ?? document.scrollingElement;
  }, preferredElement);
  const element = handle.asElement() as ElementHandle<HTMLElement> | null;
  if (!element) throw new Error('No vertical scroll surface was available.');
  return element;
}

async function expectHiddenScrollbar(target: ElementHandle<HTMLElement>, axis: 'x' | 'y') {
  const style = await target.evaluate((element, checkedAxis) => {
    const computed = getComputedStyle(element);
    const webkitScrollbar = getComputedStyle(element, '::-webkit-scrollbar');
    return {
      firefox: computed.scrollbarWidth,
      webkit: webkitScrollbar.display,
      overflow: checkedAxis === 'x' ? computed.overflowX : computed.overflowY,
      scrollable:
        checkedAxis === 'x'
          ? element.scrollWidth > element.clientWidth + 1
          : element.scrollHeight > element.clientHeight + 1,
    };
  }, axis);

  expect(style.scrollable).toBe(true);
  expect(style.overflow).not.toBe('hidden');
  expect(style.overflow).not.toBe('clip');
  expect(style.firefox).toBe('none');
  expect(style.webkit).toBe('none');
}

async function wheelScroll(
  page: Page,
  target: ElementHandle<HTMLElement>,
  axis: 'x' | 'y',
) {
  await target.evaluate((element, checkedAxis) => {
    if (checkedAxis === 'x') element.scrollLeft = 0;
    else element.scrollTop = 0;
  }, axis);

  const box = await target.boundingBox();
  if (!box) throw new Error('The scroll surface does not have a visible bounding box.');
  const viewport = page.viewportSize();
  if (!viewport) throw new Error('The viewport was not configured.');
  await page.mouse.move(
    Math.min(viewport.width - 2, Math.max(2, box.x + Math.min(box.width / 2, viewport.width / 2))),
    Math.min(viewport.height - 2, Math.max(2, box.y + Math.min(box.height / 2, viewport.height / 2))),
  );
  await page.mouse.wheel(axis === 'x' ? 500 : 0, axis === 'y' ? 500 : 0);

  await expect
    .poll(() =>
      target.evaluate((element, checkedAxis) =>
        checkedAxis === 'x' ? element.scrollLeft : element.scrollTop,
      axis),
    )
    .toBeGreaterThan(0);
}

for (const viewport of viewports) {
  test(`${viewport.label}: app pages hide bars while vertical scrolling still moves`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', 'scrollbar-test-token');
      sessionStorage.setItem('poke.account-principal', 'scrollbar@example.com');
    });

    const pages = [
      { path: '/dev/home-14-days', ready: '챌린지', preferred: 'main' },
      { path: '/dev/medications-many', ready: '복약', preferred: 'main' },
      { path: '/dev/my-authenticated', ready: '마이페이지', preferred: 'main' },
      { path: '/dev/challenges', ready: '챌린지', preferred: '.overflow-y-auto' },
    ];

    for (const surface of pages) {
      await page.goto(surface.path);
      await expect(page.getByRole('heading', { name: surface.ready, exact: true })).toBeVisible();
      const scroller = await verticalScroller(page, page.locator(surface.preferred).first());
      await expectHiddenScrollbar(scroller, 'y');
      await wheelScroll(page, scroller, 'y');
    }
  });

  test(`${viewport.label}: portal sheet and horizontal legal content hide bars and still scroll`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto('/dev/my-authenticated');
    await page.getByRole('button', { name: '알림 시간 설정' }).click();

    const sheet = page.getByRole('dialog', { name: '알림 시간' });
    await expect(sheet).toBeVisible();
    expect(await sheet.evaluate((element) => element.parentElement === document.body)).toBe(true);
    const sheetScroller = await sheet.elementHandle();
    if (!sheetScroller) throw new Error('The portal sheet was not rendered.');
    await expectHiddenScrollbar(sheetScroller, 'y');
    await wheelScroll(page, sheetScroller, 'y');
    await sheet.getByRole('button', { name: '닫기' }).focus();
    await expect(sheet.getByRole('button', { name: '닫기' })).toBeFocused();

    await page.goto('/privacy');
    const horizontalRegion = page.locator('.overflow-x-auto').first();
    await expect(horizontalRegion).toBeVisible();
    await horizontalRegion.scrollIntoViewIfNeeded();
    const horizontalScroller = await horizontalRegion.elementHandle();
    if (!horizontalScroller) throw new Error('The horizontal scroll region was not rendered.');
    await expectHiddenScrollbar(horizontalScroller, 'x');
    await wheelScroll(page, horizontalScroller, 'x');
  });
}

test('home keeps keyboard scrolling and its visible focus indicator', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 480 });
  await page.goto('/dev/home-14-days');
  const content = page.getByRole('main', { name: '홈 콘텐츠' });
  await expect(content).toBeVisible();
  await content.evaluate((element) => {
    element.scrollTop = 0;
  });
  await content.focus();
  await expect(content).toBeFocused();
  expect(await content.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe(
    'none',
  );
  await page.keyboard.press('End');
  await expect.poll(() => content.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
});
