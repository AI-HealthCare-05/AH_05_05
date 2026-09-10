import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));
test.use({ video: { mode: 'on', size: { width: 390, height: 844 } } });
const DATE = '2026-09-05';
const LONG_NAME = '아주긴건강관리처방과영양제품이름LongMedicationName'.repeat(3);
type Dose = { recordId?: number; supplementId?: number; date: string; slot: string; taken: boolean };

async function openHome(page: Page, kind: '복약' | '영양제', longName = false) {
  const writes: Dose[] = [];
  let gate: Promise<void> | undefined;
  let failure = false;
  await page.clock.setFixedTime(new Date(`${DATE}T06:00:00`));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'home-selection-fixture');
    sessionStorage.setItem('poke.account-principal', 'home-selection@example.invalid');
  });
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') {
      const dose = route.request().postDataJSON();
      writes.push(dose);
      await gate;
      if (failure) { failure = false; await route.fulfill({ status: 500, json: { detail: 'fixture failure' } }); }
      else await route.fulfill({ json: dose });
      return;
    }
    if (path === '/api/v1/medications') {
      await route.fulfill({ json: [1, 2, 3].map(id => ({
        recordId: id, alias: longName ? `${LONG_NAME}${id}` : `처방 ${id}`, documentImageUrl: '',
        start: { date: DATE, slot: 'morning' }, endDate: '2026-09-14', daysRemaining: 10, isFinished: false,
        mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
        medications: [{ medicationId: id, name: `약 ${id}`, dose: '1정', days: 10, daysRemaining: 10, slots: ['morning', 'evening'], asNeeded: false }],
      })) });
    } else if (path === '/api/v1/med/user-suppl-nutr') {
      await route.fulfill({ json: { items: [501, 502].map(id => ({
        id, custom_name: longName ? `${LONG_NAME}${id}` : `영양제 ${id}`, dose_amount: '1.000', dose_unit: '정',
        start_date: DATE, end_date: null, status: 'ACTIVE', score: null, review_body: null, note: null,
        created_at: `${DATE}T09:00:00+09:00`, updated_at: null, supplement: null,
        slots: [{ slot: 'MORNING', time: '08:00' }, { slot: 'EVENING', time: '19:00' }],
      })), total: 2, offset: 0, limit: 100, nutrient_standard: null } });
    } else if (path.endsWith('/doses') || path.endsWith('/supplement-doses')) {
      await route.fulfill({ json: [] });
    } else if (path === '/api/v1/users/me') {
      await route.fulfill({ json: { name: '테스트', maskedName: '테*트', phoneNumber: null, birthDate: null, gender: null } });
    } else if (path === '/api/v1/user/challenges') {
      await route.fulfill({ json: { items: [], total_count: 0 } });
    } else await route.fulfill({ status: 404, json: { detail: 'isolated fixture' } });
  });
  await page.goto('/home');
  if (kind === '영양제') await page.getByRole('tab', { name: '오늘의 영양제', exact: true }).click();
  const group = page.getByRole('group', { name: kind === '복약' ? '아침약 상세' : '아침 영양제', exact: true });
  const row = kind === '복약' ? group.locator('[data-episode-row]').first() : group.getByRole('button', { name: /영양제 501 선택|LongMedicationName.*501 선택/ });
  const title = kind === '복약' ? row.getByRole('heading') : row.locator('span').filter({ hasText: longName ? `${LONG_NAME}501` : '영양제 501' }).last();
  await expect(row).toBeVisible();
  return { group, row, title, writes, failNext: () => { failure = true; }, deferSave: () => {
    let release!: () => void;
    gate = new Promise<void>(resolve => { release = resolve; });
    return release;
  } };
}

for (const kind of ['복약', '영양제'] as const) {
  test(`${kind}: checkbox occupies no space until selected; text slides and deselection reverses without a dose write`, async ({ page }, info) => {
    const { row, title, writes } = await openHome(page, kind);
    const left = () => title.evaluate(el => el.getBoundingClientRect().left);
    const initialLeft = await left();
    const rowLeft = await row.evaluate(el => el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft));
    expect(initialLeft).toBeCloseTo(rowLeft, 0);
    await expect(row).toHaveAttribute('aria-pressed', 'false');
    await page.screenshot({ path: info.outputPath(`${kind}-01-unselected.png`) });
    await title.click();
    await expect(row).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(left).toBeCloseTo(initialLeft + 36, 0);
    await expect(row.locator('[data-dose-selection] svg')).toHaveCount(1);
    await expect(row.getByRole('checkbox')).toHaveCount(0);
    await expect(row.locator('button,input')).toHaveCount(0);
    await page.screenshot({ path: info.outputPath(`${kind}-02-selected.png`) });
    await row.focus();
    await page.keyboard.press('Space');
    await expect(row).toHaveAttribute('aria-pressed', 'false');
    await expect.poll(left).toBeCloseTo(initialLeft, 0);
    expect(writes).toEqual([]);
    await page.screenshot({ path: info.outputPath(`${kind}-03-deselected.png`) });
  });

  test(`${kind}: pending save, failure retry, completion and undo retain the selected row semantics`, async ({ page }) => {
    const { group, row, writes, deferSave, failNext } = await openHome(page, kind);
    await row.click();
    const release = deferSave();
    failNext();
    await group.getByRole('button', { name: kind === '복약' ? '먹었어요' : '1개 먹었어요', exact: true }).click();
    await expect(row).toBeDisabled();
    await expect.poll(() => writes.length).toBe(1);
    release();
    if (kind === '복약') await page.getByRole('dialog', { name: '기록하지 못했어요' }).getByRole('button', { name: '다시 시도' }).click();
    else await group.getByRole('button', { name: '다시 시도' }).click();
    await expect.poll(() => writes.length).toBe(2);
    const completed = group.getByRole('button', { name: kind === '복약' ? /처방 3 .* 복용 완료/ : '영양제 501 복용 완료' });
    await expect(completed).toHaveAttribute('aria-pressed', 'false');
    await expect(completed.getByText('복용 완료', { exact: true })).toBeVisible();
    await completed.click();
    await expect(completed).toHaveAttribute('aria-pressed', 'true');
    await expect(completed.getByText('복용 완료', { exact: true })).toBeVisible();
    await group.getByRole('button', { name: kind === '복약' ? '복약 기록 되돌리기' : '1개 되돌리기', exact: true }).click();
    await expect.poll(() => writes.length).toBe(3);
    expect(writes[0]).toMatchObject({ slot: 'morning', taken: true });
    expect(writes[2]).toMatchObject({ slot: 'morning', taken: false });
  });

  test(`${kind}: selection moves through an intermediate layout instead of jumping`, async ({ page }) => {
    const { row, writes } = await openHome(page, kind);
    const motion = await row.evaluate(async element => {
      element.click();
      await new Promise(requestAnimationFrame);
      const indicator = element.querySelector('[data-dose-selection]')!;
      const animations = indicator.getAnimations({ subtree: true });
      const widthAnimation = animations.find(animation => animation instanceof CSSTransition && animation.transitionProperty === 'width');
      if (!widthAnimation) return null;
      const duration = Number(widthAnimation.effect!.getTiming().duration);
      animations.forEach(animation => { animation.pause(); animation.currentTime = duration / 2; });
      const intermediateWidth = parseFloat(getComputedStyle(indicator).width);
      animations.forEach(animation => animation.play());
      return { duration, intermediateWidth };
    });
    expect(motion).not.toBeNull();
    expect(motion!.duration).toBeGreaterThanOrEqual(200);
    expect(motion!.duration).toBeLessThanOrEqual(250);
    expect(motion!.intermediateWidth).toBeGreaterThan(0);
    expect(motion!.intermediateWidth).toBeLessThan(36);
    await expect(row.locator('[data-dose-selection]')).toHaveCSS('width', '36px');
    expect(writes).toEqual([]);
  });

  test(`${kind}: long selected labels fit mobile and desktop, with immediate reduced motion`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const { row, title, writes } = await openHome(page, kind, true);
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      const x = await title.evaluate(el => el.getBoundingClientRect().left);
      await row.click();
      await expect(row).toHaveAttribute('aria-pressed', 'true');
      expect(await title.evaluate(el => el.getBoundingClientRect().left)).toBeCloseTo(x + 36, 0);
      expect(await row.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await row.locator('[data-dose-selection]').evaluate(el => getComputedStyle(el).transitionDuration)).toBe('0s');
      await row.click();
      expect(await title.evaluate(el => el.getBoundingClientRect().left)).toBeCloseTo(x, 0);
    }
    expect(writes).toEqual([]);
  });

  test(`${kind}: native swipes starting on text never select, and vertical scrolling remains native`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 600 });
    const { row, writes } = await openHome(page, kind);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true });
    async function touch(x: number, y: number, dx: number, dy: number) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      for (let step = 1; step <= 6; step++) {
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + dx * step / 6, y: y + dy * step / 6 }] });
      }
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    }
    await row.click({ trial: true });
    const morningBox = (await row.boundingBox())!;
    await touch(morningBox.x + 180, morningBox.y + 20, -130, 0);
    const tabs = page.getByRole('tablist', { name: `${kind} 시간대` });
    await expect(tabs.getByRole('tab', { name: '저녁', exact: true })).toHaveAttribute('aria-selected', 'true');
    const evening = page.getByRole('tabpanel', { name: '저녁', exact: true });
    const eveningBox = (await evening.boundingBox())!;
    await touch(eveningBox.x + 20, eveningBox.y + 80, 130, 0);
    await expect(row).toHaveAttribute('aria-pressed', 'false');
    await expect(row.locator('[data-dose-selection]')).toHaveCSS('width', '0px');
    const scroll = page.getByRole('main', { name: '홈 콘텐츠' });
    const before = await scroll.evaluate(el => el.scrollTop);
    const currentBox = (await row.boundingBox())!;
    await touch(currentBox.x + 80, currentBox.y + 35, 3, -100);
    await expect.poll(() => scroll.evaluate(el => el.scrollTop)).toBeGreaterThan(before);
    await expect(row).toHaveAttribute('aria-pressed', 'false');
    expect(writes).toEqual([]);
  });
}

test.describe('selection motion recording', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('actual medication and supplement selection motion', async ({ page }, info) => {
    for (const kind of ['복약', '영양제'] as const) {
      const { row, group, writes } = await openHome(page, kind);
      await group.screenshot({ path: info.outputPath(`${kind}-before.png`) });
      await row.click();
      await expect(row.locator('[data-dose-selection]')).toHaveCSS('width', '36px');
      await group.screenshot({ path: info.outputPath(`${kind}-selected.png`) });
      await row.click();
      await expect(row.locator('[data-dose-selection]')).toHaveCSS('width', '0px');
      await group.screenshot({ path: info.outputPath(`${kind}-deselected.png`) });
      expect(writes).toEqual([]);
    }
  });
});

test('medication disclosure arrow never selects a row or writes a dose', async ({ page }) => {
  const { row, group, writes } = await openHome(page, '복약');
  const arrow = group.getByRole('button', { name: /처방 3 .* 처방 (펼치기|접기)/ });
  await arrow.click();
  await expect(arrow).toHaveAttribute('aria-expanded', 'true');
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await expect(row.locator('[data-dose-selection]')).toHaveCSS('width', '0px');
  expect(writes).toEqual([]);
});
