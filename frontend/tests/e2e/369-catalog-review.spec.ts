import { expect, test, type Page } from 'playwright/test';

test.skip(process.env.VITE_USE_MOCK !== 'false', 'Uses isolated challenge API responses.');
test.setTimeout(45_000);

const base = {
  id: 101, name: '매일 걷기', phrase: '매일 실천해요', description: '하루 한 번 기록해요.',
  challenge_type_code: 'OFFICIAL', period_code: 'D14', duration_days: 14,
  check_type_code: 'SELF', frequency_code: 'DAILY', reward_badge: null,
  recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00',
  can_join: false, participation_id: 501,
};
const past = { ...base, id: 102, name: '다시 걷기', can_join: true, participation_id: 502 };
const closed = { ...base, id: 103, name: '종료한 걷기', participation_id: 503 };
function participation(challenge = base, status = 'ACTIVE') {
  return {
    id: challenge.participation_id, user_id: 7, challenge_id: challenge.id, challenge_name: challenge.name,
    status, joined_at: '2026-09-08T10:00:00+09:00', started_at: '2026-09-08T00:00:00+09:00',
    end_at: '2026-09-22T00:00:00+09:00', target_count: 14, completed_count: 3, progress_rate: '21.43',
    completed_at: null, cancelled_at: null, progress_periods: [], challenge,
    today: '2026-09-10', today_verification: null, can_verify: status === 'ACTIVE', verified_dates: [],
  };
}
const recommendations = [
  { templateId: 31, challengeType: 'MEDICATION', challengeName: '처방 일정 지키기', rewardBadge: null, action: 'NONE', targets: [{ id: 41, name: '새 처방', existingParticipationId: null }] },
  { templateId: 32, challengeType: 'MEDICATION', challengeName: '참여한 처방', rewardBadge: null, action: 'NONE', targets: [{ id: 42, name: '기존 처방', existingParticipationId: 601 }] },
];

async function prepare(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'catalog-review');
    sessionStorage.setItem('poke.account-principal', 'catalog@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: { items: [base, past, closed], total_count: 3, offset: 0, limit: 100 } }));
  await page.route('**/api/v1/user/challenge-catalog/102', route => route.fulfill({ json: past }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [participation(), participation(past, 'CANCELLED'), participation(closed, 'EXPIRED')], total_count: 3 } }));
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: recommendations, totalCount: 2 } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [], totalCount: 0 } }));
}

test('browse filters official and custom entries, keeps routes and disables only active entries at the bottom', async ({ page }, testInfo) => {
  await prepare(page);
  await page.goto('/challenges/browse');
  const filter = page.getByRole('combobox', { name: '챌린지 종류 필터' });
  await expect(filter).toHaveValue('all');
  const rows = page.getByRole('region', { name: '챌린지 목록' }).getByRole('button');
  await expect(rows).toHaveCount(5);
  await expect(rows.nth(0)).toHaveAccessibleName('다시 걷기 자세히 보기');
  await expect(rows.nth(3)).toHaveAccessibleName('매일 걷기 참여중');
  await expect(rows.nth(3)).toBeDisabled();
  await expect(rows.nth(4)).toBeDisabled();
  await expect(page.getByRole('button', { name: '종료한 걷기 자세히 보기' })).toBeEnabled();
  await expect(rows.nth(0)).toContainText('모집기간 : 2026년 9월 1일 ~ 2026년 9월 30일');
  await expect(rows.nth(2)).toContainText('모집기간 : 상시');
  await page.screenshot({ path: testInfo.outputPath('browse-all-390.png'), fullPage: true });
  await filter.selectOption('official');
  await expect(rows).toHaveCount(3);
  await filter.selectOption('custom');
  await expect(rows).toHaveCount(2);
  await page.getByRole('button', { name: '처방 일정 지키기 대상 선택' }).click();
  await expect(page).toHaveURL(/\/challenges\/tailored\/medication\?templateId=31$/);
  await expect(page.getByRole('checkbox', { name: '새 처방 선택' })).toBeEnabled();
});

test('official detail shows Korean recruitment dates and the shared header while retaining rejoin confirmation', async ({ page }, testInfo) => {
  await prepare(page);
  await page.goto('/challenges/official/102');
  await expect(page.locator('header').filter({ has: page.getByRole('heading', { name: '다시 걷기', exact: true }) })).toHaveCSS('border-bottom-width', '1px');
  await expect(page.getByText('모집기간', { exact: true })).toBeVisible();
  await expect(page.getByText('2026년 9월 1일 ~ 2026년 9월 30일', { exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: '주요 화면' })).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: testInfo.outputPath('official-detail-390.png'), fullPage: true });
  await page.getByRole('button', { name: '다시 참여하기', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('my keeps browse navigation without repeated bottom actions', async ({ page }) => {
  await prepare(page);
  await page.goto('/challenges');
  await expect(page.getByRole('region', { name: '진행 중인 챌린지' }).getByRole('article')).toHaveCount(1);
  await expect(page.getByRole('link', { name: '공식 챌린지 둘러보기 ›', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '맞춤 새로 참여하기 ›', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '둘러보기', exact: true })).toHaveAttribute('href', '/challenges/browse');
});

test('target and official participation use the shared challenge header', async ({ page }) => {
  await prepare(page);
  await page.goto('/challenges/tailored/medication?templateId=31');
  await expect(page.locator('header').filter({ has: page.getByRole('heading', { name: '처방 일정 지키기', exact: true }) })).toHaveCSS('border-bottom-width', '1px');
  await page.goto('/challenges/participations/501');
  await expect(page.locator('header').filter({ has: page.getByRole('heading', { name: '매일 걷기', exact: true }) })).toHaveCSS('border-bottom-width', '1px');
  await expect(page.getByText(/내 수행 기간/)).toBeVisible();
});

test('custom recommendation and target pages omit redundant bottom return links', async ({ page }) => {
  await prepare(page);
  await page.goto('/challenges/tailored');
  await expect(page.getByText('처방 일정 지키기', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '챌린지로 돌아가기', exact: true })).toHaveCount(0);
  await page.goto('/challenges/tailored/medication?templateId=31');
  await expect(page.getByRole('checkbox', { name: '새 처방 선택' })).toBeVisible();
  await expect(page.getByRole('link', { name: '맞춤 챌린지로 돌아가기', exact: true })).toHaveCount(0);
  await expect(page.locator('header').getByRole('button')).toBeVisible();
});

test('custom browse preserves new medication targets and supplement combinations despite active targets', async ({ page }) => {
  await prepare(page);
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: [
    { ...recommendations[0], targets: [...recommendations[0].targets, ...recommendations[1].targets] },
    { ...recommendations[1], challengeType: 'SUPPLEMENT', challengeName: '영양제 함께 챙기기', targets: [
      { id: 51, name: '비타민', existingParticipationId: 701 },
      { id: 52, name: '오메가', existingParticipationId: 702 },
    ] },
  ], totalCount: 2 } }));
  await page.goto('/challenges/browse');
  await expect(page.getByRole('button', { name: '처방 일정 지키기 대상 선택' })).toBeEnabled();
  await page.getByRole('button', { name: '영양제 함께 챙기기 대상 선택' }).click();
  await expect(page).toHaveURL(/\/challenges\/tailored\/supplement\?templateId=32$/);
  await expect(page.getByRole('checkbox', { name: '비타민 선택' })).toBeEnabled();
  await expect(page.getByRole('checkbox', { name: '오메가 선택' })).toBeEnabled();
});

test('retry keeps loaded official cards visible while another catalog source is delayed', async ({ page }) => {
  await prepare(page);
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ status: 503, json: { message: '맞춤 목록 확인 필요' } }));
  await page.goto('/challenges/browse');
  const available = page.getByRole('button', { name: '다시 걷기 자세히 보기' });
  await expect(available).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/user/challenge-catalog?*', async route => {
    await gate;
    await route.fulfill({ json: { items: [base, past, closed], total_count: 3, offset: 0, limit: 100 } });
  });
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(available).toBeVisible();
  release();
});

for (const [path, label] of [['/challenges/badges', '배지 불러오는 중'], ['/challenges/badges/31', '배지 상세 불러오는 중']]) {
  test(`slow ${path} loading explains what is pending without an empty card`, async ({ page }) => {
    await prepare(page);
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
      await gate;
      await route.fulfill({ status: 503, json: { message: '잠시 후 다시 시도해주세요.' } });
    });
    await page.goto(path);
    const status = page.getByRole('status', { name: label, exact: true });
    await expect(status).toContainText('배지를 불러오고 있어요.');
    expect((await status.boundingBox())!.height).toBeLessThanOrEqual(64);
    release();
  });
}
