import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

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
  reward_badge: null,
  can_join: false,
  participation_id: 501,
};

const participation = {
  id: 501,
  user_id: 7,
  challenge_id: 101,
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
  progress_periods: [],
  challenge,
  today: '2026-09-10',
  today_verification: null,
  can_verify: true,
  verified_dates: ['2026-09-08', '2026-09-09'],
};

const recommendation = {
  templateId: 31,
  challengeType: 'MEDICATION',
  challengeName: '처방 일정 지키기',
  rewardBadge: null,
  action: 'NONE',
  targets: [
    { id: 101, name: '서울의원 처방', existingParticipationId: null },
    { id: 102, name: '튼튼병원 처방', existingParticipationId: 701 },
  ],
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-447-layout-token');
    sessionStorage.setItem('poke.account-principal', 'issue-447-layout@example.com');
  });
}

async function capture(page: Page, name: string) {
  const directory = process.env.UI447_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, name), fullPage: true, animations: 'disabled' });
}

async function expectNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

async function verticalGap(upper: Locator, lower: Locator) {
  const [upperBox, lowerBox] = await Promise.all([upper.boundingBox(), lower.boundingBox()]);
  expect(upperBox).not.toBeNull();
  expect(lowerBox).not.toBeNull();
  return lowerBox!.y - (upperBox!.y + upperBox!.height);
}

async function expectNoVisibleShadow(card: Locator) {
  const shadow = await card.evaluate(element => getComputedStyle(element).boxShadow);
  const colors = shadow.match(/rgba?\([^)]+\)/g) ?? [];
  expect(shadow === 'none' || (colors.length > 0 && colors.every(color => color === 'rgba(0, 0, 0, 0)'))).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-09-10T12:00:00+09:00'));
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route =>
    fulfillJson(route, { code: 'FIXTURE_MISSING', message: '447 fixture missing' }, 503));
});

test('공식 상세 404에도 Header와 기존 안내를 유지하고 둘러보기로 돌아간다', async ({ page }) => {
  await page.route('**/api/v1/user/challenge-catalog/404', route =>
    fulfillJson(route, { code: 'NOT_FOUND', message: '챌린지가 없어요.' }, 404));

  await page.goto('/challenges/official/404');

  await expect(page.locator('header')).toHaveCount(1);
  await expect(page.locator('header').getByRole('heading', { name: '챌린지', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '챌린지를 찾을 수 없어요', exact: true })).toBeVisible();
  await capture(page, 'task-2-official-detail-error-404-390.png');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges\/browse$/);
});

test('공식 상세 503에도 Header와 재시도를 유지하고 정상 Header 하나로 복구한다', async ({ page }) => {
  let failed = true;
  await page.route('**/api/v1/user/challenge-catalog/101', route => failed
    ? fulfillJson(route, { code: 'TEMPORARY', message: '잠시 연결이 끊겼어요.' }, 503)
    : fulfillJson(route, challenge));

  await page.goto('/challenges/official/101');

  await expect(page.locator('header')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: '챌린지를 불러오지 못했어요', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('잠시 연결이 끊겼어요.');
  failed = false;
  await page.getByRole('button', { name: '다시 불러오기', exact: true }).click();
  await expect(page.locator('header')).toHaveCount(1);
  await expect(page.locator('header').getByRole('heading', { name: challenge.name, exact: true })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges\/browse$/);
});

test('공식 참여 404에도 Header와 기존 안내를 유지하고 챌린지로 돌아간다', async ({ page }) => {
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/challenges/404', route =>
    fulfillJson(route, { code: 'NOT_FOUND', message: '참여 기록이 없어요.' }, 404));

  await page.goto('/challenges/participations/404');

  await expect(page.locator('header')).toHaveCount(1);
  await expect(page.locator('header').getByRole('heading', { name: '챌린지', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '참여 기록을 찾을 수 없어요', exact: true })).toBeVisible();
  await capture(page, 'task-2-official-participation-error-404-390.png');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges$/);
});

test('공식 참여 503에도 Header와 재시도를 유지하고 정상 Header 하나로 복구한다', async ({ page }) => {
  let failed = true;
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/challenges/501', route => failed
    ? fulfillJson(route, { code: 'TEMPORARY', message: '참여 기록 연결이 끊겼어요.' }, 503)
    : fulfillJson(route, participation));

  await page.goto('/challenges/participations/501');

  await expect(page.locator('header')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: '참여 기록을 불러오지 못했어요', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('참여 기록 연결이 끊겼어요.');
  failed = false;
  await page.getByRole('button', { name: '다시 불러오기', exact: true }).click();
  await expect(page.locator('header')).toHaveCount(1);
  await expect(page.locator('header').getByRole('heading', { name: challenge.name, exact: true })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges$/);
});

test('공식 상세와 참여의 loading에서 정상 상태까지 Header를 하나만 유지한다', async ({ page }) => {
  let releaseDetail!: () => void;
  const detailGate = new Promise<void>(resolve => { releaseDetail = resolve; });
  await page.route('**/api/v1/user/challenge-catalog/101', async route => {
    await detailGate;
    await fulfillJson(route, challenge);
  });

  await page.goto('/challenges/official/101');
  await expect(page.getByLabel('챌린지 상세 불러오는 중')).toBeVisible();
  await expect(page.locator('header')).toHaveCount(1);
  releaseDetail();
  await expect(page.locator('header').getByRole('heading', { name: challenge.name, exact: true })).toBeVisible();
  await expect(page.locator('header')).toHaveCount(1);

  let releaseParticipation!: () => void;
  const participationGate = new Promise<void>(resolve => { releaseParticipation = resolve; });
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/challenges/501', async route => {
    await participationGate;
    await fulfillJson(route, participation);
  });
  await page.goto('/challenges/participations/501');
  await expect(page.getByLabel('참여 기록 불러오는 중')).toBeVisible();
  await expect(page.locator('header')).toHaveCount(1);
  releaseParticipation();
  await expect(page.locator('header').getByRole('heading', { name: challenge.name, exact: true })).toBeVisible();
  await expect(page.locator('header')).toHaveCount(1);
});

for (const width of [320, 390, 1280]) {
  test(`맞춤 추천 카드의 실제 내부 행 간격은 8px이고 정보 표면은 평면이다 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.route('**/api/v1/user/custom-challenge-recommendations', route =>
      fulfillJson(route, { items: [recommendation], totalCount: 1 }));

    await page.goto('/challenges/tailored');

    const heading = page.getByRole('heading', { name: recommendation.challengeName, exact: true });
    const cardLink = heading.locator('xpath=ancestor::a[1]');
    const titleRow = heading.locator('xpath=parent::div');
    const source = cardLink.getByText('복약 기록 연동', { exact: true });
    const availability = cardLink.getByText('참여 가능한 대상 1개', { exact: true });
    await expect(heading).toBeVisible();
    expect(await verticalGap(titleRow, source)).toBeCloseTo(8, 0);
    expect(await verticalGap(source, availability)).toBeCloseTo(8, 0);
    await expectNoVisibleShadow(cardLink.locator('.rx-card'));
    await expectNoOverflow(page);
    await capture(page, `task-2-recommendations-ordinary-${width}.png`);
  });
}

test('긴 맞춤 추천 제목도 320px에서 8px 간격과 가로 안전성을 유지한다', async ({ page }) => {
  const longRecommendation = {
    ...recommendation,
    challengeName: '서울대학교병원 순환기내과에서 처방받은 아침과 저녁의 꾸준한 복약 챌린지',
  };
  await page.setViewportSize({ width: 320, height: 844 });
  await page.route('**/api/v1/user/custom-challenge-recommendations', route =>
    fulfillJson(route, { items: [longRecommendation], totalCount: 1 }));

  await page.goto('/challenges/tailored');

  const heading = page.getByRole('heading', { name: longRecommendation.challengeName, exact: true });
  const cardLink = heading.locator('xpath=ancestor::a[1]');
  expect(await verticalGap(heading.locator('xpath=parent::div'), cardLink.getByText('복약 기록 연동', { exact: true }))).toBeCloseTo(8, 0);
  await expectNoOverflow(page);
  await capture(page, 'task-2-recommendations-long-320.png');
});

test('빈 맞춤 추천 카드의 heading, 설명, 링크 간격은 각각 12px이다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/v1/user/custom-challenge-recommendations', route =>
    fulfillJson(route, { items: [], totalCount: 0 }));

  await page.goto('/challenges/tailored');

  const heading = page.getByRole('heading', { name: '지금 참여할 수 있는 맞춤 챌린지가 없어요.', exact: true });
  const card = heading.locator('xpath=ancestor::*[contains(@class,"rx-card")][1]');
  const description = card.getByText('복약 또는 영양제 기록을 등록한 뒤 다시 확인해주세요.', { exact: true });
  const link = card.getByRole('link', { name: '내 기록 확인하기 ›', exact: true });
  expect(await verticalGap(heading, description)).toBeCloseTo(12, 0);
  expect(await verticalGap(description, link)).toBeCloseTo(12, 0);
  await expectNoVisibleShadow(card);
  await expectNoOverflow(page);
  await capture(page, 'task-2-recommendations-empty-390.png');
});
