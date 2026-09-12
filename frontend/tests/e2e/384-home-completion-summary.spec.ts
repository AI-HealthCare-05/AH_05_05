import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(60_000);

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('복약 시간대 전체 완료도 각 처방명 위에 표시하고 선택·되돌리기를 구분한다', async ({
  page,
}, testInfo) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '384-home-medication-summary-token');
    sessionStorage.setItem('poke.account-principal', '384-home-medication-summary@example.com');
  });
  await page.goto('/dev/home-multiple-episodes');

  const timeline = page.getByRole('region', { name: '오늘의 복약' });
  const detail = timeline.getByRole('group', { name: '아침약 상세' });
  const rows = detail.locator('[data-episode-row]');
  const headerSummary = timeline.locator('[data-medication-completed-summary]');

  await expect(rows).toHaveCount(2);
  await expect(headerSummary).toHaveCount(0);
  await expect(detail.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('384-medication-before.png'), fullPage: true });

  await rows.nth(0).click();
  await rows.nth(1).click();
  await detail.getByRole('button', { name: '먹었어요' }).click();

  await expect(headerSummary).toHaveCount(0);
  await expect(detail.locator('[data-episode-completed-badge]')).toHaveCount(2);
  await page.screenshot({ path: testInfo.outputPath('384-medication-after.png'), fullPage: true });

  await rows.nth(0).click();
  await expect(headerSummary).toHaveCount(0);
  await detail.getByRole('button', { name: '복약 기록 되돌리기' }).click();
  await expect(headerSummary).toHaveCount(0);
  await expect(detail.locator('[data-episode-completed-badge]')).toHaveCount(1);
});

test('복약 저장 실패는 전체 완료 요약을 만들지 않고 실패 회차를 다시 선택한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '384-home-medication-failure-token');
    sessionStorage.setItem('poke.account-principal', '384-home-medication-failure@example.com');
  });
  await page.goto('/dev/home-dose-save-error');

  const timeline = page.getByRole('region', { name: '오늘의 복약' });
  const detail = timeline.getByRole('group', { name: '아침약 상세' });
  const row = page.locator('article[aria-label*="8월 22일 처방"]').first().locator('[data-episode-row]');

  await row.click();
  await detail.getByRole('button', { name: '먹었어요' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(timeline.locator('[data-medication-completed-summary]')).toHaveCount(0);
  await expect(detail.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(row).toHaveAttribute('aria-pressed', 'true');
});

test('영양제 시간대 전체 완료는 헤더 chip 하나로 요약하고 부분 완료·되돌리기를 유지한다', async ({
  page,
}, testInfo) => {
  await page.clock.setFixedTime(new Date('2026-09-05T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '384-home-supplement-summary-token');
    sessionStorage.setItem('poke.account-principal', '384-home-supplement-summary@example.com');
  });
  await page.goto('/dev/home-empty');
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();

  const morning = page.getByRole('group', { name: '아침 영양제' });
  const headerSummary = morning.locator('[data-supplement-completed-summary]');
  const rowBadges = morning.locator('[data-supplement-completed-badge]');

  await expect(morning.getByRole('button', { name: '오메가3 선택' })).toBeVisible();
  await expect(headerSummary).toHaveCount(0);
  await expect(rowBadges).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('384-supplement-before.png'), fullPage: true });

  await morning.getByRole('button', { name: '오메가3 선택' }).click();
  await expect(headerSummary).toHaveCount(0);
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(headerSummary).toHaveCount(0);
  await expect(rowBadges).toHaveCount(1);

  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(headerSummary).toHaveCount(1);
  await expect(headerSummary).toHaveText('복용 완료');
  await expect(rowBadges).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('384-supplement-after.png'), fullPage: true });

  await morning.getByRole('button', { name: '오메가3 복용 완료' }).click();
  await expect(headerSummary).toHaveCount(1);
  await morning.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect(headerSummary).toHaveCount(0);
  await expect(rowBadges).toHaveCount(1);
});
