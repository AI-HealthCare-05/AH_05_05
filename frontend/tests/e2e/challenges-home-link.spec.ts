import { expect, test } from 'playwright/test';

test.setTimeout(30_000);

test('일반 경로의 홈 이동은 검토 전용 목업 홈으로 바꾸지 않는다', async ({ page }) => {
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
  const progress = summary.getByRole('link', { name: /복약 루틴 챌린지/ });
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

test('두 care episode를 선택하면 분모 23회로 합산하고 홈 기록이 상세까지 유지된다', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/challenges/tailored/medication');
  await page.getByRole('checkbox', { name: /9월 7일 처방/ }).check();
  await expect(page.getByText(/총 23회/)).toBeVisible();
  await page.getByRole('button', { name: '이 대상으로 참여하기' }).click();
  await expect(page.getByText('6 / 23회 인증', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '홈', exact: true }).click();
  const medication = page.getByRole('region', { name: '오늘의 복약' });
  const progress = page.getByRole('region', { name: '챌린지' }).getByRole('link', { name: /복약 루틴 챌린지/ });
  await expect(progress).toContainText('26%');
  await medication.getByRole('button', { name: /감기약.*선택$/ }).click();
  await medication.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(progress).toContainText('30%');
  await medication.getByRole('button', { name: /9월 7일 처방.*선택$/ }).click();
  await medication.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(progress).toContainText('35%');
  await expect(medication.getByRole('button', { name: '복약 기록 되돌리기', exact: true })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath('home-episodes.png') });
  await progress.click();
  await expect(page.getByText('8 / 23회 인증', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '처방별 진행률' })).toContainText('7 / 9회');
  await expect(page.getByRole('region', { name: '처방별 진행률' })).toContainText('1 / 14회');
  await page.screenshot({ path: testInfo.outputPath('episode-progress.png') });
});
