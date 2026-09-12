import { expect, test } from 'playwright/test';

const IS_REAL_API = process.env.VITE_USE_MOCK === 'false';
// WSL's mounted checkout can need more than the global 10s for Vite's first transform.
test.setTimeout(30_000);

const SEARCH_PRODUCT_RESPONSE = {
  id: 2048,
  food_code: 'SUPPL-MULTI-2048',
  name: '종합비타민',
  basis_qty: '1000mg',
  energy_kcal: 0,
  water_g: null,
  protein_g: null,
  fat_g: null,
  ash_g: null,
  carb_g: null,
  sugar_g: null,
  fiber_g: null,
  calcium_mg: null,
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
  rating_average: null,
  review_count: 0,
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'e2e-supplement-browse-token');
    sessionStorage.setItem('poke.account-principal', 'supplement-browse@example.com');
  });
});

test('영양제 기본 화면은 내 영양제이고 쿼리로 둘러보기를 연다', async ({ page }) => {
  test.skip(IS_REAL_API, '고정된 내 영양제 목록을 확인하는 목업 전용 테스트입니다.');
  await page.goto('/dev/supplements');

  const tabs = page.getByRole('tablist', { name: '영양제 화면' });
  await expect(tabs.getByRole('tab', { name: '내 영양제' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
  await expect(page.getByRole('banner').getByRole('button', { name: 'AI 보고서 받기' })).toBeVisible();

  await page.goto('/dev/supplements?tab=browse');

  await expect(tabs.getByRole('tab', { name: '둘러보기' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByRole('banner').getByRole('button', { name: 'AI 보고서 받기' }).click();
  await expect(page).toHaveURL(/\/reports\/new\?source=supplements$/);
});

test('탭을 반복해서 바꿔도 replace 이동이라 브라우저 이력이 쌓이지 않는다', async ({ page }) => {
  await page.goto('/dev/gallery');
  await page.goto('/dev/supplements');

  const tabs = page.getByRole('tablist', { name: '영양제 화면' });
  await tabs.getByRole('tab', { name: '둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);
  await tabs.getByRole('tab', { name: '내 영양제' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements$/);
  await tabs.getByRole('tab', { name: '둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/dev\/gallery$/);
});

test('둘러보기에서 내 영양제로 돌아오면 기존 목록과 성분 합계가 그대로 보인다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, '고정된 내 영양제 목록과 합계를 확인하는 목업 전용 테스트입니다.');
  await page.goto('/dev/supplements?tab=browse');

  const tabs = page.getByRole('tablist', { name: '영양제 화면' });
  await tabs.getByRole('tab', { name: '내 영양제' }).click();

  await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: '성분 합계' })).toBeVisible();
  await expect(page.getByText('등록한 영양제의 성분만 더한 값이에요')).toBeVisible();
});
test('둘러보기는 랭킹 5개와 등록된 제품 상태를 보여준다', async ({ page }) => {
  test.skip(IS_REAL_API, '목업의 고정 랭킹과 등록 상태를 확인하는 테스트입니다.');
  await page.goto('/dev/supplements?tab=browse');

  const ranking = page.getByLabel('영양제 랭킹');
  await expect(ranking.getByText('RxVita가 골랐어요', { exact: true })).toBeVisible();
  await expect(ranking.getByRole('listitem')).toHaveCount(5);
  await expect(ranking.getByText('등록됨', { exact: true })).toBeVisible();
});

test('검색 결과는 평점 집계를 보여주고 제품 상세로 이동한다', async ({ page }) => {
  test.skip(IS_REAL_API, '목업 제품으로 검색 결과와 상세 이동을 확인하는 테스트입니다.');
  await page.goto('/dev/supplements?tab=browse');

  await page.getByPlaceholder('제품명 또는 성분 검색').fill('센트룸');
  const results = page.getByLabel('영양제 검색 결과');
  await expect(results.getByText('센트룸 실버 우먼', { exact: true })).toBeVisible();
  await expect(results.getByText('★4.2 · 12', { exact: true })).toBeVisible();
  await expect(results.getByText('★0.0 · 0', { exact: true })).toHaveCount(0);

  const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
  await sorts.getByRole('button', { name: '이름순' }).click();
  await expect(results.getByText('센트룸 실버 우먼', { exact: true })).toBeVisible();

  await results.getByRole('button', { name: /센트룸 실버 우먼/ }).click();
  await expect(page).toHaveURL(/\/supplements\/product\/sp-001$/);
});

test('정렬 칩은 URL을 바꾸지 않고 실 검색 API 정렬을 첫 페이지부터 요청한다', async ({
  page,
}) => {
  test.skip(!IS_REAL_API, '실 API 모드의 검색 쿼리 계약을 확인하는 테스트입니다.');
  const requests: URL[] = [];
  await page.route('**/api/v1/med/nutr?*', async (route) => {
    const requestUrl = new URL(route.request().url());
    requests.push(requestUrl);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [SEARCH_PRODUCT_RESPONSE],
        total: 1,
        offset: 0,
        limit: 20,
      }),
    });
  });
  await page.goto('/dev/supplements?tab=browse');

  await expect(page.getByRole('group', { name: '검색 결과 정렬' })).toHaveCount(0);
  await expect(page.getByRole('group', { name: '정렬 방향' })).toHaveCount(0);
  await page.getByPlaceholder('제품명 또는 성분 검색').fill('비타민');
  const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
  const directions = page.getByRole('group', { name: '정렬 방향' });
  await expect(sorts).toBeVisible();
  await expect(directions).toBeVisible();

  await expect.poll(() => requests.at(-1)?.searchParams.get('sort')).toBe('name');
  expect(requests.at(-1)?.searchParams.get('direction')).toBe('asc');

  const expectations = [
    { label: '등록순', sort: 'registered', defaultDirection: 'desc' },
    { label: '평점순', sort: 'rating', defaultDirection: 'desc' },
    { label: '후기순', sort: 'reviews', defaultDirection: 'desc' },
    { label: '이름순', sort: 'name', defaultDirection: 'asc' },
  ] as const;
  for (const expectation of expectations) {
    await sorts.getByRole('button', { name: expectation.label }).click();
    await expect
      .poll(() => ({
        sort: requests.at(-1)?.searchParams.get('sort'),
        direction: requests.at(-1)?.searchParams.get('direction'),
      }))
      .toEqual({ sort: expectation.sort, direction: expectation.defaultDirection });
  }

  await directions.getByRole('button', { name: '내림차순' }).click();
  await expect
    .poll(() => ({
      sort: requests.at(-1)?.searchParams.get('sort'),
      direction: requests.at(-1)?.searchParams.get('direction'),
    }))
    .toEqual({ sort: 'name', direction: 'desc' });
  expect(requests.at(-1)?.searchParams.get('offset')).toBe('0');
  await expect(page).toHaveURL(/\?tab=browse$/);
});

test('검색 결과가 0건이면 정렬 컨트롤을 숨긴다', async ({ page }) => {
  test.skip(!IS_REAL_API, '실 API 응답의 0건 상태를 확인하는 테스트입니다.');
  await page.route('**/api/v1/med/nutr?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 20 }),
    });
  });
  await page.goto('/dev/supplements?tab=browse');

  await page.getByPlaceholder('제품명 또는 성분 검색').fill('없는 제품');

  await expect(page.getByText('검색 결과가 없어요.')).toBeVisible();
  await expect(page.getByRole('group', { name: '검색 결과 정렬' })).toHaveCount(0);
  await expect(page.getByRole('group', { name: '정렬 방향' })).toHaveCount(0);
});

test('이전 검색의 지연된 더 보기 응답을 새 검색 결과에 섞지 않는다', async ({ page }) => {
  test.skip(!IS_REAL_API, '실 API 경계의 지연 응답 경합을 확인하는 테스트입니다.');
  let releaseOldPage: () => void = () => undefined;
  let markOldPageStarted: () => void = () => undefined;
  const oldPageGate = new Promise<void>((resolve) => {
    releaseOldPage = resolve;
  });
  const oldPageStarted = new Promise<void>((resolve) => {
    markOldPageStarted = resolve;
  });
  await page.route('**/api/v1/med/nutr?*', async (route) => {
    const searchParams = new URL(route.request().url()).searchParams;
    const name = searchParams.get('name');
    const offset = Number(searchParams.get('offset'));
    if (name === '비타민' && offset === 1) {
      markOldPageStarted();
      await oldPageGate;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{ ...SEARCH_PRODUCT_RESPONSE, id: 2049, name: '오래된 추가 결과' }],
          total: 2,
          offset: 1,
          limit: 20,
        }),
      });
      return;
    }
    const product =
      name === '철분'
        ? { ...SEARCH_PRODUCT_RESPONSE, id: 3050, name: '새 철분 결과' }
        : { ...SEARCH_PRODUCT_RESPONSE, id: 2048, name: '기존 비타민 결과' };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [product], total: 2, offset: 0, limit: 20 }),
    });
  });
  await page.goto('/dev/supplements?tab=browse');

  const search = page.getByPlaceholder('제품명 또는 성분 검색');
  await search.fill('비타민');
  await expect(page.getByText('기존 비타민 결과')).toBeVisible();
  await page.getByRole('button', { name: '더 보기' }).click();
  await oldPageStarted;

  await search.fill('철분');
  await expect(page.getByText('새 철분 결과')).toBeVisible();
  await expect(page.getByRole('button', { name: '더 보기' })).toBeEnabled();

  const oldPageResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.searchParams.get('name') === '비타민' && url.searchParams.get('offset') === '1';
  });
  releaseOldPage();
  await oldPageResponse;
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));

  await expect(page.getByText('새 철분 결과')).toBeVisible();
  await expect(page.getByText('오래된 추가 결과')).toHaveCount(0);
});

test('새 첫 페이지를 조회하는 동안 이전 결과의 offset으로 더 보기를 요청하지 않는다', async ({
  page,
}) => {
  test.skip(!IS_REAL_API, '실 API 경계의 검색 페이지 키 격리를 확인하는 테스트입니다.');
  let releaseNewFirstPage: () => void = () => undefined;
  const newFirstPageGate = new Promise<void>((resolve) => {
    releaseNewFirstPage = resolve;
  });
  let newQueryLoadMoreRequests = 0;
  await page.route('**/api/v1/med/nutr?*', async (route) => {
    const searchParams = new URL(route.request().url()).searchParams;
    const name = searchParams.get('name');
    const offset = Number(searchParams.get('offset'));
    if (name === '철분' && offset > 0) {
      newQueryLoadMoreRequests += 1;
    }
    if (name === '철분' && offset === 0) {
      await newFirstPageGate;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            ...SEARCH_PRODUCT_RESPONSE,
            id: name === '철분' ? 3050 : 2048,
            name: name === '철분' ? '새 철분 결과' : '기존 비타민 결과',
          },
        ],
        total: 2,
        offset,
        limit: 20,
      }),
    });
  });
  await page.goto('/dev/supplements?tab=browse');

  const search = page.getByPlaceholder('제품명 또는 성분 검색');
  await search.fill('비타민');
  await expect(page.getByText('기존 비타민 결과')).toBeVisible();

  await search.fill('철분');
  const loadMore = page.getByRole('button', { name: '더 보기' });
  try {
    await expect(loadMore).toBeDisabled();
    await loadMore.evaluate((button: HTMLButtonElement) => button.click());
    expect(newQueryLoadMoreRequests).toBe(0);
  } finally {
    releaseNewFirstPage();
  }
  await expect(page.getByText('새 철분 결과')).toBeVisible();
  expect(newQueryLoadMoreRequests).toBe(0);
});

test('375px에서도 정렬 칩 네 개가 한 줄에 들어가고 가로로 넘치지 않는다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  if (IS_REAL_API) {
    await page.route('**/api/v1/med/nutr?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [SEARCH_PRODUCT_RESPONSE],
          total: 1,
          offset: 0,
          limit: 20,
        }),
      });
    });
  }
  await page.goto('/dev/supplements?tab=browse');
  await page
    .getByPlaceholder('제품명 또는 성분 검색')
    .fill(IS_REAL_API ? '비타민' : '센트룸');

  const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
  await expect(sorts.getByRole('button')).toHaveCount(4);
  await expect(page.getByRole('group', { name: '정렬 방향' }).getByRole('button')).toHaveCount(2);
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
