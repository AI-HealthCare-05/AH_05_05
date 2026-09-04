import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('홈은 시간대 안에서 처방 회차를 요약하고 메모와 복용 액션을 나눈다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'home-figma-medication-token');
    sessionStorage.setItem('poke.account-principal', 'home-figma-medication@example.com');
  });
  await page.goto('/dev/home-multiple-episodes');

  const today = page.getByRole('region', { name: '오늘의 복약' });
  const detail = today.getByRole('group', { name: '아침약 상세' });
  const firstEpisode = detail.getByRole('article', { name: /8월 22일 처방/ });
  const secondEpisode = detail.getByRole('article', { name: /8월 24일 처방/ });
  await expect(firstEpisode).toBeVisible();
  await expect(secondEpisode).toBeVisible();
  await expect(firstEpisode.getByText('셀레콕시브 외 1개')).toBeVisible();

  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*펼치기/ }).click();
  await expect(
    firstEpisode
      .getByRole('group', { name: /8월 22일 처방 약 상세/ })
      .getByText('셀레콕시브 200mg', { exact: true }),
  ).toBeVisible();

  await firstEpisode.getByRole('button', { name: '8월 22일 처방 선택' }).click();
  await expect(detail.getByRole('button', { name: '2개 먹었어요' })).toBeVisible();
  await expect(detail.getByRole('button', { name: '복약 메모 쓰기' })).toBeVisible();
  await expect(detail.getByRole('button', { name: /먹었어요/ })).toBeVisible();
  await detail.getByRole('button', { name: /먹었어요/ }).click();
  await expect(page.getByLabel('8월 25일 아침 먹은 기록')).toBeVisible();

  await detail.getByRole('button', { name: '복약 메모 쓰기' }).click();
  await expect(page).toHaveURL(/\/medications\/notes\/new$/);
});

test('로그인 홈은 오늘의 복약과 오늘의 영양제 탭 아래 카드 구성을 제공한다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const tabs = page.getByRole('tablist', { name: '오늘의 홈 탭' });
  await expect(tabs.getByRole('tab', { name: '오늘의 복약' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('region', { name: '오늘의 복약' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'RxVita 기능 소개' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '오늘의 복약' })).toHaveCount(0);
  await expect(page.getByRole('group', { name: '하루 복약 시간표' })).toHaveCount(0);

  await tabs.getByRole('tab', { name: '오늘의 영양제' }).click();
  const supplements = page.getByRole('region', { name: '오늘의 영양제' });
  await expect(supplements).toBeVisible();
  await expect(supplements.getByRole('button', { name: '개별 선택' })).toBeVisible();
  await expect(supplements.getByText('1개 먹었어요', { exact: true })).toBeVisible();
  await expect(supplements.getByText('다 먹었어요', { exact: true })).toBeVisible();
  await expect(supplements.getByRole('button', { name: '1개 먹었어요' })).toHaveCount(0);
  await expect(supplements.getByRole('button', { name: '다 먹었어요' })).toHaveCount(0);
  await expect(supplements.getByRole('button', { name: '개별 선택' })).not.toHaveAttribute(
    'aria-pressed',
  );
  await expect(page.getByRole('region', { name: '영양제 랭킹' })).toBeVisible();
});

test('회차별 복약 액션은 첫 회차 완료 뒤에도 선택한 다음 회차를 독립적으로 기록한다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const first = detail.getByRole('article', { name: /8월 22일 처방/ });
  const second = detail.getByRole('article', { name: /8월 24일 처방/ });

  await first.getByRole('button', { name: '8월 22일 처방 선택' }).click();
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(first.getByRole('button', { name: /8월 22일 처방 복용 완료/ })).toBeVisible();

  const secondSelector = second.getByRole('button', { name: '8월 24일 처방 선택' });
  await expect(secondSelector).toBeVisible();
  await secondSelector.click();
  await expect(detail.getByRole('button', { name: '1개 먹었어요' })).toBeVisible();
  await detail.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(second.getByRole('button', { name: /8월 24일 처방 복용 완료/ })).toBeVisible();
});

test('회차 선택은 다른 회차를 미완료로 유지하고 되돌리기 뒤 회차 상태를 되돌린다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const first = detail.getByRole('article', { name: /8월 22일 처방/ });
  const second = detail.getByRole('article', { name: /8월 24일 처방/ });
  const firstSelector = first.getByRole('button', { name: '8월 22일 처방 선택' });
  const secondSelector = second.getByRole('button', { name: '8월 24일 처방 선택' });

  await firstSelector.click();
  await expect(firstSelector).toHaveAttribute('aria-pressed', 'true');
  await expect(secondSelector).toHaveAttribute('aria-pressed', 'false');
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(first.getByRole('button', { name: /8월 22일 처방 복용 완료/ })).toBeVisible();
  await expect(second.getByRole('button', { name: '8월 24일 처방 선택' })).toBeVisible();

  await page.getByRole('button', { name: '되돌리기' }).click();
  await expect(first.getByRole('button', { name: '8월 22일 처방 선택' })).toBeVisible();
  await expect(second.getByRole('button', { name: '8월 24일 처방 선택' })).toBeVisible();
});

test('회차 복약 기록 실패와 날짜 변경은 낙관적 회차 상태를 초기화한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-dose-save-error');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const episode = detail
    .getByRole('article', { name: /8월 22일 처방/, includeHidden: true });
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(page.getByRole('dialog', { name: '기록하지 못했어요' })).toBeVisible();
  await expect(
    page.locator('article[aria-label^="8월 22일 처방"]').first().locator('button[aria-label="8월 22일 처방 선택"]'),
  ).toHaveCount(1);
});

test('날짜 변경은 성공한 회차의 낙관 상태를 초기화한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const episode = detail.getByRole('article', { name: /8월 22일 처방/ });
  await episode.getByRole('button', { name: '8월 22일 처방 선택' }).click();
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(episode.getByRole('button', { name: /8월 22일 처방 복용 완료/ })).toBeVisible();

  await page.clock.setFixedTime(new Date('2026-08-26T12:00:00+09:00'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  const refreshedDetail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(refreshedDetail).toBeVisible();
  const refreshedEpisode = refreshedDetail
    .getByRole('article', { name: /8월 22일 처방/ });
  await expect(refreshedEpisode).toBeVisible();
  await expect(refreshedEpisode.getByRole('button', { name: '8월 22일 처방 선택' })).toBeVisible();
});

test('게스트 홈은 세 배너 compact carousel을 유지하며 390x844에서 세로 overflow가 없다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/home');

  const carousel = page.getByRole('region', { name: 'RxVita 기능 소개' });
  await expect(carousel.locator('article:not([aria-hidden="true"])')).toHaveCount(3);
  await expect(carousel.locator('article').first()).toHaveCSS('flex-direction', 'row');

  const heading = page.getByRole('heading', { name: '오늘의 복약' });
  await expect(heading).toBeVisible();
  await expect(page.getByRole('button', { name: '로그인하고 시작하기' })).toBeVisible();
  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking.getByRole('heading', { name: '인기 영양제' })).toBeVisible();
  await expect(ranking.getByRole('listitem')).toHaveCount(5);

  const rankingBox = await ranking.boundingBox();
  const carouselBox = await carousel.boundingBox();
  expect(rankingBox).not.toBeNull();
  expect(carouselBox).not.toBeNull();
  expect(carouselBox!.y).toBeGreaterThan(rankingBox!.y);

  const overflow = await page.evaluate(() => ({
    documentScrollHeight: document.documentElement.scrollHeight,
    bodyScrollHeight: document.body.scrollHeight,
    viewportHeight: window.innerHeight,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(overflow.documentScrollHeight).toBeLessThanOrEqual(overflow.viewportHeight);
  expect(overflow.bodyScrollHeight).toBeLessThanOrEqual(overflow.viewportHeight);
  expect(overflow.documentScrollWidth).toBeLessThanOrEqual(overflow.viewportWidth);
  expect(overflow.bodyScrollWidth).toBeLessThanOrEqual(overflow.viewportWidth);
});
