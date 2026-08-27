import { expect, test } from 'playwright/test';

const useMock = process.env.VITE_USE_MOCK !== 'false';

async function loadRanking(
  page: import('playwright/test').Page,
  limit?: number,
): Promise<unknown> {
  return page.evaluate(async (requestedLimit) => {
    const supplementApi = await import('/src/entities/supplement/api.ts');
    const getSupplementRanking = Reflect.get(supplementApi, 'getSupplementRanking');
    if (typeof getSupplementRanking !== 'function') return null;
    return getSupplementRanking(requestedLimit);
  }, limit);
}

test('목업 랭킹은 서버 기준 문구와 순위를 포함한 기본 5개를 반환한다', async ({ page }) => {
  test.skip(!useMock, '목업 모드 계약입니다.');
  await page.goto('/dev/gallery');

  const ranking = await loadRanking(page);

  expect(ranking).toEqual({
    basis: '최근 7일 등록 수',
    periodDays: 7,
    items: [
      {
        rank: 1,
        productId: 'P00123',
        productName: '오메가3',
        registeredCount: 1240,
        alreadyRegistered: false,
      },
      {
        rank: 2,
        productId: 'P00456',
        productName: '종합비타민',
        registeredCount: 980,
        alreadyRegistered: false,
      },
      {
        rank: 3,
        productId: 'P00777',
        productName: '비타민D',
        registeredCount: 870,
        alreadyRegistered: true,
      },
      {
        rank: 4,
        productId: 'P00901',
        productName: '마그네슘',
        registeredCount: 760,
        alreadyRegistered: false,
      },
      {
        rank: 5,
        productId: 'P01111',
        productName: '유산균',
        registeredCount: 650,
        alreadyRegistered: false,
      },
    ],
  });
});

test('목업 랭킹은 요청한 limit만큼 서버 순위 순서를 유지한다', async ({ page }) => {
  test.skip(!useMock, '목업 모드 계약입니다.');
  await page.goto('/dev/gallery');

  const ranking = await loadRanking(page, 3);

  expect(ranking).toEqual({
    basis: '최근 7일 등록 수',
    periodDays: 7,
    items: [
      {
        rank: 1,
        productId: 'P00123',
        productName: '오메가3',
        registeredCount: 1240,
        alreadyRegistered: false,
      },
      {
        rank: 2,
        productId: 'P00456',
        productName: '종합비타민',
        registeredCount: 980,
        alreadyRegistered: false,
      },
      {
        rank: 3,
        productId: 'P00777',
        productName: '비타민D',
        registeredCount: 870,
        alreadyRegistered: true,
      },
    ],
  });
});

test('실 API 랭킹은 limit 쿼리를 붙인 v1 계약을 그대로 호출한다', async ({ page }) => {
  test.skip(useMock, '실 API 분기 계약입니다.');
  let requestedUrl: string | undefined;
  await page.route('**/api/v1/supplements/ranking?limit=3', async (route) => {
    requestedUrl = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        basis: '최근 7일 등록 수',
        periodDays: 7,
        items: [
          {
            rank: 1,
            productId: 'P00123',
            productName: '오메가3',
            registeredCount: 1240,
            alreadyRegistered: false,
          },
        ],
      }),
    });
  });
  await page.goto('/dev/gallery');

  const ranking = await loadRanking(page, 3);

  expect(ranking).toEqual({
    basis: '최근 7일 등록 수',
    periodDays: 7,
    items: [
      {
        rank: 1,
        productId: 'P00123',
        productName: '오메가3',
        registeredCount: 1240,
        alreadyRegistered: false,
      },
    ],
  });
  expect(requestedUrl).toBeDefined();
  const request = new URL(requestedUrl!);
  expect(`${request.pathname}${request.search}`).toBe(
    '/api/v1/supplements/ranking?limit=3',
  );
});
