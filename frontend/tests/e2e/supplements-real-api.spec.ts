import { expect, test, type Page, type Route } from 'playwright/test';

const ACCESS_TOKEN = 'e2e-supplement-token';

const IRON_PRODUCT = {
  id: 701,
  food_code: 'SUPPL-IRON-701',
  name: '튼튼 철분 캡슐',
  basis_qty: '1000mg',
  energy_kcal: 0,
  water_g: null,
  protein_g: '0.00',
  fat_g: null,
  ash_g: null,
  carb_g: '0.00',
  sugar_g: null,
  fiber_g: null,
  calcium_mg: null,
  iron_mg: '24.00',
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
  serving_desc: '2캡슐',
  serving_size: '1000mg',
  daily_freq: '2회',
  target: '성인',
};

const HALF_SCOOP_PRODUCT = {
  ...IRON_PRODUCT,
  id: 702,
  food_code: 'SUPPL-HALF-SCOOP-702',
  name: '하프 스쿱 철분',
  serving_desc: '0.5스쿱',
  daily_freq: '1회',
};

const DROPS_PRODUCT = {
  ...IRON_PRODUCT,
  id: 703,
  food_code: 'SUPPL-DROPS-703',
  name: '데일리 비타민 드롭',
  iron_mg: null,
  serving_desc: '30방울',
  serving_size: '30ml',
  daily_freq: '1회',
};

test.beforeEach(() => {
  test.skip(
    process.env.VITE_USE_MOCK !== 'false',
    '이 파일은 영양제 entity의 실 API 분기(VITE_USE_MOCK=false)를 검증합니다.',
  );
});

async function authenticate(page: Page) {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'supplement-e2e@example.com');
  }, ACCESS_TOKEN);
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function registrationFor(
  product: typeof IRON_PRODUCT,
  id: number,
  doseAmount: number | string,
) {
  return {
    id,
    dose_amount: doseAmount,
    dose_unit: product.serving_desc.replace(/^\d+(?:[.,]\d+)?\s*/, ''),
    start_date: koreanToday(),
    end_date: null,
    status: 'ACTIVE',
    note: null,
    created_at: '2026-08-27T09:00:00+09:00',
    updated_at: null,
    slots: [{ slot: 'MORNING', time: '08:00:00' }],
    supplement: product,
  };
}

test('제품명 검색을 실제 RDB 검색 API 계약으로 보낸다', async ({ page }) => {
  await authenticate(page);
  const searchRequests: URL[] = [];

  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    searchRequests.push(new URL(route.request().url()));
    await fulfillJson(route, {
      items: [IRON_PRODUCT],
      total: 1,
      offset: 0,
      limit: 20,
    });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  await page.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');

  await expect(page.getByText('튼튼 철분 캡슐', { exact: true })).toBeVisible();
  await expect.poll(() => searchRequests.length).toBe(1);
  expect(searchRequests[0].pathname).toBe('/api/v1/med/nutr');
  expect(searchRequests[0].searchParams.get('name')).toBe('철분');
  expect(searchRequests[0].searchParams.get('offset')).toBe('0');
  expect(searchRequests[0].searchParams.get('limit')).toBe('20');
});

test('이전 검색의 지연된 다음 페이지를 새 검색 결과에 섞지 않는다', async ({ page }) => {
  await authenticate(page);
  let releaseOldPage: () => void = () => {};
  let markOldPageRequested: () => void = () => {};
  const oldPageGate = new Promise<void>((resolve) => {
    releaseOldPage = resolve;
  });
  const oldPageRequested = new Promise<void>((resolve) => {
    markOldPageRequested = resolve;
  });
  const vitaminProducts = Array.from({ length: 40 }, (_, index) => ({
    ...IRON_PRODUCT,
    id: 1_000 + index,
    food_code: `SUPPL-VITAMIN-${index}`,
    name: `비타민 제품 ${index + 1}`,
  }));

  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    const url = new URL(route.request().url());
    const name = url.searchParams.get('name');
    const offset = Number(url.searchParams.get('offset'));
    if (name === '비타민' && offset === 20) {
      markOldPageRequested();
      await oldPageGate;
      await fulfillJson(route, {
        items: vitaminProducts.slice(20),
        total: vitaminProducts.length,
        offset: 20,
        limit: 20,
      });
      return;
    }
    if (name === '비타민') {
      await fulfillJson(route, {
        items: vitaminProducts.slice(0, 20),
        total: vitaminProducts.length,
        offset: 0,
        limit: 20,
      });
      return;
    }
    await fulfillJson(route, { items: [IRON_PRODUCT], total: 1, offset: 0, limit: 20 });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  const sheet = page.getByRole('dialog');
  const search = sheet.getByRole('searchbox', { name: '영양제 제품 검색' });
  const results = sheet.getByRole('list', { name: '검색 결과' });
  await search.fill('비타민');
  await expect(results.getByRole('listitem')).toHaveCount(20);
  await results.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event('scroll'));
  });
  await oldPageRequested;

  await search.fill('철분');
  await expect(results.getByText('튼튼 철분 캡슐', { exact: true })).toBeVisible();
  releaseOldPage();

  await expect(results.getByRole('listitem')).toHaveCount(1);
  await expect(results.getByText(/^비타민 제품 /)).toHaveCount(0);
});

test('권장 슬롯과 회당 수량을 선택해 med 사용자 영양제 API에 저장한다', async ({ page }) => {
  await authenticate(page);
  let savedRequest: { path: string; body: Record<string, unknown> } | null = null;

  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET') {
      await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
      return;
    }
    savedRequest = {
      path,
      body: request.postDataJSON() as Record<string, unknown>,
    };
    await fulfillJson(route, {
      id: 9001,
      dose_amount: '3.000',
      dose_unit: '캡슐',
      start_date: koreanToday(),
      end_date: null,
      status: 'ACTIVE',
      note: null,
      created_at: '2026-08-27T09:00:00+09:00',
      updated_at: null,
      slots: [{ slot: 'LUNCH', time: '13:00:00' }],
      supplement: IRON_PRODUCT,
    });
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    await fulfillJson(route, {
      items: [IRON_PRODUCT],
      total: 1,
      offset: 0,
      limit: 20,
    });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');
  const product = sheet.getByRole('listitem').filter({ hasText: '튼튼 철분 캡슐' });
  await product.getByRole('button', { name: /튼튼 철분 캡슐/ }).click();

  await expect(product.getByText('2캡슐 · 1000mg · 1일 2회', { exact: true })).toBeVisible();
  await expect(product.getByText('2 캡슐', { exact: true })).toBeVisible();
  const morning = product.getByRole('button', { name: '아침' });
  const lunch = product.getByRole('button', { name: '점심' });
  const evening = product.getByRole('button', { name: '저녁' });
  const bedtime = product.getByRole('button', { name: '취침' });
  await expect(morning).toHaveAttribute('aria-pressed', 'true');
  await expect(lunch).toHaveAttribute('aria-pressed', 'false');
  await expect(evening).toHaveAttribute('aria-pressed', 'true');
  await expect(bedtime).toHaveAttribute('aria-pressed', 'false');

  await morning.click();
  await evening.click();
  await expect(product.getByText('복용 시간을 하나 이상 선택해주세요.')).toBeVisible();
  await expect(product.getByRole('button', { name: '추가하기' })).toBeDisabled();
  await lunch.click();
  await product.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await product.getByRole('button', { name: '추가하기' }).click();

  await expect(sheet).toBeHidden();
  expect(savedRequest).toEqual({
    path: '/api/v1/med/user-suppl-nutr/701',
    body: {
      dose_amount: 3,
      dose_unit: '캡슐',
      start_date: koreanToday(),
      end_date: null,
      slots: ['LUNCH'],
      note: null,
    },
  });
  const firstSupplement = page
    .getByRole('region', { name: '먹고 있는 영양제' })
    .getByRole('button')
    .first();
  await expect(firstSupplement).toContainText('튼튼 철분 캡슐');
  await expect(firstSupplement).toContainText('하루 1회 · 1회 3캡슐 · 점심');
});

test('RDB의 소수 및 20 초과 1회 섭취량을 그대로 선택하고 저장한다', async ({ page }) => {
  await authenticate(page);
  const savedDoseAmounts: unknown[] = [];

  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
      return;
    }
    const doseAmount = (route.request().postDataJSON() as { dose_amount: unknown }).dose_amount;
    savedDoseAmounts.push(doseAmount);
    const product = route.request().url().endsWith('/703') ? DROPS_PRODUCT : HALF_SCOOP_PRODUCT;
    await fulfillJson(route, registrationFor(product, 9_000 + savedDoseAmounts.length, doseAmount as number));
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    const name = new URL(route.request().url()).searchParams.get('name');
    const product = name === '방울' ? DROPS_PRODUCT : HALF_SCOOP_PRODUCT;
    await fulfillJson(route, { items: [product], total: 1, offset: 0, limit: 20 });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  let sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('방울');
  let product = sheet.getByRole('listitem').filter({ hasText: DROPS_PRODUCT.name });
  await product.getByRole('button', { name: new RegExp(DROPS_PRODUCT.name) }).click();
  await expect(product.getByText('30 방울', { exact: true })).toBeVisible();
  await expect(product.getByRole('button', { name: '1회 섭취량 늘리기' })).toBeEnabled();
  await product.getByRole('button', { name: '추가하기' }).click();

  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('스쿱');
  product = sheet.getByRole('listitem').filter({ hasText: HALF_SCOOP_PRODUCT.name });
  await product.getByRole('button', { name: new RegExp(HALF_SCOOP_PRODUCT.name) }).click();
  await expect(product.getByText('0.5 스쿱', { exact: true })).toBeVisible();
  await expect(product.getByRole('button', { name: '1회 섭취량 줄이기' })).toBeDisabled();
  await product.getByRole('button', { name: '추가하기' }).click();

  expect(savedDoseAmounts).toEqual([30, 0.5]);
  await expect(
    page.getByRole('article', { name: '철 성분 합계' }).getByText('24', { exact: true }),
  ).toBeVisible();
});

test('같은 RDB 제품 재등록은 목록을 교체하고 새로고침 뒤에도 한 건으로 유지한다', async ({ page }) => {
  await authenticate(page);
  const listRequests: URL[] = [];
  let activeRegistration = {
    id: 9001,
    dose_amount: '1.000',
    dose_unit: '캡슐',
    start_date: koreanToday(),
    end_date: null,
    status: 'ACTIVE',
    note: null,
    created_at: '2026-08-27T09:00:00+09:00',
    updated_at: null,
    slots: [{ slot: 'MORNING', time: '08:00:00' }],
    supplement: IRON_PRODUCT,
  };

  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    if (route.request().method() === 'GET') {
      listRequests.push(new URL(route.request().url()));
      await fulfillJson(route, {
        items: [activeRegistration],
        total: 1,
        offset: 0,
        limit: 100,
      });
      return;
    }
    activeRegistration = {
      ...activeRegistration,
      dose_amount: '2.000',
      updated_at: '2026-08-27T10:00:00+09:00',
      slots: [{ slot: 'BEDTIME', time: '22:00:00' }],
    };
    await fulfillJson(route, activeRegistration);
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    await fulfillJson(route, { items: [IRON_PRODUCT], total: 1, offset: 0, limit: 20 });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await expect(page.getByText('먹고 있는 영양제 1개')).toBeVisible();
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');
  const product = sheet.getByRole('listitem').filter({ hasText: '튼튼 철분 캡슐' });
  await product.getByRole('button', { name: /튼튼 철분 캡슐/ }).click();
  await product.getByRole('button', { name: '아침' }).click();
  await product.getByRole('button', { name: '저녁' }).click();
  await product.getByRole('button', { name: '취침' }).click();
  await product.getByRole('button', { name: '추가하기' }).click();

  const list = page.getByRole('region', { name: '먹고 있는 영양제' });
  await expect(list.getByRole('button')).toHaveCount(1);
  await expect(list.getByRole('button').first()).toContainText('하루 1회 · 1회 2캡슐 · 취침');

  await page.reload();
  await expect(page.getByText('먹고 있는 영양제 1개')).toBeVisible();
  await expect(list.getByRole('button')).toHaveCount(1);
  await expect(list.getByRole('button').first()).toContainText('하루 1회 · 1회 2캡슐 · 취침');
  expect(listRequests.length).toBeGreaterThanOrEqual(2);
  expect(listRequests.every((request) => request.searchParams.get('status') === 'ACTIVE')).toBe(true);
  expect(listRequests.every((request) => request.searchParams.get('offset') === '0')).toBe(true);
  expect(listRequests.every((request) => request.searchParams.get('limit') === '100')).toBe(true);
});

test('검색 실패 시 FastAPI detail 메시지를 시트 안에 표시한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    await fulfillJson(route, { detail: '영양제 검색 서버가 응답하지 않았습니다.' }, 500);
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');

  await expect(sheet.getByText('영양제 검색 서버가 응답하지 않았습니다.')).toBeVisible();
  await expect(sheet).toBeVisible();
});

test('저장 실패 시 FastAPI detail 메시지를 보여주고 선택 시트를 유지한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
      return;
    }
    await fulfillJson(
      route,
      {
        detail: [
          {
            type: 'greater_than',
            loc: ['body', 'dose_amount'],
            msg: 'Input should be greater than 0',
            input: 0,
          },
        ],
      },
      422,
    );
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    await fulfillJson(route, { items: [IRON_PRODUCT], total: 1, offset: 0, limit: 20 });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');
  const product = sheet.getByRole('listitem').filter({ hasText: '튼튼 철분 캡슐' });
  await product.getByRole('button', { name: /튼튼 철분 캡슐/ }).click();
  await product.getByRole('button', { name: '추가하기' }).click();

  await expect(
    page.getByRole('dialog', { name: '영양제를 추가하지 못했어요' }),
  ).toContainText('Input should be greater than 0');
  await expect(sheet).toBeVisible();
});

function koreanToday(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}
