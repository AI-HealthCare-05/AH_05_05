import { expect, test } from 'playwright/test';
import { readFileSync } from 'node:fs';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(90000);
test.use({ reducedMotion: 'reduce' });
const customAwards = [
  { id: 4, participationId: 47, badgeId: 18, badgeName: '복약 배지', badgeImagePath: '/media/badge-a.png', awardedAt: '2026-09-14T12:00:00+09:00' },
  { id: 5, participationId: 48, badgeId: 18, badgeName: '복약 배지', badgeImagePath: '/media/badge-a.png', awardedAt: '2026-09-14T13:00:00+09:00' },
  { id: 6, participationId: 49, badgeId: 19, badgeName: '영양제 배지', badgeImagePath: '/media/badge-b.png', awardedAt: '2026-09-14T14:00:00+09:00' },
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'badge-summary-test');
    sessionStorage.setItem('poke.account-principal', 'badge-summary@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: { items: [], total_count: 0, offset: 0, limit: 100 } }));
  for (const endpoint of ['challenges', 'badges']) {
    await page.route(`**/api/v1/user/${endpoint}`, route => route.fulfill({ json: { items: [], total_count: 0 } }));
  }
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [], totalCount: 0 } }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: { items: customAwards, totalCount: 3 } }));
});

test('custom awards count in My summary after navigation and reload, ordered newest first', async ({ page }) => {
  await page.goto('/challenges');
  const summary = page.getByRole('region', { name: '작은 실천이 쌓이고 있어요' });
  await expect(summary).toContainText('모은 배지 2종 · 3회 획득');
  await expect(summary.getByRole('img')).toHaveCount(3);
  await expect(summary.getByRole('img').first()).toHaveAttribute('alt', '영양제 배지');
  await page.reload();
  await expect(summary).toContainText('모은 배지 2종 · 3회 획득');
  await summary.getByRole('link', { name: /전체 보기/ }).click();
  await expect(page.getByText('모은 배지 2종 · 총 3회 획득', { exact: true })).toBeVisible();
});

test('official and custom shared badge IDs count once per kind and revoked awards do not count', async ({ page }) => {
  const awarded = { id: 4, user_id: 15, badge_id: 18, challenge_id: 10, user_challenge_id: 7,
    status: 'AWARDED', badge_name: '복약 배지', badge_image_path: '/media/badge-a.png',
    awarded_at: '2026-09-14T10:00:00+09:00', revoked_at: null, revoke_reason: null };
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [awarded,
    { ...awarded, id: 7, badge_id: 99, status: 'REVOKED', revoked_at: '2026-09-14T11:00:00+09:00', revoke_reason: '회수' }], total_count: 2 } }));
  await page.goto('/challenges');
  await expect(page.getByText('모은 배지 2종 · 4회 획득', { exact: true })).toBeVisible();
  await page.goto('/challenges/badges');
  await expect(page.getByText('모은 배지 2종 · 총 4회 획득', { exact: true })).toBeVisible();
});

test('custom badge read failure offers retry instead of displaying a false zero', async ({ page }) => {
  let fail = true;
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill(fail
    ? { status: 503, json: { message: '맞춤 배지 조회 실패' } }
    : { json: { items: customAwards, totalCount: 3 } }));
  await page.goto('/challenges');
  const summary = page.getByRole('region', { name: '작은 실천이 쌓이고 있어요' });
  await expect(summary.getByRole('button', { name: '배지 다시 불러오기' })).toBeVisible();
  await expect(summary.getByText(/모은 배지 \d+종/)).toHaveCount(0);
  fail = false;
  await summary.getByRole('button', { name: '배지 다시 불러오기' }).click();
  await expect(summary).toContainText('모은 배지 2종 · 3회 획득');
});

test('custom badge card opens all three awards and each links to its own participation', async ({ page }, testInfo) => {
  const awards = [...customAwards, { ...customAwards[0], id: 7, participationId: 51, awardedAt: '2026-09-15T01:00:00+09:00' }];
  const image = readFileSync(new URL('../../../app/static/media/badges/water-badge.png', import.meta.url));
  await page.route('**/media/badge-a.png', route => route.fulfill({ contentType: 'image/png', body: image }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: { items: awards, totalCount: 4 } }));
  const participations = [47, 48, 51].map((id, index) => ({
    id, templateId: 1, challengeType: 'MEDICATION', challengeName: '복약 챌린지', rewardBadge: null,
    status: 'COMPLETED', joinedAt: '2026-09-14T00:00:00+09:00', endAt: '2026-09-15T00:00:00+09:00',
    actualEndDate: '2026-09-14', targetCount: 1, completedCount: 1, progressRate: '100', action: 'NONE',
    targets: [{ id, sourceId: id, name: ['서울의원 처방', '튼튼병원 처방', '감기약 처방'][index] }],
    occurrences: [],
  }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: participations, totalCount: 3 } }));
  for (const participation of participations) {
    await page.route(`**/api/v1/user/custom-challenge-participations/${participation.id}`, route => route.fulfill({ json: participation }));
    await page.route(`**/api/v1/user/custom-challenge-participations/${participation.id}/claim-reward`, route => route.fulfill({
      json: { participation, award: awards.find(item => item.participationId === participation.id), newlyAwarded: false },
    }));
  }
  await page.goto('/challenges/badges');
  await page.getByRole('link', { name: '복약 배지, 3회 획득', exact: true }).click();
  await expect(page).toHaveURL('/challenges/custom-badges/18');
  const history = page.getByRole('list', { name: '배지 획득 이력' });
  await expect(page.getByText('총 3회 획득', { exact: true })).toBeVisible();
  await expect(history.getByRole('link')).toHaveCount(3);
  await expect(history.getByRole('link').nth(0)).toContainText('감기약 처방');
  await expect(history.getByRole('link').nth(1)).toContainText('튼튼병원 처방');
  await expect(history.getByRole('link').nth(2)).toContainText('서울의원 처방');
  for (const [index, id] of [51, 48, 47].entries()) {
    await expect(history.getByRole('link').nth(index)).toHaveAttribute('href', `/challenges/custom-participations/${id}`);
    await history.getByRole('link').nth(index).click();
    await expect(page).toHaveURL(`/challenges/custom-participations/${id}`);
    await expect(page.getByText('최종 결과', { exact: true })).toBeVisible();
    await expect(page.getByText(participations.find(item => item.id === id)!.targets[0].name, { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
    await expect(history.getByRole('link')).toHaveCount(3);
  }
  await page.reload();
  await expect(history.getByRole('link')).toHaveCount(3);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await history.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.getByRole('img', { name: '복약 배지', exact: true }).evaluate((image: HTMLImageElement) => image.decode());
    await page.screenshot({ path: testInfo.outputPath(`custom-badge-history-${width}.png`), fullPage: true, animations: 'disabled' });
  }
  await expect(page.getByText('내 배지로 돌아가기', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/badges');
});

test('custom badge detail retries load errors and handles unknown badge IDs', async ({ page }) => {
  let fail = true;
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill(fail
    ? { status: 503, json: { message: '배지 이력 조회 실패' } }
    : { json: { items: customAwards, totalCount: 3 } }));
  await page.goto('/challenges/custom-badges/18');
  await expect(page.getByRole('alert')).toContainText('배지 이력 조회 실패');
  fail = false;
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(page.getByRole('list', { name: '배지 획득 이력' }).getByRole('link')).toHaveCount(2);
  await page.goto('/challenges/custom-badges/999');
  await expect(page.getByText('배지를 찾을 수 없어요', { exact: true })).toBeVisible();
  await expect(page.getByText('내 배지로 돌아가기', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/badges');
});

test('unearned intake badges are visible without participation and never count as earned', async ({ page }, testInfo) => {
  const availableBadges = [
    { id: 18, name: '복약 배지', description: '복약 배지입니다.', imagePath: '/media/badge-a.png' },
    { id: 19, name: '영양제 배지', description: '영양제 배지입니다.', imagePath: '/media/badge-b.png' },
  ];
  let items: typeof customAwards = [];
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: { items, totalCount: items.length, availableBadges } }));
  const art = readFileSync(new URL('../../../app/static/media/badges/water-badge.png', import.meta.url));
  await page.route(/\/media\/badge-[ab]\.png$/, route => route.fulfill({ contentType: 'image/png', body: art }));
  const writes: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET' && request.url().includes('/api/')) writes.push(request.url()); });
  await page.goto('/challenges');
  await expect(page.getByText('모은 배지 0종 · 0회 획득', { exact: true })).toBeVisible();
  await page.goto('/challenges/badges');
  await expect(page.getByText('모은 배지 0종 · 총 0회 획득', { exact: true })).toBeVisible();
  for (const badge of availableBadges) {
    const card = page.getByRole('link', { name: `${badge.name}, 미획득`, exact: true });
    await expect(card).toBeVisible();
    await expect(card.getByRole('img')).toHaveClass(/grayscale/);
    await card.click();
    await expect(page.getByRole('heading', { name: badge.name, exact: true })).toBeVisible();
    await expect(page.getByText('아직 획득하지 않았어요.', { exact: true })).toBeVisible();
    await expect(page.getByRole('list', { name: '배지 획득 이력' })).toHaveCount(0);
    await expect(page.getByText(badge.description, { exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByText('아직 획득하지 않았어요.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('main img').evaluateAll(images => Promise.all(images.map(image => image.decode())));
  await page.screenshot({ path: testInfo.outputPath('unearned-intake-badges.png'), fullPage: true, animations: 'disabled' });
  items = customAwards.slice(0, 2);
  await page.reload();
  await expect(page.getByText('모은 배지 1종 · 총 2회 획득', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '복약 배지, 2회 획득', exact: true })).toHaveCount(1);
  await expect(page.getByRole('link', { name: '복약 배지, 2회 획득', exact: true }).getByRole('img')).not.toHaveClass(/grayscale/);
  await expect(page.getByRole('link', { name: '영양제 배지, 미획득', exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});
