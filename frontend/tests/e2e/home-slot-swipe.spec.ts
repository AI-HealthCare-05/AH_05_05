import { expect, test, type Page, type Locator } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));
const DATE = '2026-09-05';
type Dose = { recordId?: number; supplementId?: number; date: string; slot: string; taken: boolean };

async function openHome(page: Page, slots = ['morning', 'lunch', 'evening', 'bedtime'], at = '06:00:00') {
  const writes: Dose[] = [];
  const apiReads: string[] = [];
  let saveGate: Promise<void> | undefined;
  await page.clock.setFixedTime(new Date(`${DATE}T${at}`));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'home-slot-test');
    sessionStorage.setItem('poke.account-principal', 'home-slot@example.com');
  });
  // Match API pathnames only: module URLs also contain /api/ in the source tree.
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      const payload = route.request().postDataJSON() as Dose;
      writes.push(payload);
      await saveGate;
      await route.fulfill({ json: payload });
      return;
    }
    apiReads.push(path);
    if (path === '/api/v1/medications') {
      await route.fulfill({ json: [1, 2, 3].map(id => ({
        recordId: id, alias: `처방 ${id}`, documentImageUrl: '',
        start: { date: DATE, slot: 'morning' }, endDate: '2026-09-14', daysRemaining: 10, isFinished: false,
        mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
        medications: [{ medicationId: id, name: `약 ${id}`, dose: '1정', days: 10, daysRemaining: 10, slots, asNeeded: false }],
      })) });
    } else if (path === '/api/v1/med/user-suppl-nutr') {
      await route.fulfill({ json: { items: [501, 502].map(id => ({
        id, custom_name: `영양제 ${id}`, dose_amount: '1.000', dose_unit: '정',
        start_date: DATE, end_date: null, status: 'ACTIVE', score: null, review_body: null, note: null,
        created_at: `${DATE}T09:00:00+09:00`, updated_at: null, supplement: null,
        slots: slots.map(slot => ({ slot: slot.toUpperCase(), time: ({ morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' })[slot] })),
      })), total: 2, offset: 0, limit: 100, nutrient_standard: null } });
    } else if (path === '/api/v1/medications/doses' || path === '/api/v1/med/supplement-doses') {
      await route.fulfill({ json: [] });
    } else if (path === '/api/v1/users/me') {
      await route.fulfill({ json: { name: '테스트', maskedName: '테*트', phoneNumber: null, birthDate: null, gender: null } });
    } else if (path === '/api/v1/user/challenges') {
      await route.fulfill({ json: { items: [], total_count: 0 } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Isolated fixture' } });
    }
  });
  await page.goto('/home');
  await expect(page.getByRole('group', { name: '아침약 상세' })).toBeVisible();
  return { writes, apiReads, deferSave: () => {
    let release!: () => void;
    saveGate = new Promise<void>(resolve => { release = resolve; });
    return release;
  } };
}

async function swipe(panel: Locator, dx: number, dy = 0) {
  await panel.dispatchEvent('pointerdown', { pointerId: 1, isPrimary: true, pointerType: 'touch', clientX: 180, clientY: 250 });
  await panel.dispatchEvent('pointerup', { pointerId: 1, isPrimary: true, pointerType: 'touch', clientX: 180 + dx, clientY: 250 + dy });
}

for (const kind of ['복약', '영양제']) {
  test(`${kind}: scheduled tabs, keyboard and both swipe directions preserve boundaries without API requests`, async ({ page }) => {
    const { writes, apiReads } = await openHome(page, ['morning', 'evening', 'bedtime']);
    if (kind === '영양제') await page.getByRole('tab', { name: '오늘의 영양제', exact: true }).click();
    const tabs = page.getByRole('tablist', { name: `${kind} 시간대` });
    await expect(tabs.getByRole('tab')).toHaveCount(3);
    await expect(tabs.getByRole('tab', { name: '점심', exact: true })).toHaveCount(0);
    await expect(tabs.getByRole('tab', { name: '아침', exact: true })).toHaveAttribute('aria-selected', 'true');
    const panel = () => page.getByRole('tabpanel', { name: /^(아침|저녁|자기전)$/ });
    const beforeReads = apiReads.length;
    await swipe(panel(), 90);
    await expect(tabs.getByRole('tab', { name: '아침', exact: true })).toHaveAttribute('aria-selected', 'true');
    await swipe(panel(), -90, 140);
    await expect(tabs.getByRole('tab', { name: '아침', exact: true })).toHaveAttribute('aria-selected', 'true');
    await swipe(panel(), -90);
    await expect(tabs.getByRole('tab', { name: '저녁', exact: true })).toHaveAttribute('aria-selected', 'true');
    await swipe(panel(), 90);
    await tabs.getByRole('tab', { name: '아침', exact: true }).focus();
    await page.keyboard.press('ArrowRight');
    await expect(tabs.getByRole('tab', { name: '저녁', exact: true })).toBeFocused();
    await page.keyboard.press('End');
    await swipe(panel(), -90);
    await expect(tabs.getByRole('tab', { name: '자기전', exact: true })).toHaveAttribute('aria-selected', 'true');
    await page.keyboard.press('Home');
    await page.keyboard.press('Tab');
    await expect(panel()).toBeFocused();
    await tabs.getByRole('tab', { name: '저녁', exact: true }).click();
    await expect(panel()).toHaveCount(1);
    expect(writes).toEqual([]);
    expect(apiReads.length).toBe(beforeReads);
  });
}

test('medication selection and completion belong to their slot; all includes collapsed prescriptions', async ({ page }) => {
  const { writes } = await openHome(page);
  const tabs = page.getByRole('tablist', { name: '복약 시간대' });
  const morning = page.getByRole('group', { name: '아침약 상세' });
  await morning.locator('[data-episode-row]').first().click();
  await tabs.getByRole('tab', { name: '저녁', exact: true }).click();
  const evening = page.getByRole('group', { name: '저녁약 상세' });
  await expect(evening.locator('[aria-pressed="true"]')).toHaveCount(0);
  await evening.getByRole('button', { name: /먹었어요$/ }).click();
  await expect.poll(() => writes.length).toBe(3);
  expect(writes.map(item => [item.recordId, item.slot, item.taken]).sort()).toEqual([[1, 'evening', true], [2, 'evening', true], [3, 'evening', true]]);
  await tabs.getByRole('tab', { name: '아침', exact: true }).click();
  await expect(morning.locator('[aria-pressed="true"]')).toHaveCount(1);
  await morning.getByRole('button', { name: /먹었어요$/ }).click();
  await expect.poll(() => writes.length).toBe(4);
  expect(writes[3]).toMatchObject({ recordId: 3, slot: 'morning', taken: true });
  await tabs.getByRole('tab', { name: '저녁', exact: true }).click();
  await evening.locator('[data-episode-row]').first().click();
  await evening.getByRole('button', { name: '복약 기록 되돌리기' }).click();
  await expect.poll(() => writes.length).toBe(5);
  expect(writes[4]).toMatchObject({ recordId: 3, slot: 'evening', taken: false });
  await evening.getByRole('button', { name: '복약 메모' }).click();
  await expect(page).toHaveURL(/medications\/notes\/new/);
});

test('supplement completion and undo after switching never affect another slot', async ({ page }) => {
  const { writes } = await openHome(page);
  await page.getByRole('tab', { name: '오늘의 영양제', exact: true }).click();
  const tabs = page.getByRole('tablist', { name: '영양제 시간대' });
  const morning = page.getByRole('group', { name: '아침 영양제' });
  await morning.getByRole('button', { name: '영양제 501 선택' }).click();
  await tabs.getByRole('tab', { name: '자기전', exact: true }).click();
  const bedtime = page.getByRole('group', { name: '자기전 영양제' });
  await expect(bedtime.getByRole('button', { name: '0개 먹었어요' })).toBeDisabled();
  await bedtime.getByRole('button', { name: '다 먹었어요' }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes).toEqual([501, 502].map(supplementId => ({ supplementId, date: DATE, slot: 'bedtime', taken: true })));
  await tabs.getByRole('tab', { name: '아침', exact: true }).click();
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect.poll(() => writes.length).toBe(3);
  expect(writes[2]).toEqual({ supplementId: 501, date: DATE, slot: 'morning', taken: true });
  await tabs.getByRole('tab', { name: '자기전', exact: true }).click();
  await bedtime.getByRole('button', { name: '영양제 501 복용 완료' }).click();
  await bedtime.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect.poll(() => writes.length).toBe(4);
  expect(writes[3]).toEqual({ supplementId: 501, date: DATE, slot: 'bedtime', taken: false });
});

test('single scheduled slot omits navigation in both categories', async ({ page }) => {
  await openHome(page, ['morning']);
  await expect(page.getByRole('tablist', { name: '복약 시간대' })).toHaveCount(0);
  await page.getByRole('tab', { name: '오늘의 영양제', exact: true }).click();
  await expect(page.getByRole('group', { name: '아침 영양제' })).toBeVisible();
  await expect(page.getByRole('tablist', { name: '영양제 시간대' })).toHaveCount(0);
});

for (const kind of ['복약', '영양제']) {
  test(`${kind}: a save resolving after navigation updates only its original slot`, async ({ page }) => {
    const { writes, deferSave } = await openHome(page);
    if (kind === '영양제') await page.getByRole('tab', { name: '오늘의 영양제', exact: true }).click();
    const tabs = page.getByRole('tablist', { name: `${kind} 시간대` });
    const release = deferSave();
    const morning = page.getByRole('group', { name: kind === '복약' ? '아침약 상세' : '아침 영양제' });
    await morning.getByRole('button', { name: kind === '복약' ? '먹었어요' : '다 먹었어요', exact: true }).click();
    await expect.poll(() => writes.length).toBe(kind === '복약' ? 3 : 2);
    await tabs.getByRole('tab', { name: '저녁', exact: true }).click();
    release();
    const evening = page.getByRole('group', { name: kind === '복약' ? '저녁약 상세' : '저녁 영양제' });
    await expect(evening.getByText('복용 완료', { exact: true })).toHaveCount(0);
    await tabs.getByRole('tab', { name: '아침', exact: true }).click();
    const morningCard = kind === '복약' ? morning.locator('..') : morning;
    await expect(morningCard.getByText('복용 완료', { exact: true })).toHaveCount(1);
    await expect(morning.getByRole('button', { name: /복용 완료$/ })).toHaveCount(2);
    expect(writes.every(item => item.slot === 'morning')).toBe(true);
  });

  test(`${kind}: native horizontal touch over a dose button never saves; vertical touch scrolls`, async ({ page }) => {
    const { writes } = await openHome(page, ['morning', 'evening']);
    await page.setViewportSize({ width: 390, height: 600 });
    if (kind === '영양제') await page.getByRole('tab', { name: '오늘의 영양제', exact: true }).click();
    const tabs = page.getByRole('tablist', { name: `${kind} 시간대` });
    const panel = () => page.getByRole('tabpanel', { name: /^(아침|저녁)$/ });
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true });
    async function touch(x: number, y: number, dx: number, dy: number) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      for (let step = 1; step <= 6; step++) {
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + dx * step / 6, y: y + dy * step / 6 }] });
      }
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    }
    const action = panel().getByRole('button', { name: kind === '복약' ? '먹었어요' : '다 먹었어요', exact: true });
    await action.scrollIntoViewIfNeeded();
    // Native CDP touch has no actionability wait; allow the loading-height reveal to expose the target.
    await action.click({ trial: true });
    const box = (await action.boundingBox())!;
    // The #390 floating launcher can cover the far-right edge in a short viewport.
    // Start on the exposed action itself, not on the unrelated launcher.
    const start = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    expect(await action.evaluate((button, point) => button.contains(document.elementFromPoint(point.x, point.y)), start)).toBe(true);
    await touch(start.x, start.y, -140, 0);
    await expect(tabs.getByRole('tab', { name: '저녁', exact: true })).toHaveAttribute('aria-selected', 'true');
    const eveningBox = (await panel().boundingBox())!;
    await touch(eveningBox.x + 30, eveningBox.y + 30, 140, 0);
    await expect(tabs.getByRole('tab', { name: '아침', exact: true })).toHaveAttribute('aria-selected', 'true');
    const morningBox = (await panel().boundingBox())!;
    const scrollContainer = page.getByRole('main', { name: '홈 콘텐츠' });
    const scrollBefore = await scrollContainer.evaluate(element => element.scrollTop);
    await touch(morningBox.x + 30, morningBox.y + 160, 4, -130);
    await expect.poll(() => scrollContainer.evaluate(element => element.scrollTop)).toBeGreaterThan(scrollBefore);
    await expect(tabs.getByRole('tab', { name: '아침', exact: true })).toHaveAttribute('aria-selected', 'true');
    expect(writes).toEqual([]);
  });
}

test('four scheduled slots fit 320, 390 and 1280 widths and preserve the current-time default', async ({ page }, testInfo) => {
  await openHome(page, undefined, '06:00:00');
  await page.clock.setFixedTime(new Date(`${DATE}T20:00:00`));
  await page.reload();
  await expect(page.getByRole('tablist', { name: '복약 시간대' }).getByRole('tab', { name: '저녁', exact: true })).toHaveAttribute('aria-selected', 'true');
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const kind of ['복약', '영양제']) {
      await page.getByRole('tab', { name: `오늘의 ${kind}`, exact: true }).click();
      const tabs = page.getByRole('tablist', { name: `${kind} 시간대` });
      await expect(tabs.getByRole('tab')).toHaveCount(4);
      await tabs.getByRole('tab', { name: '저녁', exact: true }).click();
      expect(await tabs.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`home-slot-${kind}-${width}.png`), fullPage: true });
    }
  }
});
