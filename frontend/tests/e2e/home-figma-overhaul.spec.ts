import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('홈은 시간대 안에서 처방 회차를 요약하고 메모와 복용 액션을 나눈다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const today = page.getByRole('region', { name: '오늘의 복약' });
  const timeline = today.getByRole('group', { name: '하루 복약 시간표' });
  const morning = timeline.getByRole('button', {
    name: /아침약 3개.*자세히 보기/,
  });

  await morning.click();

  const detail = timeline.getByRole('group', { name: '아침약 상세' });
  const firstEpisode = detail.getByRole('article', { name: /8월 22일 처방/ });
  const secondEpisode = detail.getByRole('article', { name: /8월 24일 처방/ });
  await expect(firstEpisode).toBeVisible();
  await expect(secondEpisode).toBeVisible();
  await expect(firstEpisode.getByText('셀레콕시브 외 1개')).toBeVisible();

  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*펼치기/ }).click();
  await expect(
    firstEpisode.getByRole('group', { name: /8월 22일 처방 약 상세/ }).getByText('셀레콕시브 200mg'),
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

test('게스트 홈은 세 배너 compact carousel을 유지하며 390x844에서 세로 overflow가 없다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/home');

  const carousel = page.getByRole('region', { name: 'RxVita 기능 소개' });
  await expect(carousel.locator('article')).toHaveCount(4);
  await expect(carousel.locator('article').first()).toHaveCSS('flex-direction', 'row');

  const overflow = await page.evaluate(() => {
    const main = document.querySelector('main');
    if (!(main instanceof HTMLElement)) throw new Error('홈 본문을 찾지 못했습니다.');
    return { clientHeight: main.clientHeight, scrollHeight: main.scrollHeight };
  });
  expect(overflow.scrollHeight).toBeLessThanOrEqual(overflow.clientHeight);
});
