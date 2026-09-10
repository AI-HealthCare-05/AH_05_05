import { expect, test, type Locator, type Page } from 'playwright/test';
import type { CustomChallengeParticipation } from '../../src/entities/custom-challenge';

test.skip(process.env.VITE_USE_MOCK !== 'false', 'Uses isolated API fixtures.');
test.setTimeout(60_000);

function participation(count = 4, type: 'MEDICATION' | 'SUPPLEMENT' = 'MEDICATION'): CustomChallengeParticipation {
  return {
    id: 701, templateId: 31, challengeType: type, challengeName: '매일 챙기는 건강 루틴',
    rewardBadge: null, status: 'ACTIVE', joinedAt: '2026-09-08T16:00:00Z',
    endAt: '2026-09-12T23:59:59+09:00', actualEndDate: '2026-09-12',
    targetCount: count * 3, completedCount: count + 1, progressRate: '40.00', action: 'NONE',
    targets: [{ id: 801, sourceId: 101, name: '아주 긴 이름의 처방과 영양제 VitaminSupplementWithoutSpacesForWrapping1234567890' }],
    occurrences: ['2026-09-09', '2026-09-10', '2026-09-11'].flatMap((date, day) =>
      Array.from({ length: count }, (_, index) => ({
        id: 900 + day * 20 + index, targetId: 801, scheduledDate: date,
        slot: (['MORNING', 'LUNCH', 'EVENING', 'BEDTIME'] as const)[index % 4],
        scheduledAt: `${date}T${String(8 + index).padStart(2, '0')}:00:00+09:00`,
        isCompleted: day === 0 || (day === 1 && index === 0),
      }))),
  };
}

async function openCalendar(page: Page, item: CustomChallengeParticipation) {
  const unexpected: string[] = [];
  await page.clock.setFixedTime(new Date('2026-09-10T09:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'date-strip-fixture');
    sessionStorage.setItem('poke.account-principal', 'calendar@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  // Match actual API pathnames: a broad **/api/** also intercepts Vite source modules.
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/user/custom-challenge-participations/701') return route.fulfill({ json: item });
    if (request.method() === 'GET' && path === '/api/v1/user/custom-challenges/badges') return route.fulfill({ json: { items: [], totalCount: 0 } });
    unexpected.push(`${request.method()} ${path}`);
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('/challenges/custom-participations/701');
  const calendar = page.getByRole('region', { name: '챌린지 달력', exact: true });
  await expect(calendar).toBeVisible();
  return { calendar, unexpected };
}

async function swipe(area: Locator, deltaX: number, deltaY = 0) {
  await area.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 180, clientY: 150, button: 0 });
  await area.dispatchEvent('pointerup', { pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 180 + deltaX, clientY: 150 + deltaY, button: 0 });
}

for (const count of [1, 2, 3, 4, 7]) {
  test(`date strip immediately exposes all ${count} actual records with read-only states`, async ({ page }) => {
    const { calendar, unexpected } = await openCalendar(page, participation(count));
    await expect(calendar.getByRole('heading', { name: '9월 10일' })).toBeVisible();
    await expect(calendar.getByRole('list', { name: '선택한 날짜의 복용 기록' }).getByRole('listitem')).toHaveCount(count);
    const records = calendar.getByRole('listitem');
    for (const record of await records.all()) await expect(record).toBeVisible();
    await expect(records.first()).toContainText('완료');
    if (count > 1) await expect(records.last()).toContainText('예정');
    await expect(calendar.getByRole('checkbox')).toHaveCount(0);
    await expect(calendar.locator('details')).toHaveCount(0);
    await expect(records.locator('button')).toHaveCount(0);
    await records.last().click();
    await expect(calendar.getByRole('button', { pressed: true })).toHaveAttribute('aria-current', 'date');
    expect(unexpected).toEqual([]);
  });
}

for (const type of ['MEDICATION', 'SUPPLEMENT'] as const) {
  test(`${type} completion celebrates only nonempty completed present or past days`, async ({ page }) => {
    const item = participation(2, type);
    item.occurrences.forEach(record => { record.isCompleted = true; });
    const { calendar, unexpected } = await openCalendar(page, item);
    const noun = type === 'MEDICATION' ? '약을' : '영양제를';
    await expect(calendar.getByRole('status')).toContainText(`오늘 먹을 ${noun} 다 먹었어요!`);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await calendar.getByRole('button', { name: '이전 날짜', exact: true }).click();
    await expect(calendar.getByRole('status')).toContainText(`9월 9일 먹을 ${noun} 다 먹었어요!`);
    await calendar.getByRole('button', { name: '다음 날짜', exact: true }).click();
    await calendar.getByRole('button', { name: '다음 날짜', exact: true }).click();
    await expect(calendar.getByRole('status')).toHaveCount(0);
    await calendar.getByRole('button', { name: '다음 날짜', exact: true }).click();
    await expect(calendar.getByText('이날은 목표 기록이 없어요.')).toBeVisible();
    await expect(calendar.getByRole('status')).toHaveCount(0);
    expect(unexpected).toEqual([]);
  });
}

test('record swipes change date both ways, ignore vertical/cancelled gestures, and respect Seoul period boundaries', async ({ page }) => {
  const { calendar, unexpected } = await openCalendar(page, participation());
  const area = calendar.getByRole('region', { name: '날짜별 복용 기록' });
  await swipe(area, -90);
  await expect(calendar.getByRole('heading', { name: '9월 11일' })).toBeVisible();
  await swipe(area, 90);
  await expect(calendar.getByRole('heading', { name: '9월 10일' })).toBeVisible();
  await swipe(area, -70, 140);
  await expect(calendar.getByRole('heading', { name: '9월 10일' })).toBeVisible();
  await area.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 180, clientY: 150, button: 0 });
  await area.dispatchEvent('pointercancel', { pointerId: 1, pointerType: 'touch' });
  await area.dispatchEvent('pointerup', { pointerId: 1, pointerType: 'touch', clientX: 20, clientY: 150 });
  await expect(calendar.getByRole('heading', { name: '9월 10일' })).toBeVisible();
  await swipe(area, 90);
  await swipe(area, 90);
  await expect(calendar.getByRole('heading', { name: '9월 9일' })).toBeVisible();
  await expect(calendar.getByRole('button', { name: '이전 날짜', exact: true })).toBeDisabled();
  await swipe(area, -90); await swipe(area, -90); await swipe(area, -90); await swipe(area, -90);
  await expect(calendar.getByRole('heading', { name: '9월 12일' })).toBeVisible();
  await expect(calendar.getByRole('button', { name: '다음 날짜', exact: true })).toBeDisabled();
  expect(await area.evaluate(element => getComputedStyle(element).touchAction)).toBe('pan-y');
  expect(unexpected).toEqual([]);
});

test('keyboard arrows navigate and keep the chosen date focused and visible in the native scrolling strip', async ({ page }) => {
  const item = participation(); item.actualEndDate = '2026-10-12';
  const { calendar } = await openCalendar(page, item);
  const selected = calendar.getByRole('button', { pressed: true });
  await selected.focus();
  await selected.press('ArrowRight');
  await expect(calendar.getByRole('heading', { name: '9월 11일' })).toBeVisible();
  await expect(calendar.getByRole('button', { pressed: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(calendar.getByRole('heading', { name: '10월 12일' })).toBeVisible();
  await expect(calendar.getByRole('button', { pressed: true })).toBeInViewport();
  await page.keyboard.press('Home');
  await expect(calendar.getByRole('heading', { name: '9월 9일' })).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowLeft');
  await expect(calendar.getByRole('heading', { name: '9월 9일' })).toBeVisible();
});

test('real touch gestures swipe record cards while a vertical drag scrolls the page', async ({ page, context }) => {
  const { calendar, unexpected } = await openCalendar(page, participation(7));
  const client = await context.newCDPSession(page);
  await client.send('Emulation.setTouchEmulationEnabled', { enabled: true });
  const card = calendar.getByRole('listitem').first();
  async function drag(dx: number, dy: number) {
    await card.scrollIntoViewIfNeeded();
    const box = (await card.boundingBox())!;
    const x = box.x + box.width / 2;
    const y = Math.min(600, box.y + box.height / 2);
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
    for (const step of [0.25, 0.5, 0.75, 1]) {
      await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + dx * step, y: y + dy * step }] });
    }
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  }
  await drag(-100, 0);
  await expect(calendar.getByRole('heading', { name: '9월 11일' })).toBeVisible();
  await drag(100, 0);
  await expect(calendar.getByRole('heading', { name: '9월 10일' })).toBeVisible();
  await card.scrollIntoViewIfNeeded();
  const before = (await card.boundingBox())!.y;
  await drag(0, -120);
  await expect.poll(async () => (await card.boundingBox())!.y).toBeLessThan(before - 20);
  await expect(calendar.getByRole('heading', { name: '9월 10일' })).toHaveCount(1);
  expect(unexpected).toEqual([]);
  await client.detach();
});

test('active initial date clamps to the actual period before start and after end', async ({ page }) => {
  const item = participation();
  item.joinedAt = '2026-09-11T16:00:00Z';
  item.actualEndDate = '2026-09-14';
  item.occurrences = [{ ...item.occurrences[0], scheduledDate: '2026-09-12', scheduledAt: '2026-09-12T08:00:00+09:00' }];
  const { calendar } = await openCalendar(page, item);
  await expect(calendar.getByRole('heading', { name: '9월 12일' })).toBeVisible();
  await expect(calendar.getByRole('button', { name: '이전 날짜', exact: true })).toBeDisabled();
  await expect(calendar.getByRole('status')).toHaveCount(0);
  item.joinedAt = '2026-09-01T00:00:00+09:00';
  item.actualEndDate = '2026-09-09';
  item.occurrences = [{ ...item.occurrences[0], scheduledDate: '2026-09-09', scheduledAt: '2026-09-09T08:00:00+09:00' }];
  await page.reload();
  await expect(calendar.getByRole('heading', { name: '9월 9일' })).toBeVisible();
  await expect(calendar.getByRole('button', { name: '다음 날짜', exact: true })).toBeDisabled();
});

test('terminal participation selects actual end while zero targets never announce completion', async ({ page }) => {
  const item = participation(); item.status = 'CANCELLED';
  const { calendar } = await openCalendar(page, item);
  await expect(calendar.getByRole('heading', { name: '9월 12일' })).toBeVisible();
  await expect(calendar.getByText('이날은 목표 기록이 없어요.')).toBeVisible();
  item.occurrences = []; item.targetCount = 0; item.completedCount = 0; item.actualEndDate = null;
  await page.reload();
  await expect(calendar.getByText('예정된 목표 기록이 없어요.')).toBeVisible();
  await expect(calendar.getByRole('status')).toHaveCount(0);
});

for (const width of [320, 390, 1280]) {
  test(`date strip and long record names fit ${width}px without page overflow`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const item = participation(7, 'SUPPLEMENT'); item.actualEndDate = '2026-10-12';
    const { calendar } = await openCalendar(page, item);
    const strip = calendar.getByRole('group', { name: '챌린지 날짜 선택' });
    const dimensions = await strip.evaluate(element => ({ client: element.clientWidth, scroll: element.scrollWidth, overflow: getComputedStyle(element).overflowX }));
    expect(dimensions.scroll).toBeGreaterThan(dimensions.client);
    expect(dimensions.overflow).toBe('auto');
    const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(size.scroll).toBeLessThanOrEqual(size.width);
    await calendar.screenshot({ path: testInfo.outputPath(`date-strip-${width}.png`) });
  });
}
