import { expect, test, type Page, type Route } from 'playwright/test';

test.setTimeout(60_000);
test.use({ viewport: { width: 320, height: 812 } });

const path = '/api/v1/user/custom-challenge-participations/701';
const targetName = '서울대학교병원 순환기내과에서 받은 아주 긴 참여 대상 이름';
const participation = (overrides: Record<string, unknown> = {}) => {
  const completedCount = Number(overrides.completedCount ?? 1);
  return ({
  id: 701, templateId: 31, challengeType: 'MEDICATION', challengeName: '꾸준한 건강 기록',
  rewardBadge: null, status: 'ACTIVE', joinedAt: '2026-09-09T09:00:00+09:00',
  endAt: '2026-09-16T09:00:00+09:00', actualEndDate: '2026-09-16',
  targetCount: 4, completedCount: 1, progressRate: '25.00', action: 'NONE',
  targetDayCount: 4, completedDayCount: completedCount, dayProgressRate: String(completedCount * 25),
  targets: [{ id: 801, sourceId: 101, name: targetName }],
  occurrences: [10, 11, 12, 13].map((day, index) => ({ id: 901 + index, targetId: 801, scheduledDate: `2026-09-${day}`, slot: 'MORNING', scheduledAt: `2026-09-${day}T08:00:00+09:00`, isCompleted: index < completedCount })),
  ...overrides,
  });
};

type Reply = { status?: number; json: unknown };
const errorReply = { status: 503, json: { code: 'TEMPORARY', message: '잠시 뒤 다시 시도해주세요.' } };
const gate = () => {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { promise, release };
};

async function setup(page: Page, read: () => Reply | Promise<Reply>, cancel?: () => Reply | Promise<Reply>) {
  await page.clock.setFixedTime('2026-09-10T03:00:00Z');
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'auto-refresh-test-token');
    sessionStorage.setItem('poke.account-principal', 'refresh@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  const counts = { reads: 0, cancels: 0, unexpected: [] as string[] };
  // Guard actual API paths only: SPA navigation must reach Vite, every API is a fixture.
  await page.route(url => url.pathname.startsWith('/api/'), async (route: Route) => {
    const pathname = new URL(route.request().url()).pathname;
    let reply: Reply;
    if (pathname === path && route.request().method() === 'GET') {
      counts.reads += 1;
      reply = await read();
    } else if (pathname === `${path}/cancel` && route.request().method() === 'POST' && cancel) {
      counts.cancels += 1;
      reply = await cancel();
    } else {
      counts.unexpected.push(`${route.request().method()} ${pathname}`);
      reply = { status: 404, json: { code: 'UNEXPECTED_FIXTURE_API' } };
    }
    await route.fulfill({ status: reply.status ?? 200, json: reply.json });
  });
  return counts;
}

async function invalidate(page: Page) {
  await page.evaluate(() => window.dispatchEvent(new Event('rxvita:custom-challenge-progress-invalidated')));
}

for (const challengeType of ['MEDICATION', 'SUPPLEMENT']) {
  test(`${challengeType}: progress refreshes on invalidation, focus and visible return without a refresh button`, async ({ page }) => {
    let count = 1;
    const counts = await setup(page, () => ({ json: participation({ challengeType, completedCount: count, progressRate: String(count * 25) }) }));
    await page.goto('/challenges/custom-participations/701');
    await expect(page.getByText('1 / 4일', { exact: true })).toBeVisible();
    count = 2;
    await invalidate(page);
    await expect(page.getByText('2 / 4일', { exact: true })).toBeVisible();
    count = 3;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.getByText('3 / 4일', { exact: true })).toBeVisible();
    count = 4;
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(page.getByText('4 / 4일', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '최신 진행률 불러오기' })).toHaveCount(0);
    const targets = page.getByRole('region', { name: '참여 대상', exact: true });
    await expect(targets.getByText(targetName)).toBeVisible();
    await expect(targets.locator('summary')).toHaveCount(0);
    expect(await targets.getByText(targetName).evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    expect(counts.unexpected).toEqual([]);
  });
}

test('initial failure retries and a failed background refresh retains progress and targets', async ({ page }) => {
  let fail = true;
  let blocked: ReturnType<typeof gate> | null = null;
  const counts = await setup(page, async () => {
    if (blocked) await blocked.promise;
    return fail ? errorReply : { json: participation() };
  });
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByRole('heading', { name: '참여 기록을 불러오지 못했어요' })).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(page.getByText('1 / 4일', { exact: true })).toBeVisible();
  blocked = gate();
  fail = true;
  const reads = counts.reads;
  await invalidate(page);
  await expect.poll(() => counts.reads).toBe(reads + 1);
  await expect(page.getByText('1 / 4일', { exact: true })).toBeVisible();
  await expect(page.getByRole('status', { name: '맞춤 챌린지 참여 기록 불러오는 중' })).toHaveCount(0);
  blocked.release();
  await expect(page.getByRole('alert')).toContainText('잠시 뒤');
  await expect(page.getByText('1 / 4일', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '참여 대상', exact: true }).getByText(targetName)).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(counts.unexpected).toEqual([]);
});

test('invalidation during a pending refresh coalesces into a fresh read without showing stale data', async ({ page }) => {
  let blocked: ReturnType<typeof gate> | null = null;
  let count = 1;
  const counts = await setup(page, async () => {
    const snapshot = count;
    if (blocked) await blocked.promise;
    return { json: participation({ completedCount: snapshot, progressRate: String(snapshot * 25) }) };
  });
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByText('1 / 4일', { exact: true })).toBeVisible();
  blocked = gate();
  count = 2;
  const initialReads = counts.reads;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect.poll(() => counts.reads).toBe(initialReads + 1);
  count = 3;
  await invalidate(page);
  await invalidate(page);
  expect(counts.reads).toBe(initialReads + 1);
  blocked.release();
  await expect(page.getByText('3 / 4일', { exact: true })).toBeVisible();
  expect(counts.reads).toBe(initialReads + 2);
});

test('a pending refresh cannot close the cancel dialog or overwrite its completed cancellation', async ({ page }) => {
  let blocked: ReturnType<typeof gate> | null = null;
  const cancelGate = gate();
  const counts = await setup(page, async () => {
    if (blocked) await blocked.promise;
    return { json: participation() };
  }, async () => {
    await cancelGate.promise;
    return { json: participation({ status: 'CANCELLED' }) };
  });
  await page.goto('/challenges/custom-participations/701');
  await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
  blocked = gate();
  const reads = counts.reads;
  await invalidate(page);
  await expect.poll(() => counts.reads).toBe(reads + 1);
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Queue another invalidation before cancellation; it must not survive the cancel result.
  await invalidate(page);
  await dialog.getByRole('button', { name: '참여 취소', exact: true }).click();
  await expect(dialog.getByRole('button', { name: '취소 중...' })).toBeDisabled();
  await invalidate(page);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  expect(counts.reads).toBe(reads + 1);
  cancelGate.release();
  await expect(page.getByRole('heading', { name: '최종 결과' })).toBeVisible();
  const staleResponse = page.waitForResponse(response => new URL(response.url()).pathname === path);
  blocked.release();
  await staleResponse;
  // Give the completed GET's finally callback and any wrongly queued GET time to settle.
  await page.waitForTimeout(150);
  await expect(page.getByRole('button', { name: '챌린지 참여 취소', exact: true })).toHaveCount(0);
  await expect(page.getByText('취소', { exact: true })).toBeVisible();
  expect(counts.cancels).toBe(1);
  expect(counts.reads).toBe(reads + 1);
});

test('home keeps every custom and official card with type badges and accessible groups, without repeated headings', async ({ page }) => {
  await setup(page, () => ({ json: participation() }));
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const pathname = new URL(route.request().url()).pathname;
    let json: unknown = [];
    if (pathname === '/api/v1/user/custom-challenge-participations') {
      json = { items: [participation(), participation({ id: 702, challengeName: '영양제 습관', challengeType: 'SUPPLEMENT' }), participation({ id: 703, challengeName: '세 번째 맞춤 습관' })], totalCount: 3 };
    } else if (pathname === '/api/v1/user/challenges') {
      json = { items: [{ id: 501, user_id: 7, challenge_id: 101, challenge_name: '매일 걷기', status: 'ACTIVE', joined_at: '2026-09-01T09:00:00+09:00', started_at: '2026-09-01T00:00:00+09:00', end_at: '2026-09-15T00:00:00+09:00', target_count: 14, completed_count: 3, progress_rate: '21.43', completed_at: null, cancelled_at: null, progress_periods: [] }], total_count: 1 };
    } else if (pathname === '/api/v1/med/user-suppl-nutr') {
      json = { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null };
    }
    await route.fulfill({ json });
  });
  await page.goto('/home');
  const custom = page.getByRole('region', { name: '맞춤 챌린지', exact: true });
  const official = page.getByRole('region', { name: '공식 챌린지', exact: true });
  await expect(custom.getByRole('link')).toHaveCount(3);
  await expect(official.getByRole('link')).toHaveCount(1);
  await expect(custom.getByText('맞춤', { exact: true })).toHaveCount(3);
  await expect(official.getByText('공식', { exact: true })).toHaveCount(1);
  await expect(custom.getByRole('heading')).toHaveCount(0);
  await expect(official.getByRole('heading')).toHaveCount(0);
});
