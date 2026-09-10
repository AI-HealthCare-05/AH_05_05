import { expect, test, type Page } from 'playwright/test';

const today = '2026-09-10';
const badge = { id: 1, name: '복약 배지', description: null, imagePath: '/images/challenges/badge-medication.png' };
function custom(id: number, date = today, completed = false) {
  return { id, templateId: 1, challengeType: 'MEDICATION', challengeName: `처방 ${id}`, rewardBadge: badge,
    status: 'ACTIVE', joinedAt: `${today}T00:00:00+09:00`, endAt: '2026-09-20T00:00:00+09:00',
    actualEndDate: '2026-09-19', targetCount: 10, completedCount: 0, progressRate: 0,
    targetDayCount: 10, completedDayCount: 0, dayProgressRate: 0, action: 'NONE',
    targets: [{ id, sourceId: id, name: `처방 ${id}` }],
    occurrences: [{ id, targetId: id, scheduledDate: date, scheduledAt: `${date}T08:00:00+09:00`, slot: 'MORNING', isCompleted: completed }],
  };
}
async function setup(page: Page, items: ReturnType<typeof custom>[]) {
  await page.clock.setFixedTime(new Date(`${today}T12:00:00+09:00`));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'test-token');
    sessionStorage.setItem('poke.account-principal', 'today-review@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: {} }));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/medications/doses*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/supplement-doses*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/user-suppl-nutr*', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null } }));
  await page.route('**/api/v1/display/med/nutr/rank*', route => route.fulfill({ status: 204 }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items, totalCount: items.length } }));
}

test('home keeps completed goals scheduled today with colored badge links', async ({ page }) => {
  await setup(page, [custom(1), custom(2, '2026-09-11'), custom(3, today, true)]);
  await page.goto('/home');
  const section = page.locator('section[aria-labelledby="home-challenge-title"]');
  await expect(section.getByRole('link', { name: /처방 1/ })).toBeVisible();
  await expect(section.getByRole('link', { name: /처방 2/ })).toHaveCount(0);
  await expect(section.getByRole('link', { name: /처방 3/ })).toBeVisible();
  await expect(section.getByRole('article', { name: '처방 1', exact: true })).toContainText('미달성');
  await expect(section.getByRole('article', { name: '처방 3', exact: true })).toContainText('달성');
  await expect(section.getByRole('button', { name: /했어요/ })).toHaveCount(0);
  await expect(section.getByRole('img', { name: '복약 배지' }).first()).toBeVisible();
  await expect.poll(() => section.getByRole('img', { name: '복약 배지' }).first().evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await expect(section.getByRole('link', { name: /처방 1/ })).toHaveAttribute('href', '/challenges/custom-participations/1');
});

test('fixed width cards scroll inside their panel and arrows reflect remaining direction', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, [custom(1), custom(2), custom(3), custom(4)]);
  await page.goto('/home');
  const section = page.locator('section[aria-labelledby="home-challenge-title"]');
  const next = section.getByRole('button', { name: '다음 챌린지' });
  const previous = section.getByRole('button', { name: '이전 챌린지' });
  await expect(next).toBeVisible();
  await expect(previous).toBeHidden();
  const first = section.getByRole('article', { name: '처방 1', exact: true });
  expect((await first.boundingBox())!.width).toBe(144);
  await next.click();
  await expect(previous).toBeVisible();
  for (let i = 0; i < 4 && await next.isVisible(); i++) await next.click();
  await expect(next).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/369-home-today-review.png', fullPage: true });
});

test('an empty today list does not show future challenge cards', async ({ page }) => {
  await setup(page, [custom(2, '2026-09-11')]);
  await page.goto('/home');
  const section = page.locator('section[aria-labelledby="home-challenge-title"]');
  await expect(section.getByText('오늘 남은 챌린지가 없어요')).toBeVisible();
  await expect(section.getByRole('link', { name: /처방 2/ })).toHaveCount(0);
});

test('same-account revalidation keeps the visible card until the new records arrive', async ({ page }) => {
  await setup(page, [custom(1)]);
  await page.goto('/home');
  const section = page.locator('section[aria-labelledby="home-challenge-title"]');
  const card = section.getByRole('link', { name: /처방 1/ });
  await expect(card).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route('**/api/v1/user/custom-challenge-participations', async route => {
    started = true;
    await gate;
    await route.fulfill({ json: { items: [custom(1, today, true)], totalCount: 1 } });
  });
  await page.evaluate(() => window.dispatchEvent(new Event('rxvita:custom-challenge-progress-invalidated')));
  await expect.poll(() => started).toBe(true);
  await expect(card).toBeVisible();
  await expect(section.getByRole('status')).toHaveCount(0);
  release();
  await expect(card).toBeVisible();
  await expect(section.getByText('달성', { exact: true })).toBeVisible();
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [custom(1)], totalCount: 1 } }));
  await page.evaluate(() => window.dispatchEvent(new Event('rxvita:custom-challenge-progress-invalidated')));
  await expect(section.getByText('미달성', { exact: true })).toBeVisible();
});

function official() {
  return { id: 91, user_id: 1, challenge_id: 1, challenge_name: '걷기 챌린지', status: 'ACTIVE',
    started_at: `${today}T00:00:00+09:00`, joined_at: `${today}T00:00:00+09:00`, end_at: '2026-09-17T00:00:00+09:00',
    target_count: 7, completed_count: 0, progress_rate: 0, completed_at: null, cancelled_at: null, progress_periods: [],
    challenge: { id: 1, name: '걷기 챌린지', check_type_code: 'SELF', reward_badge: null },
    today, today_verification: null, can_verify: true, verified_dates: [] as string[],
  };
}

test('official home check-in writes once, stays on home and preserves server-confirmed completion during stale refresh', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, [custom(1)]);
  const item = official();
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [item], total_count: 1 } }));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const writes: Record<string, string>[] = [];
  await page.route('**/api/v1/user/challenges/91/verifications', async route => {
    writes.push(route.request().postDataJSON());
    await gate;
    await route.fulfill({ json: { id: 1, participation_id: 91, verification_date: today, status: 'APPROVED' } });
  });
  await page.goto('/home');
  const card = page.getByRole('article', { name: '걷기 챌린지', exact: true });
  const action = card.getByRole('button', { name: /했어요/ });
  await expect(action).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('home-before-checkin.png'), animations: 'disabled' });
  await action.click();
  await expect(action).toBeDisabled();
  await action.dispatchEvent('click');
  expect(writes).toHaveLength(1);
  expect(writes[0].verification_date).toBe(today);
  expect(writes[0].idempotency_key).toBeTruthy();
  await expect(card.getByText('달성', { exact: true })).toHaveCount(0);
  release();
  await expect(card.getByText('달성', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/home$/);
  await expect(card.getByRole('button')).toHaveCount(0);
  item.verified_dates.push(today);
  item.completed_count = 1;
  item.progress_rate = 14.29;
  item.can_verify = false;
  await page.reload();
  await expect(card.getByText('달성', { exact: true })).toBeVisible();
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '14.29');
  await page.screenshot({ path: testInfo.outputPath('home-after-checkin.png'), animations: 'disabled' });
  await card.getByRole('link').click();
  await expect(page).toHaveURL(/\/challenges\/participations\/91$/);
});

test('server-completed one-day challenges remain on home today without another check-in button', async ({ page }) => {
  await setup(page, [{ ...custom(1, today, true), status: 'COMPLETED' }]);
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [{
    ...official(), status: 'COMPLETED', can_verify: false, verified_dates: [today], end_at: `${today}T10:00:00+09:00`,
    completed_count: 1, target_count: 1, progress_rate: 100,
  }], total_count: 1 } }));
  await page.goto('/home');
  const section = page.getByRole('region', { name: '챌린지', exact: true });
  await expect(section.getByText('달성', { exact: true })).toHaveCount(2);
  await expect(section.getByRole('button', { name: /했어요/ })).toHaveCount(0);
});

test('failed official check-in stays unachieved and retry reuses its idempotency key', async ({ page }) => {
  await setup(page, []);
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [official()], total_count: 1 } }));
  const keys: string[] = [];
  await page.route('**/api/v1/user/challenges/91/verifications', route => {
    keys.push(route.request().postDataJSON().idempotency_key);
    return route.fulfill(keys.length === 1 ? { status: 503, json: { message: '저장 실패' } }
      : { json: { id: 1, participation_id: 91, verification_date: today, status: 'APPROVED' } });
  });
  await page.goto('/home');
  const card = page.getByRole('article', { name: '걷기 챌린지', exact: true });
  await card.getByRole('button', { name: /했어요/ }).click();
  await expect(card.getByRole('alert')).toBeVisible();
  await expect(card.getByText('달성', { exact: true })).toHaveCount(0);
  await card.getByRole('button', { name: /했어요/ }).click();
  await expect(card.getByText('달성', { exact: true })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[1]).toBe(keys[0]);
});

for (const pendingBeforeMidnight of [false, true]) {
  test(`midnight without visibility or timer does not use yesterday's ${pendingBeforeMidnight ? 'pending response' : 'check-in date'}`, async ({ page }) => {
    await setup(page, []);
    let tomorrow = false;
    let reads = 0;
    const writes: string[] = [];
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/user/challenges', route => {
      reads++;
      return route.fulfill({ json: { items: [{ ...official(), today: tomorrow ? '2026-09-11' : today }], total_count: 1 } });
    });
    await page.route('**/api/v1/user/challenges/91/verifications', async route => {
      writes.push(route.request().postDataJSON().verification_date);
      if (pendingBeforeMidnight) await gate;
      await route.fulfill({ json: { id: 1, verification_date: today, status: 'APPROVED' } });
    });
    await page.goto('/home');
    const card = page.getByRole('article', { name: '걷기 챌린지', exact: true });
    const action = card.getByRole('button', { name: /했어요/ });
    await expect(action).toBeVisible();
    if (pendingBeforeMidnight) {
      await action.click();
      await expect.poll(() => writes.length).toBe(1);
    }
    const previousReads = reads;
    tomorrow = true;
    await page.clock.setFixedTime(new Date('2026-09-11T00:00:01+09:00'));
    if (pendingBeforeMidnight) release(); else await action.click();
    await expect.poll(() => reads).toBeGreaterThan(previousReads);
    await expect(action).toBeEnabled();
    await expect(card.getByText('달성', { exact: true })).toHaveCount(0);
    expect(writes).toEqual(pendingBeforeMidnight ? [today] : []);
  });
}

test('crossing Korea midnight reloads official eligibility without reloading the page', async ({ page }) => {
  await setup(page, []);
  let nextDay = false;
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { total_count: 1, items: [{
    id: 91, user_id: 1, challenge_id: 1, challenge_name: '물 마시기 챌린지', status: 'ACTIVE',
    joined_at: '2026-09-10T00:00:00+09:00', started_at: '2026-09-10T00:00:00+09:00', end_at: '2026-09-17T00:00:00+09:00',
    target_count: 7, completed_count: 1, progress_rate: 14.29, completed_at: null, cancelled_at: null,
    progress_periods: [{ id: 1, period_start: today, period_end: '2026-09-16', target_count: 7, completed_count: 1, progress_rate: 14.29, is_completed: false, completed_at: null }],
    challenge: { id: 1, name: '물 마시기 챌린지', phrase: '물 마시기', description: null, challenge_type_code: 'OFFICIAL', period_code: 'D7', duration_days: 7, check_type_code: 'SELF', frequency_code: 'DAILY', recruit_start_at: `${today}T00:00:00+09:00`, recruit_end_at: '2026-09-30T23:59:59+09:00', reward_badge: null, can_join: false, participation_id: 91 },
    today: nextDay ? '2026-09-11' : today, today_verification: null, can_verify: nextDay, verified_dates: [today],
  }] } }));
  await page.goto('/home');
  const section = page.locator('section[aria-labelledby="home-challenge-title"]');
  await expect(section.getByText('달성', { exact: true })).toBeVisible();
  nextDay = true;
  await page.clock.setFixedTime(new Date('2026-09-11T00:01:00+09:00'));
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(section.getByRole('link', { name: /물 마시기 챌린지/ })).toBeVisible();
  await expect(section.getByRole('button', { name: /했어요/ })).toBeVisible();
  await expect(section.getByText('달성', { exact: true })).toHaveCount(0);
});

test('native swipe over a challenge moves the carousel without opening its link', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await setup(page, [custom(1), custom(2), custom(3), custom(4)]);
  await page.goto('/home');
  const scroll = page.getByLabel('오늘 할 챌린지', { exact: true });
  await expect(scroll).toBeVisible();
  await scroll.scrollIntoViewIfNeeded();
  const box = (await scroll.boundingBox())!;
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true });
  const x = box.x + 125, y = box.y + 100;
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
  for (let step = 1; step <= 6; step++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x - step * 16, y }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(() => scroll.evaluate(element => element.scrollLeft)).toBeGreaterThan(20);
  await expect(page).toHaveURL(/\/home$/);
});

test('first populated carousel preserves the height reserved by its meaningful loading state', async ({ page }) => {
  await setup(page, [custom(1)]);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/user/custom-challenge-participations', async route => {
    await gate;
    await route.fulfill({ json: { items: [custom(1)], totalCount: 1 } });
  });
  await page.goto('/home');
  const section = page.locator('section[aria-labelledby="home-challenge-title"]');
  await expect(section.getByRole('status')).toContainText('오늘 챌린지를');
  const before = (await section.boundingBox())!.height;
  release();
  await expect(section.getByRole('link', { name: /처방 1/ })).toBeVisible();
  expect(Math.abs((await section.boundingBox())!.height - before)).toBeLessThanOrEqual(2);
});
