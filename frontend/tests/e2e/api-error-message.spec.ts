import { expect, test, type Page, type Route } from 'playwright/test';

const FALLBACK = '일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.';

test.beforeEach(() => {
  test.skip(
    process.env.VITE_USE_MOCK !== 'false',
    '이 파일은 실 API 오류 본문 정규화를 검증합니다.',
  );
});

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'e2e-api-error-token');
    window.sessionStorage.setItem('poke.account-principal', 'api-error-e2e@example.com');
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function setupProfile(page: Page) {
  await page.route('**/api/v1/me', (route) =>
    fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    }),
  );
}

test('404 string detail renders the Korean fallback instead of exposing detail', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/user-suppl-nutr**', (route) =>
    fulfillJson(route, { detail: 'Not Found' }, 404),
  );
  await setupProfile(page);

  await page.goto('/supplements');

  await expect(page.getByText(FALLBACK)).toBeVisible();
  await expect(page.getByText('Not Found')).toHaveCount(0);
});

test('development warning keeps an API diagnostic detail out of the UI', async ({ page }) => {
  const warnings: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'warning') warnings.push(message.text());
  });

  await authenticate(page);
  await page.route('**/api/v1/med/user-suppl-nutr**', (route) =>
    fulfillJson(route, { detail: 'diagnostic-request-id-404' }, 404),
  );
  await setupProfile(page);

  await page.goto('/supplements');

  await expect(page.getByText(FALLBACK)).toBeVisible();
  await expect(page.getByText('diagnostic-request-id-404')).toHaveCount(0);
  await expect.poll(() =>
    warnings.some((warning) => warning.includes('diagnostic-request-id-404')),
  ).toBe(true);
});

test('422 validation-array detail renders the Korean fallback instead of exposing detail', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/user-suppl-nutr**', (route) =>
    fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 }),
  );
  await page.route('**/api/v1/med/nutr?**', (route) =>
    fulfillJson(route, {
      detail: [{ loc: ['query', 'name'], msg: 'field required', type: 'value_error.missing' }],
    }, 422),
  );
  await setupProfile(page);

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  await page.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');

  await expect(page.getByText(FALLBACK)).toBeVisible();
  await expect(page.getByText('field required')).toHaveCount(0);
});

test('Korean server message remains visible when detail is also present', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/user-suppl-nutr**', (route) =>
    fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 }),
  );
  await page.route('**/api/v1/med/nutr?**', (route) =>
    fulfillJson(route, { message: '검색할 수 없어요.', detail: 'internal diagnostic' }, 422),
  );
  await setupProfile(page);

  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).first().click();
  await page.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('철분');

  await expect(page.getByText('검색할 수 없어요.')).toBeVisible();
  await expect(page.getByText('internal diagnostic')).toHaveCount(0);
});
