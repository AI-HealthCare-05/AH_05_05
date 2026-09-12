import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';
import { waitForVisibleImages } from './helpers/visibleImages';

test.setTimeout(20_000);

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

for (const width of [375, 390, 1280]) {
  test(`개발 배지 목록·빈 상태·상세·없음 화면은 공통 상단을 유지한다 (${width}px)`, async ({ page }, testInfo) => {
    test.setTimeout(30_000);
    await page.setViewportSize({ width, height: 900 });
    const cases = [
      ['/dev/challenges/badges', '내 배지'],
      ['/dev/challenges/badges-empty', '내 배지'],
      ['/dev/challenges/badges/badge-walk', '배지 상세'],
      ['/dev/challenges/badges/not-found', '배지를 찾을 수 없어요'],
    ] as const;

    for (const [path, title] of cases) {
      await page.goto(path);
      const header = page.getByRole('banner');
      const main = page.getByRole('main');
      const back = header.getByRole('button', { name: '뒤로 가기' });
      await expect(header.getByRole('heading', { name: title, exact: true })).toHaveCount(1);
      await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCount(1);
      await expect(back).toBeVisible();

      const [headerBox, mainBox, backBox, style] = await Promise.all([
        header.boundingBox(),
        main.boundingBox(),
        back.boundingBox(),
        header.evaluate((element) => {
          const computed = getComputedStyle(element);
          return {
            backgroundColor: computed.backgroundColor,
            borderBottomStyle: computed.borderBottomStyle,
            borderBottomWidth: computed.borderBottomWidth,
          };
        }),
      ]);
      expect(headerBox).not.toBeNull();
      expect(mainBox).not.toBeNull();
      expect(backBox).not.toBeNull();
      expect(headerBox!.height).toBe(64);
      expect(headerBox!.x).toBe(mainBox!.x);
      expect(headerBox!.width).toBe(mainBox!.width);
      expect(backBox!.width).toBeGreaterThanOrEqual(44);
      expect(backBox!.height).toBeGreaterThanOrEqual(44);
      expect(style.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
      expect(style.borderBottomStyle).toBe('solid');
      expect(style.borderBottomWidth).toBe('1px');
    }

    await page.goto('/dev/challenges/badges');
    await expect(page.getByRole('heading', { name: '내 배지', exact: true })).toBeVisible();
    const badgeGrid = page.getByRole('list', { name: '챌린지 배지' });
    await expect(badgeGrid.getByRole('listitem')).toHaveCount(6);
    await expect(badgeGrid.locator('img')).toHaveCount(6);
    await waitForVisibleImages(page);
    await page.screenshot({
      path: testInfo.outputPath(`dev-badge-header-${width}.png`),
      fullPage: true,
      animations: 'disabled',
    });
  });
}

test('개발 배지 상단 뒤로가기는 직접 진입에서도 안전한 dev 경로를 사용한다', async ({ page }) => {
  const cases = [
    ['/dev/challenges/badges', '/dev/challenges'],
    ['/dev/challenges/badges/not-found', '/dev/challenges/badges'],
  ] as const;

  for (const [path, fallback] of cases) {
    await page.goto(path);
    await page.evaluate(() => {
      window.history.replaceState({ ...window.history.state, idx: 0 }, '');
    });
    await page.getByRole('banner').getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL(new RegExp(`${fallback.replaceAll('/', '\\/')}$`));
  }
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

test('홈 챌린지는 공식 직접 인증과 맞춤 자동 기록 경계를 유지한다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const challenge = page.getByRole('region', { name: '챌린지' });
  const official = challenge.getByRole('article', { name: '매일 30분 걷기', exact: true });
  const custom = challenge.getByRole('article', { name: '감기약 복약 챌린지', exact: true });
  await expect(official.getByRole('button', { name: /했어요/ })).toBeVisible();
  await expect(custom.getByRole('link', { name: /감기약 복약 챌린지/ })).toBeVisible();
  await expect(custom.getByRole('button', { name: /했어요/ })).toHaveCount(0);
  await expect(challenge.getByRole('link', { name: /영양제 루틴/ })).toBeVisible();
});

test('홈 챌린지 빈 상태는 챌린지 목록 진입을 제공한다', async ({ page }) => {
  await page.goto('/dev/home-challenge-empty');

  const challenge = page.getByRole('region', { name: '챌린지' });
  await expect(challenge.getByText('챌린지를 등록하고 생활습관 개선에 도전하세요.')).toBeVisible();
  await challenge.getByRole('link', { name: '전체 보기' }).click();
  await expect(page).toHaveURL(/\/dev\/challenges$/);
});

test('홈 챌린지는 모든 활성 유형을 공식과 맞춤으로 구분하고 지난 기록은 제외한다', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto('/dev/home-active');
  const summary = page.getByRole('region', { name: '챌린지', exact: true });
  await expect(summary.getByRole('link', { name: /상세 보기$/ })).toHaveCount(6);
  for (const title of ['매일 30분 걷기', '첫 도전 마무리']) {
    await expect(summary.getByRole('link', { name: new RegExp(title) }).getByText('공식', { exact: true })).toBeVisible();
  }
  for (const title of ['감기약 복약 챌린지', '영양제 루틴', '이번 주 기록 돌아보기', '다음 진료 준비하기']) {
    const custom = summary.getByRole('article', { name: title, exact: true });
    await expect(custom.getByText('맞춤', { exact: true })).toBeVisible();
    await expect(custom.getByRole('button', { name: /했어요/ })).toHaveCount(0);
  }
  await expect(summary.getByRole('link', { name: /8월 31일|저녁 산책|아침 스트레칭/ })).toHaveCount(0);
  expect(await summary.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await summary.screenshot({ path: testInfo.outputPath('home-challenge-mixed-320.png') });
});

test('복약이 없는 홈에서도 독립적인 챌린지 요약을 보여준다', async ({ page }) => {
  await page.goto('/dev/home-empty');

  const challenge = page.getByRole('region', { name: '챌린지' });
  const official = challenge.getByRole('article', { name: '매일 30분 걷기', exact: true });
  const custom = challenge.getByRole('article', { name: '감기약 복약 챌린지', exact: true });
  await expect(official.getByRole('button', { name: /했어요/ })).toBeVisible();
  await expect(custom.getByRole('link', { name: /감기약 복약 챌린지/ })).toBeVisible();
  await expect(custom.getByRole('button', { name: /했어요/ })).toHaveCount(0);
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
