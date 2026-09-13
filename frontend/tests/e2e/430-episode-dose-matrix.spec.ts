import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

async function openPrescriptions(page: Page, finished = false) {
  await page.clock.setFixedTime(new Date('2026-09-12T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'fixture-430-token');
    sessionStorage.setItem('poke.account-principal', 'fixture-430@example.com');
  });
  await page.route(url => /^\/(api|media)(\/|$)/.test(url.pathname), route => route.fulfill({ json: {} }));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, route => route.fulfill({ json: [{
    recordId: 430, alias: '해맑은소아청소년과의원', documentImageUrl: null,
    start: { date: '2026-09-10', slot: 'morning' }, endDate: '2026-09-15', daysRemaining: 4, isFinished: finished,
    mealTimes: { morning: '09:30', lunch: '13:00', evening: '20:00', bedtime: '22:00' },
    medications: [
      { medicationId: 1, name: '세프디니르건조시럽', dose: '5mL', days: 6, daysRemaining: 4, slots: ['morning', 'evening'], asNeeded: false },
      { medicationId: 2, name: '암브록솔시럽', dose: '5mL', days: 6, daysRemaining: 4, slots: ['morning', 'lunch', 'evening'], asNeeded: false },
      { medicationId: 3, name: '매우긴약이름의프로바이오틱스캡슐500mg', dose: '500mg', days: 6, daysRemaining: 4, slots: ['bedtime'], asNeeded: false, untilComplete: true },
      { medicationId: 4, name: '필요시약', dose: '1정', days: 6, daysRemaining: 4, slots: ['morning'], asNeeded: true },
      { medicationId: 5, name: '시간미정약', dose: '1정', days: 6, daysRemaining: 4, slots: [], asNeeded: false },
    ],
  }] }));
  await page.goto('/medications');
  return page.locator('article').filter({ hasText: '해맑은소아청소년과의원' });
}

test('완료된 처방도 복용 표를 확인할 수 있고 편집은 숨긴다', async ({ page }) => {
  const card = await openPrescriptions(page, true);
  await expect(card.getByText('복용 완료', { exact: true })).toBeVisible();
  await expect(card.getByRole('button', { name: /처방 수정/ })).toHaveCount(0);
  await card.getByRole('button', { expanded: false }).click();
  await expect(card.getByRole('table')).toBeVisible();
  await expect(card.getByRole('rowheader', { name: '세프디니르건조시럽', exact: true })).toBeVisible();
});

test('선택 모드에서는 편집 대신 처방 선택을 토글하고 펼친 표는 유지한다', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const card = await openPrescriptions(page);
  await card.getByRole('button', { expanded: false }).click();
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await expect(card.getByRole('button', { name: /처방 수정/ })).toHaveCount(0);
  await card.getByRole('button', { expanded: true }).click();
  await expect(card.getByRole('checkbox')).toBeChecked();
  await expect(card.getByRole('table')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(card.getByRole('button', { name: /처방 수정/ })).toBeVisible();
});

test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));
for (const width of [320, 375, 390, 1280]) {
  test(`처방 헤더 두 줄 정렬과 고정 복용 열 유지 ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    const card = await openPrescriptions(page);
    const edit = card.getByRole('button', { name: /처방 수정/ });
    const toggle = card.getByRole('button', { name: /2026년 9월 10일 처방 · 약 5개/ });
    await expect(edit).toBeVisible();
    const [status, pencil, title, chevron, target] = await Promise.all([
      card.getByText('4일 남음').boundingBox(), edit.locator('svg').boundingBox(),
      card.locator('strong').boundingBox(), toggle.locator('svg').boundingBox(), edit.boundingBox(),
    ]);
    expect(Math.abs(status!.y + status!.height / 2 - pencil!.y - pencil!.height / 2)).toBeLessThanOrEqual(2);
    expect(Math.abs(title!.y + title!.height / 2 - chevron!.y - chevron!.height / 2)).toBeLessThanOrEqual(2);
    expect(target!.height).toBeGreaterThanOrEqual(44); expect(target!.width).toBeGreaterThanOrEqual(44);
    await expect(card.getByText('아침', { exact: true })).toHaveCount(0);
    await card.screenshot({ path: info.outputPath(`430-dose-header-${width}.png`) });
    await toggle.focus(); await page.keyboard.press('Enter');
    const table = card.getByRole('table');
    await expect(table.getByRole('columnheader')).toHaveText(['복용약', '아침', '점심', '저녁', '자기전']);
    const rows = table.locator('tbody tr');
    const expected = [['아침', '저녁'], ['아침', '점심', '저녁'], ['자기전'], [], []];
    const expectedCells = [['아침', '', '저녁', ''], ['아침', '점심', '저녁', ''], ['', '', '', '자기전'], ['', '', '', ''], ['', '', '', '']];
    for (let index = 0; index < expected.length; index++) {
      await expect(rows.nth(index).getByRole('img')).toHaveCount(expected[index].length);
      for (const label of expected[index]) await expect(rows.nth(index).getByRole('img', { name: label, exact: true })).toBeVisible();
      await expect(rows.nth(index).getByRole('cell')).toHaveCount(4);
      expect(await rows.nth(index).getByRole('cell').evaluateAll(cells => cells.map(cell => cell.querySelector('[role="img"]')?.getAttribute('aria-label') ?? ''))).toEqual(expectedCells[index]);
    }
    await expect(table.getByText('필요할 때만 · 알림 없음')).toBeVisible();
    await expect(table.getByText('끝까지 복용')).toBeVisible();
    await expect(table.getByText('5mL')).toHaveCount(0);
    await expect(table.getByText(/09:30|20:00/)).toHaveCount(0);
    const first = await rows.nth(0).getByRole('cell').evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().x));
    const last = await rows.nth(4).getByRole('cell').evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().x));
    expect(last).toEqual(first);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await table.getByRole('columnheader', { name: '복용약', exact: true }).click();
    await page.locator('img').evaluateAll(async imgs => { await Promise.all(imgs.map(img => img.decode().catch(() => {}))); });
    await card.screenshot({ path: info.outputPath(`430-dose-matrix-${width}.png`) });
    await toggle.focus(); await page.keyboard.press('Space'); await expect(table).toHaveCount(0);
    await edit.click(); await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }).click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
}
