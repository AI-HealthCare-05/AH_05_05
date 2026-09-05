import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('처방 상세를 펼쳐 세로 스크롤이 생겨도 복약 카드 폭과 액션 높이를 유지한다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 940 });
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'home-expand-layout-token');
    sessionStorage.setItem('poke.account-principal', 'home-expand-layout@example.com');
  });
  await page.goto('/dev/home-multiple-episodes');

  const main = page.locator('main');
  const timeline = page.getByRole('region', { name: '오늘의 복약' });
  const outerCard = timeline.locator(':scope > div').first();
  const action = timeline.getByRole('button', { name: '먹었어요' });
  const beforeCard = await outerCard.boundingBox();
  const beforeAction = await action.boundingBox();
  expect(beforeCard).not.toBeNull();
  expect(beforeAction).not.toBeNull();

  await timeline.getByRole('button', { name: /8월 22일 처방.*펼치기/ }).click();

  const afterCard = await outerCard.boundingBox();
  const afterAction = await action.boundingBox();
  expect(afterCard).not.toBeNull();
  expect(afterAction).not.toBeNull();
  expect(Math.abs(afterCard!.x - beforeCard!.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(afterCard!.width - beforeCard!.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(afterAction!.height - beforeAction!.height)).toBeLessThanOrEqual(1);
  await expect(main).toHaveCSS('scrollbar-gutter', 'stable');
  expect(await main.evaluate((element) => element.scrollWidth)).toBe(
    await main.evaluate((element) => element.clientWidth),
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    await page.evaluate(() => document.documentElement.clientWidth),
  );
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

  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await expect(detail.getByRole('button', { name: '먹었어요' })).toBeVisible();
  await expect(detail.getByRole('button', { name: '복약 메모' })).toBeVisible();
  await expect(detail.getByRole('button', { name: /먹었어요/ })).toBeVisible();
  await detail.getByRole('button', { name: /먹었어요/ }).click();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();

  await detail.getByRole('button', { name: '복약 메모' }).click();
  await expect(page).toHaveURL(/\/medications\/notes\/new$/);
});

test('목업에서도 한 처방만 기록하면 새로고침 뒤 그 처방만 완료다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'home-dose-refresh-token');
    sessionStorage.setItem('poke.account-principal', 'home-dose-refresh@example.com');
  });
  await page.goto('/dev/home-multiple-episodes');

  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  const secondEpisode = morning.getByRole('article', { name: /8월 24일 처방/ });
  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(page.getByRole('button', { name: '되돌리기', exact: true })).toBeVisible();
  await page.reload();

  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
});

test('목업 복용 기록은 로그인 principal별로 격리된다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('poke.account-principal')) {
      sessionStorage.setItem('poke.account-principal', 'dose-account-a@example.com');
    }
  });
  await page.goto('/dev/home-multiple-episodes');

  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(page.getByRole('button', { name: '되돌리기', exact: true })).toBeVisible();

  await page.evaluate(() => {
    sessionStorage.setItem('poke.account-principal', 'dose-account-b@example.com');
  });
  await page.reload();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);

  await page.evaluate(() => {
    sessionStorage.setItem('poke.account-principal', 'dose-account-a@example.com');
  });
  await page.reload();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
});

test('다중 처방은 각 회차를 독립적으로 펼치고 접는다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const morning = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  const secondEpisode = morning.getByRole('article', { name: /8월 24일 처방/ });
  await expect(page.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(page.getByText('아목시실린 500mg')).toHaveCount(0);

  await firstEpisode.getByRole('button', { name: /펼치기/ }).click();
  await expect(
    firstEpisode.getByRole('group', { name: /처방 약 상세/ }).getByText('셀레콕시브 200mg', {
      exact: true,
    }),
  ).toBeVisible();

  await secondEpisode.getByRole('button', { name: /펼치기/ }).click();
  await expect(
    secondEpisode.getByRole('list', { name: /처방 약 목록/ }).getByText('아목시실린 500mg', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(morning.getByRole('heading', { name: '감기약', exact: true })).toBeVisible();
  await expect(morning.getByRole('heading', { name: '지난 처방', exact: true })).toBeVisible();

  await firstEpisode.getByRole('button', { name: /접기/ }).click();
  await expect(firstEpisode.getByText('셀레콕시브 200mg', { exact: true })).toHaveCount(0);
  await expect(
    secondEpisode.getByRole('list', { name: /처방 약 목록/ }).getByText('아목시실린 500mg', {
      exact: true,
    }),
  ).toBeVisible();
});

test('처방 별칭은 화면 제목에만 사용하고 날짜 기반 접근성 이름을 유지한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const firstEpisode = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' })
    .getByRole('article', { name: /8월 22일 처방/ });

  await expect(firstEpisode.getByRole('heading', { name: '감기약', exact: true })).toBeVisible();
  await expect(
    firstEpisode.getByRole('button', { name: '8월 22일 처방 선택', exact: true }),
  ).toHaveCount(1);
  await expect(
    firstEpisode.getByRole('button', { name: '8월 22일 처방 펼치기', exact: true }),
  ).toHaveCount(1);
});

test('처방 행은 별칭과 24px 선택 glyph를 사용하고 chevron만 펼침을 토글한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const morning = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  const row = firstEpisode.locator('[data-episode-row]');
  const selection = firstEpisode.getByRole('button', { name: '8월 22일 처방 선택', exact: true });
  const glyph = firstEpisode.locator('[data-episode-selection-glyph]');
  const rowBox = await row.boundingBox();
  const glyphBox = await glyph.boundingBox();

  expect(rowBox).not.toBeNull();
  expect(rowBox!.height).toBeGreaterThanOrEqual(56);
  expect(rowBox!.height).toBeLessThanOrEqual(64);
  expect(glyphBox).not.toBeNull();
  expect(glyphBox!.width).toBe(24);
  expect(glyphBox!.height).toBe(24);
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await expect(firstEpisode.getByRole('heading', { name: '감기약', exact: true })).toBeVisible();
  await expect(morning.getByRole('button', { name: '다른 처방 펼치기' })).toHaveCount(0);
  const chevron = firstEpisode.getByRole('button', {
    name: '8월 22일 처방 펼치기',
    exact: true,
  });
  const chevronBox = await chevron.boundingBox();
  expect(chevronBox).not.toBeNull();
  expect(chevronBox!.width).toBeGreaterThanOrEqual(44);
  expect(chevronBox!.height).toBeGreaterThanOrEqual(44);
  await expect(chevron).toHaveAttribute('aria-expanded', 'false');

  await chevron.click();
  await expect(chevron).toHaveAttribute('aria-expanded', 'true');
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await expect(selection).toHaveAttribute('aria-pressed', 'false');
  await firstEpisode.getByRole('button', { name: '8월 22일 처방 접기', exact: true }).click();
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await expect(selection).toHaveAttribute('aria-pressed', 'false');

  await row.click();
  await expect(selection).toHaveAttribute('aria-pressed', 'true');
  await expect(row).toHaveAttribute('aria-pressed', 'true');
  await expect(row).toHaveClass(/bg-action-soft/);
  await expect(chevron).toHaveAttribute('aria-expanded', 'false');

  await chevron.click();
  await expect(
    firstEpisode.getByRole('button', { name: '8월 22일 처방 접기', exact: true }),
  ).toHaveAttribute('aria-expanded', 'true');
  await expect(selection).toHaveAttribute('aria-pressed', 'true');
});

test('복약 액션은 간결한 라벨과 완료 badge를 사용하고 되돌릴 수 있다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const firstEpisode = detail.getByRole('article', { name: /8월 22일 처방/ });
  const action = detail.getByRole('button', { name: '먹었어요' });
  await expect(action).toBeVisible();
  await expect(detail.getByRole('button', { name: /개 먹었어요/ })).toHaveCount(0);
  await expect(action.locator('svg')).toHaveCount(0);
  await expect(detail.getByRole('button', { name: '복약 메모' })).toBeVisible();

  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await action.click();
  await expect(firstEpisode.getByRole('button', { name: /8월 22일 처방.*복용 완료/ })).toBeVisible();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toContainText('복용 완료');
  const badgeCheck = firstEpisode.locator('[data-episode-completed-badge] svg');
  const badgeCheckBox = await badgeCheck.boundingBox();
  expect(badgeCheckBox).not.toBeNull();
  expect(badgeCheckBox!.width).toBe(20);
  expect(badgeCheckBox!.height).toBe(20);

  const undo = detail.getByRole('button', { name: '복약 기록 되돌리기' });
  await expect(undo).toBeVisible();
  await expect(undo).toBeDisabled();
  await expect(undo).toHaveClass(/bg-card/);
  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*복용 완료/ }).click();
  await expect(undo).toBeEnabled();
  await expect(undo).toHaveClass(/bg-primary/);
  await undo.click();
  await expect(detail.getByRole('button', { name: '먹었어요' })).toBeVisible();
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
  const morningSupplements = supplements.getByRole('group', { name: '아침 영양제' });
  await expect(morningSupplements.getByRole('button', { name: '개별 선택' })).toHaveAttribute('aria-pressed', 'false');
  await expect(morningSupplements.getByRole('button', { name: '다 먹었어요' })).toBeEnabled();
  await expect(page.getByRole('region', { name: '영양제 랭킹' })).toBeVisible();
});

test('로그인 홈은 챌린지 자리만 비대화형 카드로 예약한다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const challenge = page.getByRole('region', { name: '챌린지' });
  await expect(challenge).toBeVisible();
  const placeholder = challenge.locator('[data-challenge-placeholder]');
  await expect(placeholder).toHaveCount(1);
  await expect(placeholder).toHaveCSS('height', '132px');
  expect(
    await placeholder.evaluate((element) => ({
      role: element.getAttribute('role'),
      tabIndex: element.getAttribute('tabindex'),
      hasInteractiveSemantics: element.matches('button, a, input, [role="button"], [tabindex]') ||
        element.querySelector('button, a, input, [role="button"], [tabindex]') !== null,
    })),
  ).toEqual({ role: null, tabIndex: null, hasInteractiveSemantics: false });
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

  await first.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await detail.getByRole('button', { name: '먹었어요' }).click();
  await expect(first.getByRole('button', { name: /8월 22일 처방 복용 완료/ })).toBeVisible();
  const inactiveAction = detail.getByRole('button', { name: '먹었어요' });
  await expect(inactiveAction).toBeDisabled();
  await expect(inactiveAction).toHaveClass(/bg-card/);

  const secondSelector = second.getByRole('button', { name: /8월 24일 처방.*선택/ });
  await expect(secondSelector).toBeVisible();
  await secondSelector.click();
  const activeAction = detail.getByRole('button', { name: '먹었어요' });
  await expect(activeAction).toBeEnabled();
  await expect(activeAction).toHaveClass(/bg-primary/);
  await activeAction.click();
  await expect(second.getByRole('button', { name: /8월 24일 처방 복용 완료/ })).toBeVisible();
  const completedAction = detail.getByRole('button', { name: '복약 기록 되돌리기' });
  await expect(completedAction).toBeDisabled();
  await second.getByRole('button', { name: /8월 24일 처방.*복용 완료/ }).click();
  await expect(completedAction).toBeEnabled();
  await expect(completedAction).toHaveClass(/bg-primary/);
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
  const firstSelector = first.getByRole('button', { name: /8월 22일 처방.*선택/ });
  const secondSelector = second.getByRole('button', { name: /8월 24일 처방.*선택/ });

  await firstSelector.click();
  await expect(firstSelector).toHaveAttribute('aria-pressed', 'true');
  await expect(secondSelector).toHaveAttribute('aria-pressed', 'false');
  await detail.getByRole('button', { name: '먹었어요' }).click();
  await expect(first.getByRole('button', { name: /8월 22일 처방 복용 완료/ })).toBeVisible();
  await expect(second.getByRole('button', { name: /8월 24일 처방.*선택/ })).toBeVisible();

  await page.getByRole('button', { name: '되돌리기' }).click();
  await expect(first.getByRole('button', { name: /8월 22일 처방.*선택/ })).toBeVisible();
  await expect(second.getByRole('button', { name: /8월 24일 처방.*선택/ })).toBeVisible();
});

test('회차 복약 기록 실패와 날짜 변경은 낙관적 회차 상태를 초기화한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-dose-save-error');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const episode = detail
    .getByRole('article', { name: /8월 22일 처방/, includeHidden: true });
  await detail.getByRole('button', { name: '먹었어요' }).click();
  await expect(page.getByRole('dialog', { name: '기록하지 못했어요' })).toBeVisible();
  await expect(
    page
      .locator('article[aria-label*="8월 22일 처방"]')
      .first()
      .locator('button[aria-label*="8월 22일 처방"][aria-label$="선택"]'),
  ).toHaveCount(1);
});

test('날짜 변경은 성공한 회차의 낙관 상태를 초기화한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const episode = detail.getByRole('article', { name: /8월 22일 처방/ });
  await episode.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await detail.getByRole('button', { name: '먹었어요' }).click();
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
  await expect(refreshedEpisode.getByRole('button', { name: /8월 22일 처방.*선택/ })).toBeVisible();
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
