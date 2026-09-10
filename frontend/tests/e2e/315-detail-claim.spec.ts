import { expect, test, type Page, type Route } from 'playwright/test';

const name = '상세에서 달성을 확인하는 챌린지';
const badgeName = '꾸준한 실천의 배지';
const detailUrl = '/challenges/custom-participations/701';
const api = '**/api/v1/user/custom-challenge-participations/701';
const actualAward = { id: 91, participationId: 701, badgeId: 31, badgeName, badgeImagePath: '/media/claim-award.svg', awardedAt: '2026-09-10T10:00:00+09:00' };
function item(status = 'ACTIVE', complete = true, kind = 'MEDICATION') {
  return {
    id: 701, templateId: 31, challengeType: kind, challengeName: name, status,
    rewardBadge: { id: 31, name: badgeName, description: '', imagePath: '/media/claim-award.svg' },
    joinedAt: '2026-09-09T07:00:00+09:00', endAt: '2026-09-20T00:00:00+09:00', actualEndDate: '2026-09-10',
    targetCount: 3, completedCount: complete ? 3 : 2, progressRate: complete ? '100.00' : '66.67',
    targetDayCount: 2, completedDayCount: complete ? 2 : 1, dayProgressRate: complete ? '100.00' : '50.00', action: 'NONE',
    targets: [{ id: 801, sourceId: 41, name: '내 실제 목표' }],
    occurrences: [
      { id: 901, targetId: 801, scheduledDate: '2026-09-09', slot: 'MORNING', scheduledAt: '2026-09-09T08:00:00+09:00', isCompleted: true },
      { id: 902, targetId: 801, scheduledDate: '2026-09-10', slot: 'MORNING', scheduledAt: '2026-09-10T08:00:00+09:00', isCompleted: true },
      { id: 903, targetId: 801, scheduledDate: '2026-09-10', slot: 'EVENING', scheduledAt: '2026-09-10T19:00:00+09:00', isCompleted: complete },
    ],
  };
}
const gate = () => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  return { pending, release };
};
const dialog = (page: Page) => page.getByRole('dialog', { name: '배지를 획득했어요!' });
async function focus(page: Page, dose = false) {
  await page.evaluate(dose => window.dispatchEvent(new Event(dose ? 'rxvita:custom-challenge-progress-invalidated' : 'focus')), dose);
}
async function setup(page: Page, initial = item()) {
  const state = { current: initial, claims: 0, reads: 0, awarded: false };
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'claim-fixture-token');
    sessionStorage.setItem('poke.account-principal', 'claim@example.invalid');
  });
  await page.route(/fonts\.(googleapis|gstatic)\.com/, route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/media/claim-award.svg', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192"><circle cx="96" cy="96" r="86" fill="#087d7d"/><path d="m48 94 32 34 65-68" fill="none" stroke="white" stroke-width="13"/></svg>' }));
  await page.route(api, async route => { state.reads += 1; await route.fulfill({ json: state.current }); });
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [state.current], totalCount: 1 } }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: { items: state.awarded ? [actualAward] : [], totalCount: state.awarded ? 1 : 0 } }));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/medications/doses*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/user-suppl-nutr*', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null } }));
  await page.route('**/api/v1/display/med/nutr/rank*', route => route.fulfill({ status: 204 }));
  const completeClaim = async (route: Route) => {
    expect(route.request().method()).toBe('POST');
    state.claims += 1;
    const newlyAwarded = !state.awarded;
    state.awarded = true;
    state.current = { ...state.current, status: 'COMPLETED' };
    await route.fulfill({ json: { participation: state.current, award: actualAward, newlyAwarded } });
  };
  await page.route(`${api}/claim-reward`, completeClaim);
  return { state, completeClaim };
}

for (const kind of ['MEDICATION', 'SUPPLEMENT']) test(`${kind}: first eligible detail entry claims actual award once and preserves the final result on revisit`, async ({ page }, testInfo) => {
  const { state } = await setup(page, item('ACTIVE', true, kind));
  await page.goto(detailUrl);
  await expect(dialog(page)).toBeVisible();
  await expect(dialog(page).getByRole('img', { name: badgeName })).toBeVisible();
  await expect(dialog(page).getByRole('button', { name: '확인', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`${kind.toLowerCase()}-detail-award.png`) });
  await dialog(page).getByRole('button', { name: '확인', exact: true }).click();
  await expect(page.getByRole('heading', { name: '획득 배지', exact: true })).toBeVisible();
  await expect(page.getByText(/달성 시 확정된 결과/)).toBeVisible();
  await focus(page, true);
  await expect.poll(() => state.reads).toBeGreaterThan(1);
  expect(state.claims).toBe(1);
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  await expect(page.getByRole('region', { name: '진행 중인 챌린지', exact: true }).getByRole('article', { name })).toHaveCount(0);
  await page.getByRole('button', { name: '지난 기록 펼치기' }).click();
  const history = page.getByRole('region', { name: '지난 기록', exact: true });
  await expect(history.getByRole('article', { name })).toContainText('달성');
  await history.getByRole('link', { name: `${name} 자세히 보기` }).click();
  await expect.poll(() => state.claims).toBe(2);
  await expect(dialog(page)).toHaveCount(0);
  await page.reload();
  await expect.poll(() => state.claims).toBe(3);
  await expect(dialog(page)).toHaveCount(0);
});

test('100% Home and My listing never claim or celebrate before detail entry', async ({ page }) => {
  const { state } = await setup(page);
  await page.goto('/home');
  await expect(page.getByRole('link', { name: new RegExp(name) })).toBeVisible();
  await focus(page, true);
  await page.goto('/challenges');
  await expect(page.getByRole('article', { name })).toBeVisible();
  await focus(page);
  expect(state.claims).toBe(0);
  await expect(dialog(page)).toHaveCount(0);
});

for (const status of ['ACTIVE', 'CANCELLED', 'EXPIRED', 'ZERO']) test(`${status}: ineligible goals never claim even if a percentage says 100`, async ({ page }) => {
  const candidate = item(status === 'ZERO' ? 'ACTIVE' : status, status !== 'ACTIVE');
  if (status === 'ZERO') candidate.occurrences = [];
  candidate.progressRate = candidate.dayProgressRate = '100.00';
  const { state } = await setup(page, candidate);
  await page.goto(detailUrl);
  await expect(page.getByRole('progressbar')).toBeVisible();
  await focus(page, true);
  expect(state.claims).toBe(0);
  await expect(dialog(page)).toHaveCount(0);
});

test('already-awarded completed detail keeps badge card without celebration', async ({ page }) => {
  const { state } = await setup(page, item('COMPLETED'));
  state.awarded = true;
  await page.goto(detailUrl);
  await expect.poll(() => state.claims).toBe(1);
  await expect(page.getByRole('heading', { name: '획득 배지', exact: true })).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
});

test('completed but unclaimed detail presents only the newly returned award', async ({ page }) => {
  await setup(page, item('COMPLETED'));
  await page.goto(detailUrl);
  await expect(dialog(page)).toBeVisible();
});

test('server undo race replaces stale 100% and does not loop or invent a badge', async ({ page }) => {
  const { state, completeClaim } = await setup(page);
  await page.route(`${api}/claim-reward`, async route => {
    state.claims += 1;
    state.current = item('ACTIVE', false);
    await route.fulfill({ json: { participation: state.current, award: null, newlyAwarded: false } });
  });
  await page.goto(detailUrl);
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
  await focus(page, true);
  expect(state.claims).toBe(1);
  await expect(dialog(page)).toHaveCount(0);
  state.current = item();
  await page.route(`${api}/claim-reward`, completeClaim);
  await focus(page);
  await expect(dialog(page)).toBeVisible();
});

test('pending claim disables cancellation and coalesces focus/invalidation without duplicate POSTs', async ({ page }) => {
  const { state, completeClaim } = await setup(page);
  const held = gate();
  let started = false;
  await page.route(`${api}/claim-reward`, async route => { started = true; await held.pending; await completeClaim(route); });
  await page.goto(detailUrl);
  await expect.poll(() => started).toBe(true);
  await expect(page.getByText('달성 결과 확인 중...')).toBeVisible();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소', exact: true })).toBeDisabled();
  await focus(page); await focus(page, true);
  held.release();
  await expect(dialog(page)).toBeVisible();
  expect(state.claims).toBe(1);
});

test('claim failure stays retryable and a successful explicit retry presents once', async ({ page }) => {
  const { completeClaim } = await setup(page);
  let failed = false;
  await page.route(`${api}/claim-reward`, async route => {
    if (!failed) { failed = true; await route.fulfill({ status: 503, json: { message: '잠시 뒤 다시 시도해주세요.' } }); }
    else await completeClaim(route);
  });
  await page.goto(detailUrl);
  await expect(page.getByRole('button', { name: '달성 확인 다시 시도' })).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
  await page.getByRole('button', { name: '달성 확인 다시 시도' }).click();
  await expect(dialog(page)).toBeVisible();
});

test('claim 401 expires quietly without a retry error or award', async ({ page }) => {
  await setup(page);
  await page.route(`${api}/claim-reward`, route => route.fulfill({ status: 401, json: { message: 'expired' } }));
  await page.goto(detailUrl);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('button', { name: '달성 확인 다시 시도' })).toHaveCount(0);
  await expect(dialog(page)).toHaveCount(0);
});

test('a late claim after SPA route departure cannot celebrate or replace another page', async ({ page }) => {
  const { completeClaim } = await setup(page);
  const held = gate(); let started = false;
  await page.route(`${api}/claim-reward`, async route => { started = true; await held.pending; await completeClaim(route); });
  await page.goto(detailUrl);
  await expect.poll(() => started).toBe(true);
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  const response = page.waitForResponse(response => response.url().endsWith('/701/claim-reward'));
  held.release();
  await (await response).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  // The list may already reflect the server-side completion in collapsed history.
  await expect(page.getByRole('heading', { name: '챌린지', exact: true })).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
});

test('a late claim is ignored when browser location changes before React route cleanup', async ({ page }) => {
  const { completeClaim } = await setup(page);
  const held = gate(); let started = false;
  await page.route(`${api}/claim-reward`, async route => { started = true; await held.pending; await completeClaim(route); });
  await page.goto(detailUrl);
  await expect.poll(() => started).toBe(true);
  // Hold the browser/React boundary: the URL has changed, but route cleanup has not run yet.
  await page.evaluate(() => window.history.pushState({}, '', '/challenges'));
  await expect(page).toHaveURL(/\/challenges$/);
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  const response = page.waitForResponse(response => response.url().endsWith('/701/claim-reward'));
  held.release();
  await (await response).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(dialog(page)).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '획득 배지', exact: true })).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new PopStateEvent('popstate')));
  await expect(page.getByRole('heading', { name: '챌린지', exact: true })).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
});

test('late old-auth claim cannot show an award after session expiry', async ({ page }) => {
  const { completeClaim } = await setup(page);
  const held = gate(); let started = false;
  await page.route(`${api}/claim-reward`, async route => { started = true; await held.pending; await completeClaim(route); });
  await page.goto(detailUrl);
  await expect.poll(() => started).toBe(true);
  await page.evaluate(() => window.dispatchEvent(new Event('poke:auth-session-expired')));
  await expect(page).toHaveURL(/\/login$/);
  const response = page.waitForResponse(response => response.url().endsWith('/701/claim-reward'));
  held.release();
  await (await response).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  await expect(dialog(page)).toHaveCount(0);
});

test('a pending cancellation prevents a focus refresh from starting a claim', async ({ page }) => {
  const { state } = await setup(page, item('ACTIVE', false));
  const held = gate(); let started = false;
  await page.route(`${api}/cancel`, async route => {
    started = true; await held.pending;
    state.current = item('CANCELLED', false);
    await route.fulfill({ json: state.current });
  });
  await page.goto(detailUrl);
  await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
  await page.getByRole('button', { name: '참여 취소', exact: true }).click();
  await expect.poll(() => started).toBe(true);
  state.current = item();
  const readsBeforeFocus = state.reads;
  await focus(page, true);
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  expect(state.reads).toBe(readsBeforeFocus);
  expect(state.claims).toBe(0);
  held.release();
  await expect(page.getByRole('button', { name: '내 챌린지로 돌아가기' })).toBeVisible();
  await focus(page);
  expect(state.claims).toBe(0);
  await expect(dialog(page)).toHaveCount(0);
});

test('a cancellation conflict refreshes completed server state and waits for the cancel dialog before presenting', async ({ page }) => {
  const { state } = await setup(page, item('ACTIVE', false));
  await page.route(`${api}/cancel`, async route => {
    state.current = item('COMPLETED');
    await route.fulfill({ status: 409, json: { message: '이미 달성한 챌린지예요.' } });
  });
  await page.goto(detailUrl);
  await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
  await page.getByRole('button', { name: '참여 취소', exact: true }).click();
  await expect.poll(() => state.claims).toBe(1);
  await expect(dialog(page)).toHaveCount(0);
  await page.getByRole('button', { name: '돌아가기', exact: true }).click();
  await expect(dialog(page)).toBeVisible();
});

test('320px reduced-motion detail award exposes confirmation without overflow', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await setup(page);
  await page.goto(detailUrl);
  await expect(dialog(page)).toHaveAttribute('data-phase', 'ready');
  await expect(dialog(page).getByRole('button', { name: '확인', exact: true })).toBeInViewport();
  const box = (await dialog(page).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(320);
  await page.screenshot({ path: testInfo.outputPath('detail-award-320-reduced.png') });
});

test('newlyAwarded without an actual award never creates a presentation', async ({ page }) => {
  const { state } = await setup(page);
  await page.route(`${api}/claim-reward`, async route => {
    state.claims += 1; state.current = item('COMPLETED');
    await route.fulfill({ json: { participation: state.current, award: null, newlyAwarded: true } });
  });
  await page.goto(detailUrl);
  await expect.poll(() => state.claims).toBe(1);
  await expect(page.getByRole('heading', { name: '최종 결과' })).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
});
