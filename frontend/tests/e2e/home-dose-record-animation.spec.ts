import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
});

async function expandMorningMedication(page: import('playwright/test').Page) {
  await page.getByRole('button', { name: /아침약 2개.*자세히 보기/ }).click();
}

test('첫 렌더의 기존 복약 기록은 자라나는 애니메이션을 재생하지 않는다', async ({
  page,
}) => {
  await page.goto('/dev/home-active');
  const existing = page.getByLabel('8월 22일 아침 먹은 기록');

  await expect(existing).toBeVisible();
  await expect.poll(() => existing.evaluate((cell) => getComputedStyle(cell).animationName))
    .toBe('none');
});

test('방금 기록한 오늘 칸은 아래에서 220ms 동안 자라난다', async ({ page }) => {
  await page.goto('/dev/home-active');
  await expandMorningMedication(page);
  await page.getByRole('button', { name: '2개 먹었어요' }).click();
  const planted = page.getByLabel('8월 25일 아침 먹은 기록');

  await expect(planted).toBeVisible();
  const motion = await planted.evaluate((cell) => {
    const style = getComputedStyle(cell);
    return {
      name: style.animationName,
      duration: style.animationDuration,
      originY: Number.parseFloat(style.transformOrigin.split(' ')[1] ?? '0'),
      height: Number.parseFloat(style.height),
    };
  });
  expect(motion.name).toBe('record-cell-grow');
  expect(motion.duration).toBe('0.22s');
  expect(motion.originY).toBeCloseTo(motion.height, 0);
});

test('되돌리기는 역방향 애니메이션 없이 즉시 기록 없음으로 돌아간다', async ({ page }) => {
  await page.goto('/dev/home-active');
  await expandMorningMedication(page);
  await page.getByRole('button', { name: '2개 먹었어요' }).click();
  await page.getByRole('button', { name: '되돌리기' }).click();
  const reverted = page.getByLabel('8월 25일 아침 기록 없음');

  await expect(reverted).toBeVisible();
  await expect.poll(() => reverted.evaluate((cell) => getComputedStyle(cell).animationName))
    .toBe('none');
});

test('지난 기록을 뒤늦게 채울 때도 그 칸만 자라난다', async ({ page }) => {
  await page.goto('/dev/home-active');
  await page.getByLabel('8월 24일 저녁 기록 없음').click();
  const planted = page.getByLabel('8월 24일 저녁 먹은 기록');

  await expect(planted).toBeVisible();
  expect(await planted.evaluate((cell) => getComputedStyle(cell).animationName))
    .toBe('record-cell-grow');
  expect(await page.getByLabel('8월 22일 아침 먹은 기록').evaluate(
    (cell) => getComputedStyle(cell).animationName,
  )).toBe('none');
});

test('움직임 줄이기 설정에서는 새 기록도 색만 바뀐다', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/dev/home-active');
  await expandMorningMedication(page);
  await page.getByRole('button', { name: '2개 먹었어요' }).click();
  const planted = page.getByLabel('8월 25일 아침 먹은 기록');

  await expect(planted).toBeVisible();
  await expect.poll(() => planted.evaluate((cell) => getComputedStyle(cell).animationName))
    .toBe('none');
});
