import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);
test.use({ viewport: { width: 320, height: 812 } });

const longName = '서울대학교병원 순환기내과에서 처방받은 아침과 저녁의 꾸준한 복약 챌린지';
const firstTarget = '서울대학교병원 순환기내과 첫 번째 장기 처방 전체 이름';
const secondTarget = '튼튼병원 내분비내과 두 번째 장기 처방 전체 이름';
const badge = { id: 9, name: '매일의 복약 일정을 꾸준하게 기록한 루틴 배지', description: '처방 일정 달성 배지', imagePath: '/media/layout-badge.svg' };
const custom = {
  id: 701, templateId: 31, challengeType: 'MEDICATION', challengeName: longName,
  rewardBadge: badge, status: 'ACTIVE', joinedAt: '2026-09-09T09:00:00+09:00',
  endAt: '2026-09-16T09:00:00+09:00', actualEndDate: '2026-09-16',
  targetCount: 3, completedCount: 1, progressRate: '33.33', action: 'NONE',
  targets: [{ id: 801, sourceId: 101, name: firstTarget }, { id: 802, sourceId: 102, name: secondTarget }],
  occurrences: [
    { id: 901, targetId: 801, scheduledDate: '2026-09-10', slot: 'MORNING', scheduledAt: '2026-09-10T08:00:00+09:00', isCompleted: true },
    { id: 902, targetId: 802, scheduledDate: '2026-09-10', slot: 'EVENING', scheduledAt: '2026-09-10T19:00:00+09:00', isCompleted: false },
    { id: 903, targetId: 801, scheduledDate: '2026-09-11', slot: 'MORNING', scheduledAt: '2026-09-11T08:00:00+09:00', isCompleted: false },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.clock.setFixedTime('2026-09-10T03:00:00Z');
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'layout-test-token');
    sessionStorage.setItem('poke.account-principal', 'challenge-layout@example.com');
  });
  await page.route('**/media/layout-badge.svg', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="28" fill="#087d7d"/></svg>' }));
});

async function expectNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test('custom detail keeps full title and essential progress visible with immediately visible targets and selected date records', async ({ page }, testInfo) => {
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: custom }));
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByRole('heading', { name: longName, exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('custom-detail-mobile.png'), fullPage: true });
  const heading = page.getByRole('heading', { name: longName, exact: true });
  expect(await heading.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await heading.evaluate(element => {
    const title = element.getBoundingClientRect();
    const header = element.closest('header')!.getBoundingClientRect();
    return title.top >= header.top && title.bottom <= header.bottom;
  })).toBe(true);
  await expect(page.getByRole('heading', { name: '내 진행률' })).toBeVisible();
  await expect(page.getByRole('region', { name: '챌린지 달력', exact: true })).toBeVisible();
  const targets = page.getByRole('region', { name: '참여 대상', exact: true });
  await expect(targets.getByText(firstTarget, { exact: true })).toBeVisible();
  await expect(targets.getByText(secondTarget, { exact: true })).toBeVisible();
  const records = page.getByRole('region', { name: '날짜별 복용 기록' });
  await expect(records.getByRole('list')).toBeVisible();
  await expect(records.getByRole('listitem')).toHaveCount(2);
  await page.getByRole('button', { name: '2026.09.11, 예정 1회' }).click();
  await expect(page.getByRole('heading', { name: '9월 11일' })).toBeVisible();
  await expect(records.getByRole('list')).toBeVisible();
  await expect(records.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('button', { name: '챌린지 참여 취소', exact: true })).toBeVisible();
  await expectNoOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('custom-detail-expanded-mobile.png'), fullPage: true });
});

test('custom join keeps choices accessible and supplementary guidance collapsible', async ({ page }, testInfo) => {
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: [{
    templateId: 31, challengeType: 'MEDICATION', challengeName: longName, rewardBadge: badge, action: 'NONE',
    targets: [{ id: 101, name: firstTarget, existingParticipationId: null }, { id: 102, name: secondTarget, existingParticipationId: null }, { id: 103, name: '기존 처방', existingParticipationId: 703 }],
  }], totalCount: 1 } }));
  await page.goto('/challenges/tailored/medication?templateId=31');
  await page.getByLabel(`${firstTarget} 선택`).check();
  await page.getByLabel(`${secondTarget} 선택`).check();
  await page.screenshot({ path: testInfo.outputPath('custom-join-mobile.png'), fullPage: true });
  const guidance = page.locator('details').filter({ has: page.locator('summary', { hasText: '배지와 인증 안내' }) });
  await expect(guidance).not.toHaveAttribute('open', '');
  await expect(guidance.getByText(/건강 상태/)).toBeHidden();
  await guidance.locator('summary').click();
  await expect(guidance.getByText(/건강 상태/)).toBeVisible();
  await expect(page.getByRole('link', { name: '이미 참여 중인 처방 보기' })).toHaveAttribute('href', '/challenges/custom-participations/703');
  const selection = page.getByRole('region', { name: '참여 대상', exact: true });
  const summary = selection.getByRole('list', { name: '선택 대상' });
  await expect(summary.getByRole('listitem')).toHaveCount(2);
  await expect(page.getByRole('button', { name: '선택한 처방으로 참여하기' })).toBeEnabled();
  await expectNoOverflow(page);
});

test('official manual eligibility remains visible before opening badge guidance', async ({ page }, testInfo) => {
  await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: {
    id: 101, name: longName, phrase: '건강한 습관을 기록하는 일상', description: '실천한 기록을 확인해요.',
    challenge_type_code: 'OFFICIAL', period_code: 'D14', duration_days: 14,
    check_type_code: 'MANUAL', frequency_code: 'TOTAL_10', recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00', reward_badge: null, can_join: true, participation_id: null,
  } }));
  await page.goto('/challenges/official/101');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('official-join-mobile.png'), fullPage: true });
  const guide = page.getByRole('region', { name: '참여 안내', exact: true });
  await expect(guide).toContainText('현재 앱에서 참여할 수 없어요');
  await expect(guide.getByText(/현재 앱에서 참여할 수 없어요/)).toBeVisible();
  const guidance = page.locator('details').filter({ has: page.locator('summary', { hasText: '배지와 인증 안내' }) });
  await expect(guidance.getByText(/건강 상태/)).toBeHidden();
  await guidance.locator('summary').click();
  await expect(guidance.getByText(/건강 상태/)).toBeVisible();
  await expect(page.getByRole('button', { name: '현재 앱에서는 참여할 수 없어요' })).toBeDisabled();
  await expectNoOverflow(page);
});
