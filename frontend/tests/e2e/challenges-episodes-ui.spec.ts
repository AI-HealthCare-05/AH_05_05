import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('지난 기록은 기본으로 접혀 있고 다시 진입해도 접힌 상태로 시작한다', async ({ page }) => {
  await page.goto('/dev/challenges');

  const historyToggle = page.getByRole('button', { name: '지난 기록 펼치기' });
  await expect(historyToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('link', { name: '저녁 산책 7일 자세히 보기' })).toHaveCount(0);

  await historyToggle.click();
  await expect(page.getByRole('button', { name: '지난 기록 접기' })).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('link', { name: '저녁 산책 7일 자세히 보기' })).toBeVisible();

  await page.getByRole('link', { name: '둘러보기' }).click();
  await page.getByRole('link', { name: '마이' }).click();
  await expect(page.getByRole('button', { name: '지난 기록 펼치기' })).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('link', { name: '저녁 산책 7일 자세히 보기' })).toHaveCount(0);
});

test('복약 대상은 처방 회차별로 선택하며 예정 복용 횟수를 합산한다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored/medication');

  const coldEpisode = page.getByRole('checkbox', { name: /감기약/ });
  const septemberEpisode = page.getByRole('checkbox', { name: /9월 7일 처방/ });
  const joinButton = page.getByRole('button', { name: '이 대상으로 참여하기' });

  await expect(coldEpisode).toBeChecked();
  await expect(septemberEpisode).not.toBeChecked();
  await expect(page.getByText('선택한 처방 1개 · 총 9회')).toBeVisible();
  await expect(page.getByText('같은 처방 회차의 같은 날짜·시간대는 약이 여러 개여도 1회로 계산해요.')).toBeVisible();

  await septemberEpisode.check();
  await expect(page.getByText('선택한 처방 2개 · 총 23회')).toBeVisible();

  await coldEpisode.uncheck();
  await septemberEpisode.uncheck();
  await expect(joinButton).toBeDisabled();
});

test('복약 참여 상세는 선택한 처방 회차별 진행률을 보여 주고 일 단위 인증표를 숨긴다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored/medication');
  await page.getByRole('checkbox', { name: /9월 7일 처방/ }).check();
  await page.getByRole('button', { name: '이 대상으로 참여하기' }).click();

  await expect(page).toHaveURL(/\/dev\/challenges\/participations\/part-medication-active$/);
  await expect(page.getByText('6 / 23회 인증')).toBeVisible();
  await expect(page.getByText('전체 달성률 26%')).toBeVisible();

  const coldProgress = page.getByRole('article', { name: '감기약 진행률' });
  await expect(coldProgress.getByText('6 / 9회')).toBeVisible();
  await expect(coldProgress.getByText('67%')).toBeVisible();

  const septemberProgress = page.getByRole('article', { name: '9월 7일 처방 진행률' });
  await expect(septemberProgress.getByText('0 / 14회')).toBeVisible();
  await expect(septemberProgress.getByText('0%')).toBeVisible();

  await expect(page.getByLabel('날짜별 인증 기록')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /했어요|오늘 인증 완료/ })).toHaveCount(0);
});
