import { expect, test } from 'playwright/test';

test.setTimeout(30_000);

test('일반 경로의 홈 이동은 검토 전용 목업 홈으로 바꾸지 않는다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'challenge-home-link-token');
    sessionStorage.setItem('poke.account-principal', 'challenge-home-link@example.com');
  });
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [], total_count: 0, offset: 0, limit: 100 },
  }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({
    json: { items: [], total_count: 0 },
  }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({
    json: { items: [], total_count: 0 },
  }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
  await page.goto('/challenges');
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test('목업 홈의 개별 처방 기록은 선택 대상만 한 회 집계하고 되돌릴 수 있다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => {
    if (['fetch', 'xhr'].includes(request.resourceType())) requests.push(request.url());
  });
  await page.goto('/dev/challenges');
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page).toHaveURL(/\/dev\/home-challenges$/);
  const medication = page.getByRole('region', { name: '오늘의 복약' });
  const summary = page.getByRole('region', { name: '챌린지' });
  const progress = summary.getByRole('link', { name: /감기약 복약 챌린지/ });
  await expect(progress).toContainText('67%');
  // The second prescription is not a challenge target yet.
  await medication.getByRole('button', { name: /9월 7일 처방.*선택$/ }).click();
  await medication.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(progress).toContainText('67%');
  await medication.getByRole('button', { name: /감기약.*선택$/ }).click();
  await medication.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(progress).toContainText('78%');
  await medication.getByRole('button', { name: /감기약.*복용 완료$/ }).click();
  await medication.getByRole('button', { name: '복약 기록 되돌리기', exact: true }).click();
  await expect(progress).toContainText('67%');
  await progress.click();
  await expect(page.getByText('6 / 9회 인증', { exact: true })).toBeVisible();
  expect(requests).toEqual([]);
});

test('참여하지 않은 처방 기록은 배지를 주지 않고 나중에 참여하면 예시 기록을 반영한다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/home-challenges');
  const medication = page.getByRole('region', { name: '오늘의 복약' });
  await medication.getByRole('button', { name: /9월 7일 처방.*선택$/ }).click();
  await medication.getByRole('button', { name: '먹었어요', exact: true }).click();
  await page.getByRole('region', { name: '챌린지' }).getByRole('link', { name: '전체 보기', exact: true }).click();
  await page.getByRole('region', { name: '작은 실천이 쌓이고 있어요' }).getByRole('link', { name: /전체 보기/ }).click();
  await expect(page.getByRole('link', { name: '복약 루틴 배지, 1회 획득', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await page.getByRole('link', { name: /복약 챌린지 참여 처방 확인/ }).click();
  await page.getByRole('checkbox', { name: /9월 7일 처방/ }).check();
  await page.getByRole('button', { name: '이 대상으로 참여하기' }).click();
  await page.getByRole('button', { name: '지난 기록 펼치기' }).click();
  await expect(page.getByRole('article', { name: '9월 7일 처방 복약 챌린지', exact: true })).toContainText('100%');
});
