import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(20_000);

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('배지함은 획득 상태를 구분하고 상세에서 기록 기준을 설명한다', async ({ page }) => {
  await page.goto('/dev/challenges/badges');

  await expect(page.getByRole('heading', { name: '내 배지' })).toBeVisible();
  const grid = page.getByRole('list', { name: '챌린지 배지' });
  await expect(grid.getByRole('listitem')).toHaveCount(6);
  await expect(grid.locator('img')).toHaveCount(6);
  expect(
    await grid.locator('img').evaluateAll((images) =>
      new Set(images.map((image) => image.getAttribute('src'))).size,
    ),
  ).toBe(4);
  await expect(grid.getByRole('link', { name: /7일 걷기 배지.*획득/ })).toBeVisible();
  await expect(grid.getByRole('link', { name: /물 마시기 7일 배지.*미획득/ })).toBeVisible();

  await grid.getByRole('link', { name: /7일 걷기 배지/ }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/badges\/badge-walk$/);
  await expect(page.getByRole('heading', { name: '배지 상세' })).toBeVisible();
  await expect(page.getByRole('img', { name: '7일 걷기 배지' })).toBeVisible();
  await expect(page.getByText('실제 운동량·건강 상태의 인증은 아니에요.')).toBeVisible();

  await page.getByRole('link', { name: '내 배지로 돌아가기' }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/badges$/);

  await page.getByRole('link', { name: /물 마시기 7일 배지.*미획득/ }).click();
  await expect(page.getByText('공식 챌린지 배지')).toBeVisible();
  await expect(page.getByText('아직 획득하지 않았어요.')).toBeVisible();
});

test('획득한 배지가 없으면 다음 행동이 있는 빈 상태를 보여준다', async ({ page }) => {
  await page.goto('/dev/challenges/badges-empty');

  await expect(page.getByRole('heading', { name: '내 배지' })).toBeVisible();
  await expect(page.getByText('아직 모은 배지가 없어요')).toBeVisible();
  await page.getByRole('link', { name: '챌린지 둘러보기' }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/browse$/);
});

test('홈 챌린지는 요약과 이동만 제공하고 직접 인증 액션은 두지 않는다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const challenge = page.getByRole('region', { name: '챌린지' });
  await expect(challenge.getByRole('link', { name: /감기약 복약 챌린지/ })).toBeVisible();
  await expect(challenge.getByRole('link', { name: /영양제 루틴 챌린지/ })).toBeVisible();
  await expect(challenge.getByRole('button', { name: /했어요/ })).toHaveCount(0);
});

test('홈 챌린지 빈 상태는 최신 맞춤 진입 문구를 제공한다', async ({ page }) => {
  await page.goto('/dev/home-challenge-empty');

  const challenge = page.getByRole('region', { name: '챌린지' });
  await expect(challenge.getByText('참여 중인 챌린지가 없어요')).toBeVisible();
  await challenge.getByRole('link', { name: '맞춤 챌린지 보기' }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/tailored$/);
});

test('복약이 없는 홈에서도 독립적인 챌린지 요약을 보여준다', async ({ page }) => {
  await page.goto('/dev/home-empty');

  const challenge = page.getByRole('region', { name: '챌린지' });
  await expect(challenge.getByRole('link', { name: /감기약 복약 챌린지/ })).toBeVisible();
  await expect(challenge.getByRole('button', { name: /했어요/ })).toHaveCount(0);
});

test('마이페이지 챌린지 기록은 내 챌린지로 이동한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');

  await page.getByRole('button', { name: '챌린지 기록' }).click();
  await expect(page).toHaveURL(/\/dev\/challenges$/);
  await expect(page.getByRole('heading', { name: '챌린지', exact: true })).toBeVisible();
});

test('개발 챌린지 전체 경로는 로그인 없이 서로 이동한다', async ({ page }) => {
  const routes = [
    ['/dev/challenges', '챌린지'],
    ['/dev/challenges/browse', '챌린지'],
    ['/dev/challenges/official/official-walk-7d', '매일 30분 걷기'],
    ['/dev/challenges/participations/part-official-active', '매일 30분 걷기'],
    ['/dev/challenges/tailored', '맞춤 챌린지'],
    ['/dev/challenges/tailored/medication', '복약'],
    ['/dev/challenges/create', '나만의'],
    ['/dev/challenges/badges', '내 배지'],
    ['/dev/challenges/badges/badge-walk', '배지 상세'],
    [
      '/dev/challenges/participations/part-review-active/records/review-medications',
      '복약 기록',
    ],
  ] as const;

  for (const [path, heading] of routes) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`${path.replaceAll('/', '\\/')}$`));
    await expect(page.getByRole('heading', { name: new RegExp(heading) }).first()).toBeVisible();
    await expect(page.getByText('로그인이 필요')).toHaveCount(0);
  }
});
