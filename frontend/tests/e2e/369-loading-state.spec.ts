import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

for (const screen of [
  { name: '홈', path: '/home', label: '복약 정보 불러오는 중', ready: '' },
  { name: '복용약', path: '/medications', label: '복용약 불러오는 중', ready: '이 기간에 등록한 처방이 없어요' },
]) {
  test(`${screen.name}: 느린 첫 조회는 큰 빈 상자 대신 작은 상태 안내를 보여준다`, async ({ page }, testInfo) => {
    test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', '369-loading-token');
      sessionStorage.setItem('poke.account-principal', '369-loading@example.com');
    });
    await page.route('**/api/v1/**', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } }));
    await page.route('**/api/v1/medications/doses?**', route => route.fulfill({ json: [] }));
    let release = () => {};
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route(/\/api\/v1\/medications(?:\?.*)?$/, async route => {
      await gate;
      await route.fulfill({ json: { episodes: [] } });
    });
    const request = page.waitForRequest(/\/api\/v1\/medications(?:\?.*)?$/);
    await page.goto(screen.path);
    await request;
    const status = page.getByRole('status', { name: screen.label, exact: true });
    try {
      await expect(status).toBeVisible();
      await expect(status).toContainText(/불러오/);
      expect((await status.boundingBox())!.height).toBeLessThanOrEqual(64);
      await page.screenshot({ path: testInfo.outputPath('slow-loading.png'), fullPage: true, animations: 'disabled' });
    } finally {
      release();
    }
    await expect(status).toHaveCount(0);
    if (screen.path === '/home') {
      await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
    } else {
      await expect(page.getByText(screen.ready, { exact: true })).toBeVisible();
    }
    await page.screenshot({ path: testInfo.outputPath('loaded.png'), fullPage: true, animations: 'disabled' });
  });
}

test('홈 복약 첫 로딩은 아래 챌린지를 한 프레임에 밀지 않고 높이를 부드럽게 바꾼다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '369-loading-token');
    sessionStorage.setItem('poke.account-principal', '369-loading@example.com');
  });
  await page.route('**/api/v1/**', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } }));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, async route => {
    await gate;
    await route.fulfill({ json: { episodes: [] } });
  });
  await page.goto('/home');
  await expect(page.getByRole('status', { name: '복약 정보 불러오는 중', exact: true })).toBeVisible();
  const samples = page.evaluate(() => new Promise<number[]>(resolve => {
    const positions: number[] = [];
    const started = performance.now();
    function frame() {
      positions.push(document.querySelector('.rx-home-challenges')!.getBoundingClientRect().top);
      if (performance.now() - started > 900) resolve(positions);
      else requestAnimationFrame(frame);
    }
    frame();
  }));
  release();
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
  const values = await samples;
  const first = values[0], last = values.at(-1)!;
  expect(last - first).toBeGreaterThan(50);
  expect(values.filter(value => value > first + 5 && value < last - 5).length).toBeGreaterThan(1);
});
