import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(10000);
  page.setDefaultNavigationTimeout(60000);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'fixture-only-token');
    sessionStorage.setItem('poke.account-principal', '428-accordion-fixture@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [{
    id: 502, user_id: 1, challenge_id: 102, challenge_name: catalog[0].name,
    status: 'ACTIVE', joined_at: '2026-09-12T00:00:00+09:00', started_at: '2026-09-12T00:00:00+09:00',
    end_at: '2026-09-18T23:59:59+09:00', target_count: 7, completed_count: 0, progress_rate: 0,
    completed_at: null, cancelled_at: null, progress_periods: [], challenge: catalog[0],
    today: '2026-09-12', today_verification: null, can_verify: true, verified_dates: [],
  }], total_count: 1 } }));
});

const catalog = [
  { id: 102, name: '참여 중 걷기', can_join: false, participation_id: 502 },
  { id: 101, name: '매일 가볍게 걸으며 건강한 생활 습관을 만드는 공식 챌린지', can_join: true, participation_id: null },
].map(item => ({ ...item, phrase: '매일 걸어요', description: null, challenge_type_code: 'OFFICIAL', period_code: 'D7', duration_days: 7, check_type_code: 'SELF', frequency_code: 'DAILY', recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00', reward_badge: null }));
const recommendations = [
  { templateId: 41, challengeType: 'SUPPLEMENT', challengeName: '참여 중 영양제', targets: [{ id: 201, name: '비타민', existingParticipationId: 701 }] },
  { templateId: 42, challengeType: 'MEDICATION', challengeName: '처방 일정 지키기', targets: [{ id: 202, name: '복약 처방', existingParticipationId: null }] },
].map(item => ({ ...item, rewardBadge: null, action: 'NONE' }));

async function stubLists(page: Page) {
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: { items: catalog, total_count: catalog.length, offset: 0, limit: 100 } }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: recommendations, totalCount: recommendations.length } }));
}

for (const width of [375, 390, 1280]) {
  test(`browse accordion groups stay independent and preserve card states at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await stubLists(page);
    await page.goto('/challenges/browse');
    const official = page.getByRole('region', { name: '공식 챌린지', exact: true });
    const custom = page.getByRole('region', { name: '맞춤 챌린지', exact: true });
    const officialToggle = official.getByRole('button', { name: '공식 챌린지 펼치기', exact: true });
    const customToggle = custom.getByRole('button', { name: '맞춤 챌린지 펼치기', exact: true });
    await expect(officialToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(customToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(officialToggle).toContainText('2개');
    await expect(customToggle).toContainText('2개');
    await expect(page.getByRole('combobox', { name: '챌린지 종류 필터' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '참여 중 걷기 참여중', exact: true })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`browse-collapsed-${width}.png`), animations: 'disabled' });
    await officialToggle.focus();
    await page.keyboard.press('Enter');
    await expect(official.getByRole('button', { name: '공식 챌린지 접기', exact: true })).toHaveAttribute('aria-expanded', 'true');
    await expect(customToggle).toHaveAttribute('aria-expanded', 'false');
    await customToggle.click();
    await expect(custom.getByRole('button', { name: '맞춤 챌린지 접기', exact: true })).toHaveAttribute('aria-expanded', 'true');
    await expect(official.getByRole('button', { name: `${catalog[1].name} 자세히 보기`, exact: true })).toBeEnabled();
    await expect(official.getByRole('button', { name: '참여 중 걷기 참여중', exact: true })).toBeDisabled();
    await expect(custom.getByRole('button', { name: '참여 중 영양제 참여중', exact: true })).toBeDisabled();
    await expect(custom.getByRole('button', { name: '처방 일정 지키기 대상 선택', exact: true })).toBeEnabled();
    await expect(official).not.toContainText('처방 일정 지키기');
    await expect(custom).not.toContainText('참여 중 걷기');
    await expect(official.getByRole('button').nth(1)).toHaveAccessibleName(`${catalog[1].name} 자세히 보기`);
    await expect(custom.getByRole('button').nth(1)).toHaveAccessibleName('처방 일정 지키기 대상 선택');
    await expect(official).toContainText('2026년 9월 1일 ~ 2026년 9월 30일');
    expect(await page.locator('main').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`browse-expanded-${width}.png`), animations: 'disabled' });
    await official.getByRole('button', { name: '공식 챌린지 접기', exact: true }).click();
    await expect(custom.getByRole('button', { name: '처방 일정 지키기 대상 선택', exact: true })).toBeVisible();
    await custom.getByRole('button', { name: '처방 일정 지키기 대상 선택', exact: true }).click();
    await expect(page).toHaveURL(/\/challenges\/tailored\/medication\?templateId=42$/);
  });
}

test('a loading or failed official group does not hide custom entries while retrying', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let failing = true;
  await page.route('**/api/v1/user/challenge-catalog?*', async route => {
    if (failing) {
      await gate;
      return route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '공식 목록을 잠시 불러올 수 없어요.' } });
    }
    return route.fulfill({ json: { items: [], total_count: 0, offset: 0, limit: 100 } });
  });
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: { items: recommendations, totalCount: 2 } }));
  await page.goto('/challenges/browse');
  const official = page.getByRole('region', { name: '공식 챌린지', exact: true });
  const custom = page.getByRole('region', { name: '맞춤 챌린지', exact: true });
  await official.getByRole('button', { name: '공식 챌린지 펼치기' }).click();
  await custom.getByRole('button', { name: '맞춤 챌린지 펼치기' }).click();
  await expect(official.getByRole('status')).toBeVisible();
  await expect(custom.getByRole('button', { name: '처방 일정 지키기 대상 선택' })).toBeVisible();
  release();
  await expect(official.getByRole('alert')).toContainText('공식 목록을 잠시');
  await expect(custom.getByRole('alert')).toHaveCount(0);
  failing = false;
  await official.getByRole('button', { name: '다시 불러오기', exact: true }).click();
  await expect(official).toContainText('지금 참여할 수 있는 공식 챌린지가 없어요.');
  await expect(custom.getByRole('button', { name: '처방 일정 지키기 대상 선택' })).toBeVisible();
});

test('an empty official group and failed custom group show their own states', async ({ page }) => {
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: { items: [], total_count: 0, offset: 0, limit: 100 } }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '맞춤 목록을 잠시 불러올 수 없어요.' } }));
  await page.goto('/challenges/browse');
  const official = page.getByRole('region', { name: '공식 챌린지', exact: true });
  const custom = page.getByRole('region', { name: '맞춤 챌린지', exact: true });
  await official.getByRole('button', { name: '공식 챌린지 펼치기' }).click();
  await custom.getByRole('button', { name: '맞춤 챌린지 펼치기' }).click();
  await expect(official).toContainText('지금 참여할 수 있는 공식 챌린지가 없어요.');
  await expect(official.getByRole('alert')).toHaveCount(0);
  await expect(custom.getByRole('alert')).toContainText('맞춤 목록을 잠시');
});
