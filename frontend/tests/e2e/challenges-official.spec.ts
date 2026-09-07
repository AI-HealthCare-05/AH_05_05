import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(20_000);

test('개발용과 프로덕션 챌린지 경로 모두 목업 기준일과 초기화를 알린다', async ({ page }) => {
  const notice = '목업 미리보기 · 기준일 2026.09.13 · 새로고침 시 초기화';
  await page.goto('/dev/challenges');
  await expect(page.getByText(notice, { exact: true })).toBeVisible();

  await page.goto('/challenges');
  await expect(page.getByText(notice, { exact: true })).toBeVisible();
});

test('둘러보기에서 미참여 공식 챌린지를 선택하고 참여를 시작한다', async ({ page }) => {
  await page.goto('/dev/challenges/browse');

  await page.getByRole('button', { name: /물 마시기.*자세히 보기/ }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/official\/official-water-7d$/);
  await expect(page.getByRole('heading', { name: '물 마시기', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '참여하기' }).click();

  await expect(page).toHaveURL(/\/dev\/challenges\/participations\/part-official-water$/);
  await expect(page.getByText('내 수행 기간')).toBeVisible();
});

test('마이에서 오늘 인증하며 같은 날에는 한 번만 반영한다', async ({ page }) => {
  await page.goto('/dev/challenges');

  const activeChallenge = page.getByRole('article', { name: '매일 30분 걷기' });
  await activeChallenge.getByRole('button', { name: '했어요' }).click();

  await expect(activeChallenge.getByText('4 / 7일 인증')).toBeVisible();
  const completedButton = activeChallenge.getByRole('button', { name: '오늘 인증 완료' });
  await expect(completedButton).toBeDisabled();
  await completedButton.evaluate((element: HTMLButtonElement) => element.click());
  await expect(activeChallenge.getByText('4 / 7일 인증')).toBeVisible();

  await activeChallenge.getByRole('link', { name: '매일 30분 걷기 자세히 보기' }).click();
  await expect(page.getByText('오늘의 실천을 기록했어요')).toBeVisible();
  await expect(page.getByText('4 / 7일 인증', { exact: true })).toBeVisible();
});

test('완주한 공식 챌린지는 결과와 획득 배지를 보여준다', async ({ page }) => {
  await page.goto('/dev/challenges/participations/part-official-achieved');

  await expect(page.getByRole('heading', { name: '저녁 산책 7일' })).toBeVisible();
  await expect(page.getByText('7 / 7일 인증')).toBeVisible();
  await expect(page.getByText('챌린지를 완주했어요')).toBeVisible();
  await expect(page.getByRole('link', { name: /7일 걷기 배지/ })).toBeVisible();
});

test('마이와 공식 챌린지 보상은 생성된 배지 이미지를 사용한다', async ({ page }) => {
  await page.goto('/dev/challenges');
  await expect(page.getByRole('img', { name: '7일 걷기 배지' })).toBeVisible();

  await page.goto('/dev/challenges/official/official-walk-7d');
  await expect(page.getByRole('img', { name: '7일 걷기 배지' })).toBeVisible();
});

test('마지막 인증은 새 배지를 획득 상태로 바꾼다', async ({ page }) => {
  await page.goto('/dev/challenges/participations/part-official-first-finish');

  await page.getByRole('button', { name: '했어요' }).click();

  await expect(page.getByText('챌린지를 완주했어요')).toBeVisible();
  await page.getByRole('link', { name: /첫 챌린지 배지/ }).click();
  await expect(page.getByText(/2026-09-13 획득/)).toBeVisible();
});

test('모집이 끝난 공식 챌린지는 참여할 수 없다', async ({ page }) => {
  await page.goto('/dev/challenges/official/official-ended');

  await expect(page.getByText('모집이 끝났어요')).toBeVisible();
  await expect(page.getByRole('button', { name: '참여하기' })).toBeDisabled();
});

test('챌린지 탐색과 참여는 네트워크 API 요청 없이 동작한다', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    if (['xhr', 'fetch'].includes(request.resourceType())) apiRequests.push(request.url());
  });

  await page.goto('/dev/challenges/browse');
  await page.getByRole('button', { name: /스트레칭.*자세히 보기/ }).click();
  await page.getByRole('button', { name: '참여하기' }).click();
  await expect(page.getByText('내 수행 기간')).toBeVisible();

  expect(apiRequests).toEqual([]);
});
