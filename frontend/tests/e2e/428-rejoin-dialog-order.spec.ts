import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const challenge = {
  id: 101, name: '걷기 챌린지', phrase: '매일 30분 걷기', description: '매일 실천해요.',
  challenge_type_code: 'OFFICIAL', period_code: 'D14', duration_days: 14,
  check_type_code: 'SELF', frequency_code: 'DAILY', reward_badge: null,
  recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00',
  can_join: true, participation_id: 501,
};
function attempt(status = 'CANCELLED') {
  return {
    id: 501, user_id: 7, challenge_id: 101, challenge_name: challenge.name, status,
    joined_at: '2026-09-08T10:00:00+09:00', started_at: '2026-09-08T00:00:00+09:00', end_at: '2026-09-22T00:00:00+09:00',
    target_count: 14, completed_count: status === 'COMPLETED' ? 14 : 3, progress_rate: status === 'COMPLETED' ? '100.00' : '21.43',
    completed_at: status === 'COMPLETED' ? '2026-09-12T10:00:00+09:00' : null,
    cancelled_at: status === 'CANCELLED' ? '2026-09-10T10:00:00+09:00' : null,
    progress_periods: [], challenge, today: '2026-09-12', today_verification: null, can_verify: false, verified_dates: [],
  };
}
async function prepare(page: Page, entry: 'catalog' | 'participation', status = 'CANCELLED', openDialog = true) {
  await page.clock.setFixedTime(new Date('2026-09-12T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'rejoin-fixture');
    sessionStorage.setItem('poke.account-principal', 'rejoin-fixture@example.com');
  });
  await page.route(url => /^\/(api|media)(\/|$)/.test(url.pathname), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: challenge }));
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: attempt(status) }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.goto(entry === 'catalog' ? '/challenges/official/101' : '/challenges/participations/501');
  if (openDialog) await page.getByRole('button', { name: '다시 참여하기', exact: true }).click();
  return page.getByRole('dialog', { name: '챌린지에 다시 참여할까요?' });
}
test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));
test('completed participation retains existing no-rejoin policy', async ({ page }) => {
  await prepare(page, 'participation', 'COMPLETED', false);
  await expect(page.getByRole('heading', { name: '걷기 챌린지', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toHaveCount(0);
});
for (const entry of ['catalog', 'participation'] as const) {
  for (const width of [320, 390, 1280]) {
    test(`rejoin order ${entry} ${width}px`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 });
      let writes = 0;
      const dialog = await prepare(page, entry);
      await page.route('**/api/v1/user/challenges/101/join', route => { writes++; return route.fulfill({ status: 500, json: {} }); });
      const primary = dialog.getByRole('button', { name: '다시 참여하기', exact: true });
      const secondary = dialog.getByRole('button', { name: '돌아가기', exact: true });
      const [first, second] = await Promise.all([primary.boundingBox(), secondary.boundingBox()]);
      expect(first!.y + first!.height).toBeLessThanOrEqual(second!.y);
      expect(first!.height).toBeGreaterThanOrEqual(44);
      expect(second!.height).toBeGreaterThanOrEqual(44);
      await primary.focus(); await page.keyboard.press('Tab'); await expect(secondary).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await dialog.getByRole('heading').click();
      await page.locator('img').evaluateAll(async imgs => { await Promise.all(imgs.filter(img => img.getBoundingClientRect().width > 0).map(img => img.decode().catch(() => {}))); });
      await dialog.screenshot({ path: info.outputPath(`428-rejoin-${entry}-${width}.png`) });
      await secondary.click(); await expect(dialog).toHaveCount(0);
      expect(writes).toBe(0);
    });
  }
  test(`rejoin pending prevents duplicate and close from ${entry}`, async ({ page }) => {
    const dialog = await prepare(page, entry);
    let writes = 0;
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/user/challenges/101/join', async route => {
      writes++; await gate; await route.fulfill({ status: 503, json: { code: 'TEMPORARY_ERROR', message: '잠시 후 다시 시도해주세요' } });
    });
    await dialog.getByRole('button', { name: '다시 참여하기', exact: true }).click();
    const pending = dialog.getByRole('button', { name: '참여 중', exact: true });
    await expect(pending).toBeDisabled();
    await expect(dialog.getByRole('button', { name: '돌아가기', exact: true })).toBeDisabled();
    await pending.evaluate((element: HTMLButtonElement) => element.click());
    await page.keyboard.press('Escape'); await expect(dialog).toBeVisible();
    expect(writes).toBe(1);
    release();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toBeEnabled();
  });
}
