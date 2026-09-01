import { expect, test } from 'playwright/test';

async function expandMorningMedication(page: import('playwright/test').Page) {
  await page.getByRole('button', { name: /아침약 \d+개.*자세히 보기/ }).click();
}

test('다중 care episode 목업은 서로 다른 회차의 약을 같은 홈에 제공한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const disclosure = page.getByRole('button', { name: /아침약 3개.*08:00.*자세히 보기/ });
  await expect(disclosure).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(page.getByText('아목시실린 500mg')).toHaveCount(0);

  await disclosure.click();
  const expandedDisclosure = page.getByRole('button', {
    name: /아침약 3개.*08:00.*간단히 보기/,
  });
  await expect(expandedDisclosure).toHaveAttribute('aria-expanded', 'true');
  const morning = page.getByRole('group', { name: '아침약 상세' });
  await expect(morning.getByText('셀레콕시브 200mg')).toBeVisible();
  await expect(morning.getByText('아목시실린 500mg')).toBeVisible();
  await expect(morning.getByText('8월 22일 처방')).toHaveCount(2);
  await expect(morning.getByText('8월 24일 처방')).toBeVisible();

  await morning.getByRole('button', { name: '3개 먹었어요' }).click();
  await expect(page.getByLabel('8월 25일 아침 먹은 기록')).toBeVisible();

  await expandedDisclosure.click();
  await expect(page.getByRole('button', { name: /아침약 3개.*자세히 보기/ })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  await expect(page.getByText('셀레콕시브 200mg')).toHaveCount(0);
});

test('홈 잔디는 타임라인 아래에서 복약 기간과 약이 있는 슬롯만 보여준다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const timeline = page.getByRole('region', { name: '오늘의 복약' });
  const records = page.getByRole('region', { name: '복약 기록' });

  await expect(records.getByText('8월 22일 ~ 31일')).toBeVisible();
  await expect(records.getByRole('columnheader')).toHaveCount(10);
  await expect(records.getByRole('row', { name: '아침' })).toBeVisible();
  await expect(records.getByRole('row', { name: '저녁' })).toBeVisible();
  await expect(records.getByRole('row', { name: '점심' })).toHaveCount(0);
  await expect(records.getByRole('row', { name: '취침 전' })).toHaveCount(0);
  await expect(records.getByLabel('8월 22일 아침 먹은 기록')).toBeVisible();
  await expect(records.getByLabel('8월 25일 아침 기록 없음')).toBeVisible();
  await expect(records.getByLabel('8월 25일 저녁 아직')).toBeVisible();
  await expect(records.getByLabel('8월 29일 아침 약 없음')).toBeVisible();
  await expect(records.getByLabel('8월 29일 저녁 아직')).toBeVisible();
  await expect(records.getByText('먹은 기록', { exact: true })).toBeVisible();
  await expect(records.getByText('기록 없음', { exact: true })).toBeVisible();
  await expect(records.getByText('아직', { exact: true })).toBeVisible();
  await expect(records.getByText(/안 먹음|안 드셨어요|%|연속/)).toHaveCount(0);

  await expect(records.getByRole('button', { name: '이전 10일' })).toBeDisabled();
  await expect(records.getByRole('button', { name: '다음 10일' })).toBeDisabled();

  const timelineBox = await timeline.boundingBox();
  const recordsBox = await records.boundingBox();
  expect(timelineBox).not.toBeNull();
  expect(recordsBox).not.toBeNull();
  expect(timelineBox!.y + timelineBox!.height).toBeLessThanOrEqual(recordsBox!.y);
});

test('홈에서 먹었어요를 누르면 오늘 잔디 칸이 새로고침 없이 채워지고 되돌릴 수 있다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');

  await expandMorningMedication(page);
  await page.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(page.getByLabel('8월 25일 아침 먹은 기록')).toBeVisible();
  await page.getByRole('button', { name: '되돌리기' }).click();
  await expect(page.getByLabel('8월 25일 아침 기록 없음')).toBeVisible();
});

test('지난 기록 없음 칸은 뒤늦게 체크되고 아직 칸은 반응하지 않는다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const past = page.getByLabel('8월 24일 저녁 기록 없음');
  const future = page.getByLabel('8월 25일 저녁 아직');

  await expect(future).toBeDisabled();
  await past.click();
  await expect(page.getByLabel('8월 24일 저녁 먹은 기록')).toBeVisible();
});

test('14일 복약 기록은 375px 홈에서 10일씩 이동하며 가로 스크롤이 생기지 않는다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-14-days');
  const grid = page.getByRole('grid', { name: '복약 기간 기록' });
  const previous = page.getByRole('button', { name: '이전 10일' });
  const next = page.getByRole('button', { name: '다음 10일' });

  await expect(page.getByText('8월 22일 ~ 31일')).toBeVisible();
  await expect(grid.getByRole('columnheader')).toHaveCount(10);
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();
  const overflow = await grid.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
  const viewportOverflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewportOverflow.scrollWidth).toBeLessThanOrEqual(viewportOverflow.clientWidth);

  await next.click();
  await expect(page.getByText('9월 1일 ~ 4일')).toBeVisible();
  await expect(grid.getByRole('columnheader')).toHaveCount(4);
  await expect(page.getByLabel('9월 1일 아침 아직')).toBeVisible();
  await expect(page.getByLabel('8월 22일 아침 먹은 기록')).toHaveCount(0);
  await expect(previous).toBeEnabled();
  await expect(next).toBeDisabled();
});

test('480px에서도 슬롯명과 첫 날짜 사이가 목업 간격을 유지한다', async ({ page }) => {
  await page.setViewportSize({ width: 480, height: 812 });
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-14-days');

  const rowHeader = page.getByRole('rowheader', { name: '아침' });
  const rowHeaderTextRight = await rowHeader.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const box = range.getBoundingClientRect();
    return box.x + box.width;
  });
  const firstDateBox = await page
    .getByRole('columnheader', { name: '8월 22일' })
    .boundingBox();

  expect(firstDateBox).not.toBeNull();
  const labelToFirstDateGap = firstDateBox!.x - rowHeaderTextRight;
  expect(labelToFirstDateGap).toBeGreaterThanOrEqual(0);
  expect(labelToFirstDateGap).toBeLessThanOrEqual(24);
});

test('복약이 끝난 홈에도 그 회차의 기록 잔디가 남고 복약 탭에는 중복하지 않는다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-09-01T12:00:00+09:00'));
  await page.goto('/dev/home-data-ended');
  await expect(page.getByRole('region', { name: '복약 기록' })).toBeVisible();

  await page.goto('/dev/medications');
  await expect(page.getByRole('region', { name: '복약 기록' })).toHaveCount(0);
});
