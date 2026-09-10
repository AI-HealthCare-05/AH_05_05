import { expect, test, type Page } from 'playwright/test';

test.setTimeout(120_000);

const badge = {
  id: 31,
  name: '튼튼 걷기 배지',
  description: '꾸준한 걷기를 기록했어요.',
  image_path: '/images/challenges/badge-walk.png',
};

const challenge = {
  id: 101,
  name: '매일 30분 걷기',
  phrase: '걷기로 채우는 나의 2주',
  description: '하루 한 번 걷고 직접 기록해요.',
  challenge_type_code: 'OFFICIAL',
  period_code: 'D14',
  duration_days: 14,
  check_type_code: 'SELF',
  frequency_code: 'DAILY',
  recruit_start_at: '2026-09-01T00:00:00+09:00',
  recruit_end_at: '2026-09-30T23:59:59+09:00',
  reward_badge: badge,
  can_join: false,
  participation_id: 501,
};

const participation = {
  id: 501,
  user_id: 7,
  challenge_id: challenge.id,
  challenge_name: challenge.name,
  status: 'ACTIVE',
  joined_at: '2026-09-08T10:00:00+09:00',
  started_at: '2026-09-08T00:00:00+09:00',
  end_at: '2026-09-22T00:00:00+09:00',
  target_count: 14,
  completed_count: 3,
  progress_rate: '21.43',
  completed_at: null,
  cancelled_at: null,
  progress_periods: [{
    id: 801,
    period_start: '2026-09-08',
    period_end: '2026-09-21',
    target_count: 14,
    completed_count: 3,
    progress_rate: '21.43',
    is_completed: false,
    completed_at: null,
  }],
  challenge,
  today: '2026-09-10',
  today_verification: null,
  can_verify: true,
  verified_dates: ['2026-09-08', '2026-09-09'],
};

const awardedBadge = {
  id: 901,
  user_id: 7,
  badge_id: badge.id,
  challenge_id: challenge.id,
  user_challenge_id: participation.id,
  status: 'AWARDED',
  badge_name: badge.name,
  badge_image_path: badge.image_path,
  awarded_at: '2026-09-10T10:00:00+09:00',
  revoked_at: null,
  revoke_reason: null,
};

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'challenge-navigation-test');
    sessionStorage.setItem('poke.account-principal', 'navigation@example.com');
  });
  // Keep unrelated Home/My reads isolated from a real backend. Specific challenge routes below
  // take precedence over this fallback and mirror their complete response contracts.
  await page.route('**/api/v1/**', route => route.fulfill({
    status: 404,
    json: { code: 'NOT_FOUND', message: '테스트 fixture에 없음' },
  }));
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [challenge], total_count: 1, offset: 0, limit: 100 },
  }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({
    json: { items: [participation], total_count: 1 },
  }));
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({
    json: { items: [awardedBadge], total_count: 1 },
  }));
});

function recordWrites(page: Page) {
  const writes: string[] = [];
  page.on('request', request => {
    if (request.url().includes('/api/') && request.method() !== 'GET') {
      writes.push(`${request.method()} ${request.url()}`);
    }
  });
  return writes;
}

async function openParticipationFromChallengeMy(page: Page) {
  await expect(page).toHaveURL(/\/challenges$/);
  await page.getByRole('link', { name: `${challenge.name} 자세히 보기`, exact: true }).click();
  await expect(page).toHaveURL(/\/challenges\/participations\/501$/);
  await expect(page.getByRole('heading', { name: challenge.name })).toBeVisible();
}

test('Home에서 연 참여 상세를 두 번 뒤로 가면 Home 원래 위치로 복귀한다', async ({ page }, testInfo) => {
  const writes = recordWrites(page);
  await page.goto('/home');
  await page.getByRole('region', { name: '챌린지' }).getByRole('link', { name: '전체 보기', exact: true }).click();
  await openParticipationFromChallengeMy(page);
  await page.screenshot({ path: testInfo.outputPath('home-participation-before-back.png'), fullPage: true });

  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();

  await expect(page).toHaveURL(/\/home$/);
  await page.screenshot({ path: testInfo.outputPath('home-origin-restored.png'), fullPage: true });
  expect(writes).toEqual([]);
});

test('My에서 연 참여 상세를 두 번 뒤로 가면 My 원래 위치로 복귀한다', async ({ page }, testInfo) => {
  const writes = recordWrites(page);
  await page.goto('/my');
  await page.getByRole('button', { name: '챌린지 기록', exact: true }).click();
  await openParticipationFromChallengeMy(page);
  await page.screenshot({ path: testInfo.outputPath('my-participation-before-back.png'), fullPage: true });

  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();

  await expect(page).toHaveURL(/\/my$/);
  await page.screenshot({ path: testInfo.outputPath('my-origin-restored.png'), fullPage: true });
  expect(writes).toEqual([]);
});

test('참여 상세 딥링크의 뒤로가기는 챌린지 fallback을 거쳐 Home으로 빠져나간다', async ({ page }, testInfo) => {
  const writes = recordWrites(page);
  await page.goto('/challenges/participations/501');

  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();

  await expect(page).toHaveURL(/\/home$/);
  await page.screenshot({ path: testInfo.outputPath('participation-deeplink-fallback.png'), fullPage: true });
  expect(writes).toEqual([]);
});

test('챌린지의 배지 전체 보기는 공통 헤더로 내 배지에서 돌아갈 수 있다', async ({ page }, testInfo) => {
  const writes = recordWrites(page);
  await page.goto('/challenges');
  await page.getByRole('region', { name: '작은 실천이 쌓이고 있어요' }).getByRole('link', { name: /전체 보기/ }).click();
  await expect(page).toHaveURL(/\/challenges\/badges$/);
  await page.screenshot({ path: testInfo.outputPath('badges-before-back.png'), fullPage: true });

  const header = page.getByRole('banner');
  const back = header.getByRole('button', { name: '뒤로 가기', exact: true });
  await expect(header.getByRole('heading', { name: '내 배지', exact: true })).toBeVisible();
  await expect(back.locator('svg')).toHaveClass(/lucide-chevron-left/);
  const bounds = await back.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.width).toBeGreaterThanOrEqual(44);
  expect(bounds!.height).toBeGreaterThanOrEqual(44);
  await back.click();

  await expect(page).toHaveURL(/\/challenges$/);
  await page.screenshot({ path: testInfo.outputPath('badges-returned-to-challenges.png'), fullPage: true });
  expect(writes).toEqual([]);
});

test('내 배지 딥링크의 공통 헤더는 챌린지로 fallback한다', async ({ page }, testInfo) => {
  const writes = recordWrites(page);
  await page.goto('/challenges/badges');
  await page.screenshot({ path: testInfo.outputPath('badges-deeplink-before-back.png'), fullPage: true });

  const back = page.getByRole('banner').getByRole('button', { name: '뒤로 가기', exact: true });
  await expect(back).toBeVisible();
  await back.click();

  await expect(page).toHaveURL(/\/challenges$/);
  await page.screenshot({ path: testInfo.outputPath('badges-deeplink-fallback.png'), fullPage: true });
  expect(writes).toEqual([]);
});
