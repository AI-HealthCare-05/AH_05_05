import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON, REAL_API_ONLY_REASON } from './helpers/mode';

const SORT_LABELS = {
  name: '이름순',
  registered: '등록순',
  rating: '평점순',
  reviews: '후기순',
} as const;

const PRODUCT = {
  id: 44701,
  food_code: 'SUPPL-447-01',
  name: '이름순 오름차순 결과',
  basis_qty: '1000mg',
  energy_kcal: 0,
  water_g: null,
  protein_g: null,
  fat_g: null,
  ash_g: null,
  carb_g: null,
  sugar_g: null,
  fiber_g: null,
  calcium_mg: '100.00',
  iron_mg: null,
  phosphorus_mg: null,
  potassium_mg: null,
  sodium_mg: null,
  vitamin_a_ug_rae: null,
  retinol_ug: null,
  beta_carotene_ug: null,
  thiamine_mg: null,
  riboflavin_mg: null,
  niacin_mg: null,
  vitamin_c_mg: null,
  vitamin_d_ug: null,
  cholesterol_mg: null,
  sat_fat_g: null,
  trans_fat_g: null,
  serving_desc: '1정',
  serving_size: '1000mg',
  daily_freq: '1회',
  target: '성인',
  rating_average: 4.7,
  review_count: 447,
};

const REGISTRATION = {
  id: 44702,
  custom_name: null,
  dose_amount: '1.000',
  dose_unit: '정',
  start_date: '2026-09-01',
  end_date: null,
  status: 'ACTIVE',
  score: 5,
  review_body: null,
  note: null,
  created_at: '2026-09-01T09:00:00+09:00',
  updated_at: null,
  slots: [{ slot: 'MORNING', time: '08:00:00' }],
  supplement: PRODUCT,
};

interface TrackMaterial {
  backgroundImage: string;
  borderRadius: string;
  borderWidth: string;
  boxShadow: string;
  padding: string;
}

interface PillMaterial {
  backgroundImage: string;
  borderRadius: string;
  boxShadow: string;
  height: number;
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-447-sort-token');
    sessionStorage.setItem('poke.account-principal', 'issue-447-sort@example.com');
  });
}

async function settleAnimations(page: Page) {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
}

async function trackMaterial(group: Locator): Promise<TrackMaterial> {
  return group.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundImage: style.backgroundImage,
      borderRadius: style.borderRadius,
      borderWidth: style.borderTopWidth,
      boxShadow: style.boxShadow,
      padding: style.padding,
    };
  });
}

async function pillMaterial(group: Locator): Promise<PillMaterial> {
  return group.locator('[data-continuous-pill]').evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundImage: style.backgroundImage,
      borderRadius: style.borderRadius,
      boxShadow: style.boxShadow,
      height: element.getBoundingClientRect().height,
    };
  });
}

async function expectPillAligned(group: Locator) {
  const pill = group.locator('[data-continuous-pill]');
  const selected = group.locator('button[aria-pressed="true"], button[aria-selected="true"]');
  await expect(pill).toHaveCount(1);
  await expect(selected).toHaveCount(1);
  await expect.poll(async () => {
    const [pillBox, selectedBox] = await Promise.all([pill.boundingBox(), selected.boundingBox()]);
    if (!pillBox || !selectedBox) return null;
    return {
      x: Math.abs(pillBox.x - selectedBox.x),
      y: Math.abs(pillBox.y - selectedBox.y),
      width: Math.abs(pillBox.width - selectedBox.width),
      height: Math.abs(pillBox.height - selectedBox.height),
    };
  }).toEqual({ x: 0, y: 0, width: 0, height: 0 });
}

async function expectLabelsFit(group: Locator) {
  expect(await group.getByRole('button').evaluateAll((buttons) => buttons.every((button) => (
    button.scrollWidth <= button.clientWidth + 1 && button.scrollHeight <= button.clientHeight + 1
  )))).toBe(true);
}

async function capture(page: Page, name: string) {
  const directory = process.env.UI447_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await settleAnimations(page);
  await page.screenshot({ path: path.join(directory, name), fullPage: true, animations: 'disabled' });
}

function sortButton(group: Locator, label: string) {
  return group.getByRole('button', { name: new RegExp(`^${label}(?: [▲▼])?$`) });
}

test.beforeEach(async ({ page }) => {
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, (route) => route.abort());
});

for (const width of [320, 390, 1280]) {
  test(`영양제 정렬은 한 줄에서 홈과 같은 연속 탭 표면을 사용한다 (${width}px)`, async ({ page }) => {
    test.skip(IS_REAL_API, MOCK_ONLY_REASON);
    await page.setViewportSize({ width, height: 844 });
    await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
    await authenticate(page);
    await page.goto('/dev/home-multiple-episodes');

    const home = page.getByRole('tablist', { name: '복약 시간대' });
    await expect(home).toBeVisible();
    await settleAnimations(page);
    const homeTrack = await trackMaterial(home);
    const homePill = await pillMaterial(home);
    expect(homeTrack.borderWidth).toBe('1px');
    expect(homeTrack.borderRadius).not.toBe('0px');
    expect(homeTrack.backgroundImage).not.toBe('none');
    expect(homeTrack.boxShadow).not.toBe('none');
    expect(homePill.backgroundImage).not.toBe('none');
    expect(homePill.boxShadow).not.toBe('none');
    await expectPillAligned(home);

    await page.goto('/dev/supplements?tab=browse');
    await page.getByPlaceholder('제품명 또는 성분 검색').fill('센트룸');
    await expect(page.getByLabel('영양제 검색 결과')).toBeVisible();
    const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
    await expect(page.getByRole('group', { name: '정렬 방향' })).toHaveCount(0);
    await settleAnimations(page);

    expect(await trackMaterial(sorts)).toEqual(homeTrack);
    expect(await pillMaterial(sorts)).toEqual(homePill);
    await expectPillAligned(sorts);
    await expectLabelsFit(sorts);

    await sortButton(sorts, '등록순').click();
    await expect(sorts.getByRole('button', { name: '등록순 ▼', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await sortButton(sorts, '등록순').click();
    await expect(sorts.getByRole('button', { name: '등록순 ▲', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await settleAnimations(page);
    await expectPillAligned(sorts);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

async function prepareProductionBrowse(page: Page) {
  const requests: Array<{ sort: keyof typeof SORT_LABELS; direction: 'asc' | 'desc'; offset: string | null }> = [];
  await authenticate(page);
  await page.route('**/api/v1/**', (route) => fulfillJson(route, { code: 'FIXTURE_MISSING', message: '447 fixture missing' }, 503));
  await page.route('**/api/v1/med/user-suppl-nutr?*', (route) => fulfillJson(route, {
    items: [REGISTRATION], total: 1, offset: 0, limit: 100, nutrient_standard: null,
  }));
  await page.route('**/api/v1/display/med/nutr/rank', (route) => fulfillJson(route, { items: [] }));
  await page.route('**/api/v1/med/nutr?*', async (route) => {
    const params = new URL(route.request().url()).searchParams;
    const sort = params.get('sort') as keyof typeof SORT_LABELS;
    const direction = params.get('direction') as 'asc' | 'desc';
    requests.push({ sort, direction, offset: params.get('offset') });
    await fulfillJson(route, {
      items: [{ ...PRODUCT, name: `${SORT_LABELS[sort]} ${direction === 'asc' ? '오름차순' : '내림차순'} 결과` }],
      total: 1,
      offset: 0,
      limit: 20,
    });
  });
  return requests;
}

async function expectRequestAndFixture(
  page: Page,
  requests: Awaited<ReturnType<typeof prepareProductionBrowse>>,
  sort: keyof typeof SORT_LABELS,
  direction: 'asc' | 'desc',
) {
  await expect.poll(() => requests.at(-1)).toEqual({ sort, direction, offset: '0' });
  await expect(page.getByLabel('영양제 검색 결과').getByText(
    `${SORT_LABELS[sort]} ${direction === 'asc' ? '오름차순' : '내림차순'} 결과`,
    { exact: true },
  )).toBeVisible();
}

for (const width of [320, 390, 1280]) {
  test(`선택한 정렬 기준을 다시 누르면 방향을 바꾸고 기준 변경은 기본 방향을 쓴다 (${width}px)`, async ({ page }) => {
    test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
    await page.setViewportSize({ width, height: 844 });
    const requests = await prepareProductionBrowse(page);
    await page.goto('/dev/supplements?tab=browse');
    await page.getByPlaceholder('제품명 또는 성분 검색').fill('비타민');

    const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
    await expectRequestAndFixture(page, requests, 'name', 'asc');
    await settleAnimations(page);
    await expect(sorts).toHaveCSS('border-top-width', '1px');
    await expect(sorts).not.toHaveCSS('border-radius', '0px');
    await expect(sorts).not.toHaveCSS('background-image', 'none');
    await expect(sorts.locator('[data-continuous-pill]')).not.toHaveCSS('background-image', 'none');
    await expect(sorts.locator('[data-continuous-pill]')).not.toHaveCSS('box-shadow', 'none');
    await expectPillAligned(sorts);
    await expectLabelsFit(sorts);

    if (width === 390) {
      await sortButton(sorts, '이름순').click();
      await expectRequestAndFixture(page, requests, 'name', 'desc');
      await sortButton(sorts, '이름순').click();
      await expectRequestAndFixture(page, requests, 'name', 'asc');

      for (const sort of ['rating', 'reviews', 'registered'] as const) {
        await sortButton(sorts, SORT_LABELS[sort]).click();
        await expectRequestAndFixture(page, requests, sort, 'desc');
        await sortButton(sorts, SORT_LABELS[sort]).click();
        await expectRequestAndFixture(page, requests, sort, 'asc');
        await sortButton(sorts, SORT_LABELS[sort]).click();
        await expectRequestAndFixture(page, requests, sort, 'desc');
      }
    } else {
      await sortButton(sorts, '등록순').click();
      await expectRequestAndFixture(page, requests, 'registered', 'desc');
    }

    await expect(page.getByRole('group', { name: '정렬 방향' })).toHaveCount(0);
    await expect(sortButton(sorts, '등록순')).toHaveAttribute('aria-pressed', 'true');
    await expect(sorts.getByRole('button', { name: '등록순 ▼', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByLabel('영양제 검색 결과').getByText('복용 중', { exact: true })).toBeVisible();
    await settleAnimations(page);
    await expectPillAligned(sorts);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    if (width <= 390) await capture(page, `task-5-sort-controls-${width}.png`);
  });
}
