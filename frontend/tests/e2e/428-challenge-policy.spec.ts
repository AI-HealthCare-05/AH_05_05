import { readFileSync } from 'node:fs';
import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
const walkingBadge = readFileSync(new URL('../../public/images/challenges/badge-walk.png', import.meta.url));
const supplementBadge = readFileSync(new URL('../../public/images/challenges/badge-supplement.png', import.meta.url));
test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(10_000);
  page.setDefaultNavigationTimeout(60_000);
  await page.clock.setFixedTime('2026-09-10T03:00:00Z');
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'fixture-token');
    sessionStorage.setItem('poke.account-principal', 'challenge-fixture@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route('**/images/challenges/badge-walk.png', route => route.fulfill({ contentType: 'image/png', body: walkingBadge }));
  await page.route('**/images/challenges/badge-supplement.png', route => route.fulfill({ contentType: 'image/png', body: supplementBadge }));
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: { items: [], totalCount: 0 } }));
});

const challenge = {
  id: 101, name: '매일 걷기', phrase: '매일 걸어요', description: null,
  challenge_type_code: 'OFFICIAL', period_code: 'D7', duration_days: 7,
  check_type_code: 'SELF', frequency_code: 'DAILY',
  recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00',
  reward_badge: null, can_join: false, participation_id: 501,
};
const official = {
  id: 501, user_id: 1, challenge_id: 101, challenge_name: '매일 걷기', status: 'ACTIVE',
  joined_at: '2026-09-09T00:00:00+09:00', started_at: '2026-09-09T00:00:00+09:00', end_at: '2026-09-16T00:00:00+09:00',
  target_count: 7, completed_count: 2, progress_rate: '28.57', completed_at: null, cancelled_at: null,
  progress_periods: [{ id: 801, period_start: '2026-09-09', period_end: '2026-09-15', target_count: 7, completed_count: 2, progress_rate: '28.57', is_completed: false, completed_at: null }],
  challenge, today: '2026-09-10', today_verification: null, can_verify: false, verified_dates: ['2026-09-09', '2026-09-10'],
};
const custom = {
  id: 701, templateId: 41, challengeType: 'SUPPLEMENT', challengeName: '영양제 챌린지', rewardBadge: null,
  status: 'ACTIVE', joinedAt: '2026-09-09T00:00:00+09:00', endAt: '2026-09-16T00:00:00+09:00', actualEndDate: '2026-09-15',
  targetCount: 14, completedCount: 3, progressRate: '21.43', targetDayCount: 7, completedDayCount: 1, dayProgressRate: '14.29', action: 'NONE',
  targets: [{ id: 901, sourceId: 201, name: '비타민' }],
  occurrences: [
    { id: 801, targetId: 901, scheduledDate: '2026-09-10', slot: 'MORNING', scheduledAt: '2026-09-10T08:00:00+09:00', isCompleted: true },
    { id: 802, targetId: 901, scheduledDate: '2026-09-10', slot: 'EVENING', scheduledAt: '2026-09-10T19:00:00+09:00', isCompleted: false },
  ],
};

async function lists(page: Page, officials: unknown[] = [official], customs: unknown[] = [custom]) {
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: officials, total_count: officials.length } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: customs, totalCount: customs.length } }));
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: official }));
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: custom }));
}

test('occupied supplement is disabled while a distinct registration remains selectable', async ({ page }) => {
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: [{
    templateId: 41, challengeType: 'SUPPLEMENT', challengeName: '영양제 챌린지', rewardBadge: null, action: 'NONE',
    targets: [{ id: 201, name: '참여 중 비타민', existingParticipationId: 701 }, { id: 202, name: '새 영양제', existingParticipationId: null }],
  }], totalCount: 1 } }));
  await page.goto('/challenges/tailored');
  await expect(page.getByRole('link', { name: '영양제 챌린지 대상 선택' })).toContainText('참여 가능한 대상 1개');
  await page.goto('/challenges/tailored/supplement?templateId=41');
  await expect(page.getByRole('checkbox', { name: '참여 중 비타민 선택' })).toBeDisabled();
  await expect(page.getByRole('link', { name: /이미 참여 중인 영양제 보기/ })).toHaveAttribute('href', '/challenges/custom-participations/701');
  await page.getByRole('checkbox', { name: '새 영양제 선택' }).check();
  await expect(page.getByRole('button', { name: '선택한 영양제로 참여하기' })).toBeEnabled();
});

for (const width of [375, 390, 1280]) {
  test(`home and detail share day progress and keep today's completed card at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await lists(page);
    await page.goto('/home');
    const summary = page.getByRole('region', { name: '챌린지', exact: true });
    const walking = summary.getByRole('article', { name: '매일 걷기', exact: true });
    const supplement = summary.getByRole('article', { name: '영양제 챌린지', exact: true });
    await expect(walking).toContainText('2 / 7일');
    await expect(walking.getByText('완료', { exact: true })).toBeVisible();
    await expect(supplement.getByText('미완료', { exact: true })).toBeVisible();
    await expect(supplement.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '14.29');
    const officialColor = await walking.getByText('공식', { exact: true }).evaluate(el => getComputedStyle(el).backgroundColor);
    expect(await supplement.getByText('맞춤', { exact: true }).evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(officialColor);
    const arrow = summary.getByRole('button', { name: '다음 챌린지' });
    if (await arrow.count()) {
      const cardBox = await walking.boundingBox();
      const arrowBox = await arrow.boundingBox();
      expect(arrowBox!.y).toBeGreaterThanOrEqual(cardBox!.y + cardBox!.height);
    }
    await expect.poll(() => summary.getByRole('img').evaluateAll(images => images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
    await summary.screenshot({ path: testInfo.outputPath(`home-${width}.png`), animations: 'disabled' });
    await page.goto('/challenges/custom-participations/701');
    const progress = page.getByRole('region', { name: '내 진행률', exact: true });
    await expect(progress).toContainText('1 / 7일');
    await expect(progress.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '14.29');
    await page.screenshot({ path: testInfo.outputPath(`detail-${width}.png`), fullPage: true, animations: 'disabled' });
  });
}

test('home distinguishes no participation from an active challenge without today schedule', async ({ page }) => {
  await lists(page, [], []);
  await page.goto('/home');
  const summary = page.getByRole('region', { name: '챌린지', exact: true });
  await expect(summary).toContainText('챌린지를 등록하고 생활습관 개선에 도전하세요.');
  await lists(page, [{ ...official, verified_dates: [], can_verify: false }], []);
  await page.reload();
  await expect(summary).toContainText('오늘 예정된 챌린지가 없어요.');
});

test('an unfinished official card shows its state alongside the check-in action', async ({ page }) => {
  await lists(page, [{ ...official, can_verify: true, verified_dates: [] }], []);
  await page.goto('/home');
  const card = page.getByRole('region', { name: '챌린지', exact: true }).getByRole('article', { name: '매일 걷기', exact: true });
  await expect(card.getByText('미완료', { exact: true })).toBeVisible();
  await expect(card.getByRole('button', { name: '매일 걷기 했어요' })).toBeEnabled();
});

test('entire participation card opens details while check-in stays separate', async ({ page }) => {
  await lists(page);
  await page.goto('/challenges', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: '진행 중인 챌린지 펼치기' }).click();
  const card = page.getByRole('article', { name: '영양제 챌린지', exact: true });
  const customProgress = await card.getByText('1 / 7일', { exact: true }).boundingBox();
  await page.mouse.click(customProgress!.x + 5, customProgress!.y + 5);
  await expect(page).toHaveURL(/\/custom-participations\/701$/);
  await page.goto('/challenges', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: '진행 중인 챌린지 펼치기' }).click();
  const walking = page.getByRole('article', { name: '매일 걷기', exact: true });
  await expect(walking.locator('a button, button a')).toHaveCount(0);
  await expect(walking.getByText('공식 배지', { exact: true })).toHaveCount(0);
  const officialProgress = await walking.getByRole('progressbar').boundingBox();
  await page.mouse.click(officialProgress!.x + 5, officialProgress!.y + 4);
  await expect(page).toHaveURL(/\/participations\/501$/);
});

test('browse labels each type and keeps full recruitment dates', async ({ page }) => {
  await lists(page, [], []);
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: { items: [{ ...challenge, can_join: true, participation_id: null }], total_count: 1, offset: 0, limit: 100 } }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: [{ templateId: 41, challengeType: 'SUPPLEMENT', challengeName: '영양제 챌린지', targets: [{ id: 201, name: '비타민', existingParticipationId: null }], rewardBadge: null, action: 'NONE' }], totalCount: 1 } }));
  await page.goto('/challenges/browse');
  await page.getByRole('button', { name: '공식 챌린지 펼치기', exact: true }).click();
  await page.getByRole('button', { name: '맞춤 챌린지 펼치기', exact: true }).click();
  const officialEntry = page.getByRole('button', { name: '매일 걷기 자세히 보기' });
  await expect(officialEntry.getByText('공식', { exact: true })).toBeVisible();
  await expect(officialEntry).toContainText('2026년 9월 1일 ~ 2026년 9월 30일');
  await expect(page.getByRole('button', { name: '영양제 챌린지 대상 선택' }).getByText('맞춤', { exact: true })).toBeVisible();
});

test('historical participation omits redundant progress button and retains eligible rejoin', async ({ page }) => {
  await lists(page);
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: {
    ...official, status: 'CANCELLED', challenge: { ...challenge, participation_id: 502 },
  } }));
  await page.goto('/challenges/participations/501', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: '내 인증 기록', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '진행 보기', exact: true })).toHaveCount(0);
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: {
    ...official, status: 'CANCELLED', challenge: { ...challenge, can_join: true },
  } }));
  await page.reload();
  await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toBeVisible();
});

for (const status of ['COMPLETED', 'EXPIRED', 'CANCELLED'] as const) {
  for (const width of [390, 1280]) {
    test(`ended custom ${status} detail uses header navigation without a redundant footer at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      const ended = { ...custom, status, ...(status === 'COMPLETED' ? {
        completedCount: 14, progressRate: '100.00', completedDayCount: 7, dayProgressRate: '100.00',
        occurrences: custom.occurrences.map(occurrence => ({ ...occurrence, isCompleted: true })),
      } : {}) };
      await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: ended }));
      await page.route('**/api/v1/user/custom-challenge-participations/701/claim-reward', route => route.fulfill({ json: { participation: ended, award: null, newlyAwarded: false } }));
      await page.goto('/challenges/custom-participations/701');
      await expect(page.getByRole('region', { name: '최종 결과', exact: true })).toBeVisible();
      await expect(page.getByRole('region', { name: '참여 대상', exact: true })).toContainText('비타민');
      await expect(page.getByRole('button', { name: /내 챌린지로 돌아가기|챌린지 참여 취소/ })).toHaveCount(0);
      const back = page.getByRole('banner').getByRole('button', { name: '뒤로 가기', exact: true });
      await expect(back).toBeVisible();
      await expect(page.getByRole('alert')).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath(`custom-${status.toLowerCase()}-top-${width}.png`), animations: 'disabled' });
      await page.getByText('진행률은 홈과 영양제 기록을 기준으로 자동 계산돼요.', { exact: false }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: testInfo.outputPath(`custom-${status.toLowerCase()}-bottom-${width}.png`), animations: 'disabled' });
      await back.click();
      await expect(page).toHaveURL(/\/challenges$/);
    });
  }
}

test('active custom detail retains cancel action and dialog dismissal without cancelling', async ({ page }) => {
  let cancelPosts = 0;
  await lists(page);
  await page.route('**/api/v1/user/custom-challenge-participations/701/cancel', route => {
    cancelPosts += 1;
    return route.fulfill({ json: { ...custom, status: 'CANCELLED' } });
  });
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByRole('region', { name: '내 진행률', exact: true })).toBeVisible();
  await expect(page.getByRole('banner').getByRole('button', { name: '뒤로 가기', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: '참여 취소', exact: true })).toBeEnabled();
  await dialog.getByRole('button', { name: '돌아가기', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: '챌린지 참여 취소', exact: true })).toBeEnabled();
  expect(cancelPosts).toBe(0);
});

test('missing custom participation keeps its error fallback navigation', async ({ page }) => {
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ status: 404, json: { code: 'NOT_FOUND', message: '참여 없음' } }));
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByRole('heading', { name: '참여 기록을 찾을 수 없어요', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '챌린지로 돌아가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges$/);
});
