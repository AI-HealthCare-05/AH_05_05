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

test('복약 대상은 처방 회차별 목표를 표시하고 이미 참여한 처방을 유지한다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored/medication');

  const coldEpisode = page.getByRole('checkbox', { name: /감기약/ });
  const septemberEpisode = page.getByRole('checkbox', { name: /9월 7일 처방/ });

  await expect(coldEpisode).toBeChecked();
  await expect(septemberEpisode).not.toBeChecked();
  await expect(coldEpisode).toBeDisabled();
  await expect(page.getByText('선택한 처방 1개 · 각각의 챌린지로 참여해요')).toBeVisible();
  await expect(page.getByText('같은 처방 회차의 같은 날짜·시간대는 약이 여러 개여도 1회로 계산해요.')).toBeVisible();

  await septemberEpisode.check();
  await expect(page.getByText('선택한 처방 2개 · 각각의 챌린지로 참여해요')).toBeVisible();
  await septemberEpisode.uncheck();
  await expect(coldEpisode).toBeChecked();
});

test('복약 참여 상세는 한 처방만 표시하고 일 단위 인증표를 숨긴다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored/medication');
  await page.getByRole('checkbox', { name: /9월 7일 처방/ }).check();
  await page.getByRole('button', { name: '이 대상으로 참여하기' }).click();
  await page.getByRole('link', { name: '감기약 복약 챌린지 자세히 보기', exact: true }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/participations\/part-medication-active$/);
  await expect(page.getByText('6 / 9회 인증')).toBeVisible();
  await expect(page.getByText('이 처방 달성률 67%')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('감기약 복약 챌린지');

  await expect(page.getByLabel('날짜별 인증 기록')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /했어요|오늘 인증 완료/ })).toHaveCount(0);
});
