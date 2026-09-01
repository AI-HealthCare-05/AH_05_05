import { expect, test } from 'playwright/test';

const IS_REAL_API = process.env.VITE_USE_MOCK === 'false';

test('영양제 기본 화면은 내 영양제이고 쿼리로 둘러보기를 연다', async ({ page }) => {
  test.skip(IS_REAL_API, '고정된 내 영양제 목록을 확인하는 목업 전용 테스트입니다.');
  await page.goto('/dev/supplements');

  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await expect(tabs.getByRole('button', { name: '내 영양제' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
  await expect(page.getByLabel('영양제 추가', { exact: true })).toBeVisible();

  await page.goto('/dev/supplements?tab=browse');

  await expect(tabs.getByRole('button', { name: '둘러보기' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByLabel('영양제 추가', { exact: true })).toBeVisible();
});

test('탭을 반복해서 바꿔도 replace 이동이라 브라우저 이력이 쌓이지 않는다', async ({ page }) => {
  await page.goto('/dev/gallery');
  await page.goto('/dev/supplements');

  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await tabs.getByRole('button', { name: '둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);
  await tabs.getByRole('button', { name: '내 영양제' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements$/);
  await tabs.getByRole('button', { name: '둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/supplements\?tab=browse$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/dev\/gallery$/);
});

test('둘러보기에서 내 영양제로 돌아오면 기존 목록과 성분 합계가 그대로 보인다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, '고정된 내 영양제 목록과 합계를 확인하는 목업 전용 테스트입니다.');
  await page.goto('/dev/supplements?tab=browse');

  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await tabs.getByRole('button', { name: '내 영양제' }).click();

  await expect(page.getByRole('heading', { name: /먹고 있는 영양제/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: '성분 합계' })).toBeVisible();
  await expect(page.getByText(/등록한 건강기능식품 .*개만 더한 값입니다/)).toBeVisible();
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

  await page.getByPlaceholder('제품명을 검색해 주세요').fill('센트룸');
  const results = page.getByLabel('영양제 검색 결과');
  await expect(results.getByText('센트룸 실버 우먼', { exact: true })).toBeVisible();
  await expect(results.getByText('★4.2 · 12', { exact: true })).toBeVisible();
  await expect(results.getByText('★0.0 · 0', { exact: true })).toHaveCount(0);

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
      body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 20 }),
    });
  });
  await page.goto('/dev/supplements?tab=browse');

  await page.getByPlaceholder('제품명을 검색해 주세요').fill('비타민');
  await page.getByRole('button', { name: '평점순' }).click();

  await expect.poll(() => requests.at(-1)?.searchParams.get('sort')).toBe('rating');
  expect(requests.at(-1)?.searchParams.get('offset')).toBe('0');
  await expect(page).toHaveURL(/\?tab=browse$/);
});

test('375px에서도 정렬 칩 네 개가 한 줄에 들어가고 가로로 넘치지 않는다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/dev/supplements?tab=browse');

  const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
  await expect(sorts.getByRole('button')).toHaveCount(4);
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
