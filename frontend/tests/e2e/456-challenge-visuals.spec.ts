import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

const today = '2026-09-10';
const officialName = '매일 30분 걷기';
const customName = '아침 처방 복약 챌린지';

const catalogItem = {
  id: 456,
  name: officialName,
  phrase: '오늘도 가볍게 걸어요',
  description: '걷는 습관을 꾸준히 기록해요.',
  challenge_type_code: 'OFFICIAL',
  period_code: 'D7',
  duration_days: 7,
  check_type_code: 'SELF',
  frequency_code: 'DAILY',
  recruit_start_at: '2026-09-01T00:00:00+09:00',
  recruit_end_at: '2026-09-30T23:59:59+09:00',
  reward_badge: null,
  can_join: true,
  participation_id: null,
};

const officialParticipation = {
  id: 501,
  user_id: 1,
  challenge_id: catalogItem.id,
  challenge_name: officialName,
  status: 'ACTIVE',
  joined_at: `${today}T00:00:00+09:00`,
  started_at: `${today}T00:00:00+09:00`,
  end_at: '2026-09-17T00:00:00+09:00',
  target_count: 7,
  completed_count: 2,
  progress_rate: 28.57,
  completed_at: null,
  cancelled_at: null,
  progress_periods: [],
  challenge: { ...catalogItem, can_join: false, participation_id: 501 },
  today,
  today_verification: null,
  can_verify: true,
  verified_dates: ['2026-09-09'],
};

function customParticipation(id: number, name = customName) {
  return {
    id,
    templateId: 41,
    challengeType: 'MEDICATION',
    challengeName: name,
    rewardBadge: null,
    status: 'ACTIVE',
    joinedAt: `${today}T00:00:00+09:00`,
    endAt: '2026-09-17T00:00:00+09:00',
    actualEndDate: '2026-09-16',
    targetCount: 7,
    completedCount: 2,
    progressRate: 28.57,
    targetDayCount: 7,
    completedDayCount: 2,
    dayProgressRate: 28.57,
    action: 'NONE',
    targets: [{ id: id + 1000, sourceId: id + 2000, name: `처방 ${id}` }],
    occurrences: [{ id: id + 3000, targetId: id + 1000, scheduledDate: today, scheduledAt: `${today}T08:00:00+09:00`, slot: 'MORNING', isCompleted: false }],
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function screenshot(page: Page, name: string) {
  const directory = process.env.UI456_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, name), fullPage: true, animations: 'disabled' });
}

async function expectTypeSurface(card: Locator, badgeText: '공식' | '맞춤') {
  const badge = card.getByText(badgeText, { exact: true });
  await expect(badge).toBeVisible();
  const [cardColor, badgeColor] = await Promise.all([
    card.evaluate(element => getComputedStyle(element).backgroundColor),
    badge.evaluate(element => getComputedStyle(element).backgroundColor),
  ]);
  expect(cardColor).toBe(badgeColor);
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date(`${today}T12:00:00+09:00`));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-456-visual-token');
    sessionStorage.setItem('poke.account-principal', 'issue-456-visual@example.com');
  });
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route =>
    fulfillJson(route, { code: 'FIXTURE_MISSING', message: '456 visual fixture missing' }, 503));
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => fulfillJson(route, { items: [], totalCount: 0 }));
});

test('홈 챌린지는 양쪽 44px 조작 영역 안에 작은 반투명 화살표를 두고 유형별 카드 색을 쓴다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const customItems = [customParticipation(701), customParticipation(702, '저녁 처방 복약 챌린지'), customParticipation(703, '주말 처방 복약 챌린지')];
  await page.route('**/api/v1/user/challenges', route => fulfillJson(route, { items: [officialParticipation], total_count: 1 }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, { items: customItems, totalCount: customItems.length }));

  await page.goto('/home');
  const summary = page.getByRole('region', { name: '챌린지', exact: true });
  const viewport = summary.getByLabel('오늘 할 챌린지', { exact: true });
  const previous = summary.getByRole('button', { name: '이전 챌린지', exact: true });
  const next = summary.getByRole('button', { name: '다음 챌린지', exact: true });
  await expect(previous).toBeVisible();
  await expect(next).toBeVisible();
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();

  const [viewportBox, previousBox, nextBox] = await Promise.all([viewport.boundingBox(), previous.boundingBox(), next.boundingBox()]);
  expect(viewportBox).not.toBeNull();
  expect(previousBox).not.toBeNull();
  expect(nextBox).not.toBeNull();
  expect(previousBox!.width).toBeGreaterThanOrEqual(44);
  expect(previousBox!.height).toBeGreaterThanOrEqual(44);
  expect(nextBox!.width).toBeGreaterThanOrEqual(44);
  expect(nextBox!.height).toBeGreaterThanOrEqual(44);
  expect(Math.abs((previousBox!.x + previousBox!.width / 2) - viewportBox!.x)).toBeLessThanOrEqual(10);
  expect(Math.abs((nextBox!.x + nextBox!.width / 2) - (viewportBox!.x + viewportBox!.width))).toBeLessThanOrEqual(10);

  for (const button of [previous, next]) {
    const circle = button.locator('[data-challenge-arrow-circle]');
    const circleBox = await circle.boundingBox();
    expect(circleBox).not.toBeNull();
    expect(circleBox!.width).toBeLessThan(44);
    expect(circleBox!.height).toBeLessThan(44);
    expect(await circle.evaluate(element => getComputedStyle(element).backgroundColor)).toMatch(/rgba\([^)]*, 0\.[1-9]/);
  }

  await expectTypeSurface(summary.getByRole('article', { name: officialName, exact: true }), '공식');
  await expectTypeSurface(summary.getByRole('article', { name: customName, exact: true }), '맞춤');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await screenshot(page, 'task-c-home-carousel-390.png');

  const before = await viewport.evaluate(element => element.scrollLeft);
  await next.click();
  await expect.poll(() => viewport.evaluate(element => element.scrollLeft)).toBeGreaterThan(before);
  await viewport.evaluate(element => element.scrollTo({ left: 0, behavior: 'instant' }));
  await expect(previous).toBeDisabled();
  await page.setViewportSize({ width: 320, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await screenshot(page, 'task-c-home-carousel-320.png');
});

test('320px 둘러보기는 기존 유형 배지를 유지하고 모집기간 전체를 한 줄로 표시한다', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const recommendation = {
    templateId: 41,
    challengeType: 'MEDICATION',
    challengeName: customName,
    rewardBadge: null,
    action: 'NONE',
    targets: [{ id: 201, name: '아침 처방약', existingParticipationId: null }],
  };
  await page.route('**/api/v1/user/challenge-catalog?*', route => fulfillJson(route, { items: [catalogItem], total_count: 1, offset: 0, limit: 100 }));
  await page.route('**/api/v1/user/challenges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => fulfillJson(route, { items: [recommendation], totalCount: 1 }));

  await page.goto('/challenges/browse');
  await page.getByRole('button', { name: '공식 챌린지 펼치기', exact: true }).click();
  await page.getByRole('button', { name: '맞춤 챌린지 펼치기', exact: true }).click();
  const officialCard = page.getByRole('button', { name: `${officialName} 자세히 보기`, exact: true });
  const customCard = page.getByRole('button', { name: `${customName} 대상 선택`, exact: true });
  await expect(officialCard.getByText('공식', { exact: true })).toBeVisible();
  await expect(customCard.getByText('맞춤', { exact: true })).toBeVisible();

  const recruitment = officialCard.getByText('모집기간 : 2026.09.01 ~ 2026.09.30', { exact: true });
  const [cardBox, recruitmentBox] = await Promise.all([officialCard.boundingBox(), recruitment.boundingBox()]);
  expect(cardBox).not.toBeNull();
  expect(recruitmentBox).not.toBeNull();
  const lines = await recruitment.evaluate(element => {
    const style = getComputedStyle(element);
    return element.getBoundingClientRect().height / Number.parseFloat(style.lineHeight);
  });
  expect(lines).toBeLessThanOrEqual(1.05);
  expect(recruitmentBox!.x).toBeGreaterThanOrEqual(cardBox!.x);
  expect(recruitmentBox!.x + recruitmentBox!.width).toBeLessThanOrEqual(cardBox!.x + cardBox!.width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await screenshot(page, 'task-c-challenge-browse-320.png');
});

test('공식·맞춤 상세의 윗면은 유형 색을 쓰고 상세 유형 배지는 반복하지 않는다', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.route('**/api/v1/user/challenge-catalog/456', route => fulfillJson(route, catalogItem));
  await page.goto('/challenges/official/456');
  await expect(page.getByText('공식', { exact: true })).toHaveCount(0);
  const officialHighlight = page.locator('section[aria-labelledby="official-highlight-title"]');
  await expect(officialHighlight).toHaveCSS('background-color', 'rgb(221, 244, 241)');
  const recruitment = page.getByText('2026.09.01 ~ 2026.09.30', { exact: true });
  const participationGuide = page.locator('section[aria-labelledby="participation-guide-title"]');
  const [guideBox, recruitmentBox] = await Promise.all([participationGuide.boundingBox(), recruitment.boundingBox()]);
  expect(guideBox).not.toBeNull();
  expect(recruitmentBox).not.toBeNull();
  expect(recruitmentBox!.x).toBeGreaterThanOrEqual(guideBox!.x);
  expect(recruitmentBox!.x + recruitmentBox!.width).toBeLessThanOrEqual(guideBox!.x + guideBox!.width);
  const recruitmentLines = await recruitment.evaluate(element => {
    const style = getComputedStyle(element);
    return element.getBoundingClientRect().height / Number.parseFloat(style.lineHeight);
  });
  expect(recruitmentLines).toBeLessThanOrEqual(1.05);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await screenshot(page, 'task-c-official-detail-320.png');

  const recommendation = {
    templateId: 41,
    challengeType: 'MEDICATION',
    challengeName: customName,
    rewardBadge: null,
    action: 'NONE',
    targets: [{ id: 201, name: '아침 처방약', existingParticipationId: null }],
  };
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => fulfillJson(route, { items: [recommendation], totalCount: 1 }));
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('/challenges/tailored/medication?templateId=41');
  await expect(page.getByText('맞춤', { exact: true })).toHaveCount(0);
  const customHighlight = page.locator('section[aria-labelledby="custom-highlight-title"]');
  await expect(customHighlight).toHaveCSS('background-color', 'rgb(253, 241, 231)');

  const custom = customParticipation(701);
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => fulfillJson(route, custom));
  await page.goto('/challenges/custom-participations/701');
  const progress = page.locator('section[aria-labelledby="custom-progress-title"]');
  await expect(progress).toHaveCSS('background-color', 'rgb(253, 241, 231)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await screenshot(page, 'task-c-challenge-details-390.png');
});
