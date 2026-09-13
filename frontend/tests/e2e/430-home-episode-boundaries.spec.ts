import { expect, test, type Locator, type Page, type Route } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const names = ['늘푸른내과의원', '해맑은소아청소년과의원진료센터긴이름', '세번째 의원'];
const overviews = names.map((alias, index) => ({
  recordId: 430 + index, alias, documentImageUrl: null,
  start: { date: `2026-09-${12 - index}`, slot: 'morning' },
  endDate: '2026-09-20', daysRemaining: 9, isFinished: false,
  mealTimes: { morning: '09:30', lunch: '13:00', evening: '20:00', bedtime: '22:00' },
  medications: (index === 0 ? ['아세트아미노펜정500mg', '세티리진정10mg', '암브록솔정30mg', '파모티딘정20mg'] : ['암브록솔시럽', '프로바이오틱스분말긴이름줄바꿈확인용']).map((name, item) => ({
    medicationId: 4300 + index * 10 + item, name, dose: '1정', days: 14,
    daysRemaining: 9, slots: ['morning'], asNeeded: false,
  })),
}));
type Dose = { recordId: number; date: string; slot: string; taken: boolean };
async function json(route: Route, body: unknown) {
  await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
}
async function setup(page: Page, count = 2) {
  await page.clock.setFixedTime(new Date('2026-09-12T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'boundaries-fixture-token');
    sessionStorage.setItem('poke.account-principal', 'boundaries-fixture@example.com');
  });
  await page.route(/\/api\/v1\//, route => json(route, {}));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, route => json(route, overviews.slice(0, count)));
  await page.route('**/api/v1/med/user-suppl-nutr*', route => json(route, { items: [], total: 0, offset: 0, limit: 100 }));
  await page.route('**/api/v1/med/supplement-doses*', route => json(route, []));
  await page.route('**/api/v1/display/med/nutr/rank*', route => json(route, { items: [] }));
  await page.route('**/api/v1/user/challenges*', route => json(route, { items: [], totalCount: 0 }));
  await page.route('**/api/v1/user/custom-challenge-participations*', route => json(route, { items: [], totalCount: 0 }));
  const writes: Dose[] = [];
  const records: Dose[] = [];
  const releases: Array<() => void> = [];
  await page.route('**/api/v1/medications/doses*', async route => {
    if (route.request().method() === 'GET') return json(route, records);
    const body = route.request().postDataJSON() as Dose;
    writes.push(body);
    await new Promise<void>(resolve => { releases.push(resolve); });
    const previous = records.findIndex(item => item.recordId === body.recordId);
    if (previous >= 0) records.splice(previous, 1);
    if (body.taken) records.push(body);
    await json(route, body);
  });
  await page.goto('/home');
  const group = page.getByRole('group', { name: '아침약 상세' });
  await expect(group.getByRole('article')).toHaveCount(Math.min(count, 2));
  return { group, writes, release: () => releases.splice(0).forEach(resolve => resolve()) };
}
async function enclosed(article: Locator) {
  const result = await article.evaluate(element => {
    const style = getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    const row = element.querySelector('[data-episode-row]')!;
    const rowStyle = getComputedStyle(row);
    const detail = element.querySelector('[id^="episode-detail-"]');
    const children = [row, ...(detail ? [detail] : [])];
    return {
      widths: [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth],
      styles: [style.borderTopStyle, style.borderRightStyle, style.borderBottomStyle, style.borderLeftStyle],
      color: style.borderTopColor,
      contained: children.every(child => { const box = child.getBoundingClientRect(); return box.left >= bounds.left && box.right <= bounds.right && box.top >= bounds.top && box.bottom <= bounds.bottom; }),
      rowBottom: rowStyle.borderBottomWidth, rowRadius: rowStyle.borderRadius, rowShadow: rowStyle.boxShadow,
    };
  });
  expect(result.widths).toEqual(['1px', '1px', '1px', '1px']);
  expect(result.styles).toEqual(['solid', 'solid', 'solid', 'solid']);
  expect(result.color).not.toBe('rgba(0, 0, 0, 0)');
  expect(result.contained).toBe(true);
  expect(result.rowBottom).toBe('0px');
  expect(result.rowRadius).toBe('0px');
  // Tailwind composes an invisible zero-size shadow with its focus ring variables.
  expect(result.rowShadow === 'none' || result.rowShadow
    .replaceAll('rgba(0, 0, 0, 0)', '').replace(/0px|[\s,]/g, '') === '').toBe(true);
}
test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));
for (const width of [320, 390, 1280]) {
  test(`처방 전체를 감싸는 경계와 두 열린 처방 간격 (${width}px)`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const { group } = await setup(page);
    const articles = group.getByRole('article');
    for (const article of await articles.all()) {
      await enclosed(article);
      const expand = article.getByRole('button', { name: /처방 펼치기$/ });
      const box = await expand.boundingBox();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
      await expand.click();
      await expect(article.locator('[data-episode-row]')).toHaveAttribute('aria-pressed', 'false');
      await enclosed(article);
    }
    const [first, second] = await Promise.all([articles.nth(0).boundingBox(), articles.nth(1).boundingBox()]);
    expect(second!.y - first!.y - first!.height).toBeGreaterThanOrEqual(12);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('img:visible').evaluateAll(async images => {
      await Promise.all(images.map(image => (image as HTMLImageElement).decode()));
      if (images.some(image => !(image as HTMLImageElement).naturalWidth)) throw new Error('Undecoded image');
    });
    await page.mouse.move(0, 0);
    await page.locator('[data-home-dose-card]').screenshot({ path: info.outputPath(`430-home-episode-boundaries-${width}.png`) });
  });
}
test('한 처방도 접힘과 키보드 펼침·선택이 독립적이다', async ({ page }) => {
  const { group } = await setup(page, 1);
  const article = group.getByRole('article');
  await enclosed(article);
  const expand = article.locator('button[aria-expanded]');
  await expand.focus();
  await page.keyboard.press('Enter');
  await expect(expand).toHaveAttribute('aria-expanded', 'true');
  const selection = article.locator('[data-episode-row]');
  await expect(selection).toHaveAttribute('aria-pressed', 'false');
  await selection.focus();
  await page.keyboard.press('Space');
  await expect(selection).toHaveAttribute('aria-pressed', 'true');
  expect(await selection.evaluate(element => getComputedStyle(element).boxShadow)).toContain('2px');
  await expect(expand).toHaveAttribute('aria-expanded', 'true');
  await expand.click();
  await expect(article.getByRole('list')).toHaveCount(0);
});
test('대기 중 선택 차단과 일부·전체 완료·되돌리기 및 세 번째 처방 경계를 유지한다', async ({ page }) => {
  const { group, writes, release } = await setup(page, 3);
  await group.getByRole('button', { name: '다른 처방 펼치기' }).click();
  const articles = group.getByRole('article');
  await expect(articles).toHaveCount(3);
  for (const article of await articles.all()) await enclosed(article);
  const first = articles.nth(0);
  await first.locator('[data-episode-row]').click();
  await group.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({ recordId: 430, date: '2026-09-12', slot: 'morning', taken: true });
  for (const row of await group.locator('[data-episode-row]').all()) await expect(row).toBeDisabled();
  release();
  await expect(first.locator('[data-episode-row]')).toBeEnabled();
  await expect(group.locator('[data-episode-completed-badge]')).toHaveCount(1);
  await group.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect.poll(() => writes.length).toBe(3);
  release();
  await expect(first.locator('[data-episode-row]')).toBeEnabled();
  await expect(group.locator('[data-episode-completed-badge]')).toHaveCount(3);
  for (const article of await articles.all()) {
    const badge = await article.locator('[data-episode-completed-badge]').boundingBox();
    const title = await article.getByRole('heading').boundingBox();
    expect(badge!.y + badge!.height).toBeLessThanOrEqual(title!.y);
  }
  await first.locator('[data-episode-row]').click();
  await group.getByRole('button', { name: '복약 기록 되돌리기' }).click();
  await expect.poll(() => writes.length).toBe(4);
  expect(writes[3]).toEqual({ recordId: 430, date: '2026-09-12', slot: 'morning', taken: false });
  release();
  await expect(first.locator('[data-episode-row]')).toBeEnabled();
  await expect(group.locator('[data-episode-completed-badge]')).toHaveCount(2);
  await group.getByRole('button', { name: '다른 처방 접기' }).click();
  await expect(articles).toHaveCount(2);
});
