import { expect, test, type Locator, type Route } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(60_000);

const LONG_NAME = `복합성분서방정${'MEDICATION'.repeat(14)}정`;
const LONG_ALIAS = `퇴원후집중관리${'PRESCRIPTION'.repeat(8)}처방`;
const active = {
  recordId: 391,
  alias: LONG_ALIAS,
  documentImageUrl: '/api/v1/ocr/jobs/391/image',
  start: { date: '2026-09-05', slot: 'morning' },
  endDate: '2026-09-14', daysRemaining: 5, isFinished: false,
  mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
  medications: [
    { medicationId: 3910, name: LONG_NAME, dose: '125/500mg 2정', days: 10,
      daysRemaining: 5, slots: ['morning', 'lunch', 'evening', 'bedtime'], asNeeded: false, untilComplete: true },
    { medicationId: 3911, name: '필요시복용약', dose: '650mg 1캡슐', days: 10,
      daysRemaining: null, slots: [], asNeeded: true },
  ],
};

async function json(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function expectUnclipped(text: Locator) {
  await expect(text).toBeVisible();
  const result = await text.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      fits: element.scrollWidth <= element.clientWidth + 1 && element.scrollHeight <= element.clientHeight + 1,
      ellipsis: style.textOverflow === 'ellipsis',
      nowrap: style.whiteSpace === 'nowrap',
    };
  });
  expect(result).toEqual({ fits: true, ellipsis: false, nowrap: false });
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-391-token');
    sessionStorage.setItem('poke.account-principal', 'feature-391@example.com');
  });
  await page.route('**/api/v1/**', (route) => json(route, {}));
  await page.route('**/api/v1/med/medication/schedule/391', (route) => json(route, {
    start: active.start,
    mealTimes: active.mealTimes,
    medications: [{
      medicationId: 3910, name: LONG_NAME, dose: '125/500mg 2정',
      timesPerDay: 4, timing: '식후', slots: ['morning', 'lunch', 'evening', 'bedtime'],
    }],
  }));
  await page.route('**/api/v1/medications', (route) => json(route, [active, {
    ...active, recordId: 392, alias: '지난 처방', isFinished: true, daysRemaining: 0,
    start: { date: '2026-08-01', slot: 'morning' }, endDate: '2026-08-10',
  }]));
});

test('접힌 처방의 화살표는 아래를 가리킨다', async ({ page }) => {
  await page.goto('/medications');
  const toggle = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
  const direction = await toggle.locator('svg path').evaluate((path) => {
    const shape = path as SVGPathElement;
    const matrix = shape.getScreenCTM()!;
    const start = shape.getPointAtLength(0).matrixTransform(matrix);
    const tip = shape.getPointAtLength(shape.getTotalLength() / 2).matrixTransform(matrix);
    const end = shape.getPointAtLength(shape.getTotalLength()).matrixTransform(matrix);
    return Math.abs(start.y - end.y) < 1 && tip.y > start.y;
  });
  expect(direction).toBe(true);
});

for (const width of [320, 390, 1280]) {
  test(`시간대 칩과 연필은 같은 행에 있고 펼침 화살표가 아래와 위를 가리킨다 (${width})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/medications');
    const toggle = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
    const card = page.locator('article').filter({ has: toggle });
    const edit = card.getByRole('button', { name: '처방 수정 · 2026년 9월 5일', exact: true });
    const morning = card.locator(':scope > div:first-child').getByText('아침', { exact: true });
    const expectAlignedEdit = async () => {
      const chipBox = await morning.boundingBox();
      const editBox = await edit.boundingBox();
      expect(chipBox).not.toBeNull();
      expect(editBox).not.toBeNull();
      expect(editBox!.y).toBeLessThan(chipBox!.y + chipBox!.height);
      expect(editBox!.y + editBox!.height).toBeGreaterThan(chipBox!.y);
      for (const label of ['아침', '점심', '저녁', '자기전']) {
        const chip = card.locator(':scope > div:first-child').getByText(label, { exact: true });
        await expectUnclipped(chip);
        const box = await chip.boundingBox();
        expect(box!.x + box!.width).toBeLessThanOrEqual(editBox!.x);
      }
    };
    const chevronDirection = () => toggle.locator('svg path').evaluate((path) => {
      const shape = path as SVGPathElement;
      const matrix = shape.getScreenCTM()!;
      const start = shape.getPointAtLength(0).matrixTransform(matrix);
      const tip = shape.getPointAtLength(shape.getTotalLength() / 2).matrixTransform(matrix);
      const end = shape.getPointAtLength(shape.getTotalLength()).matrixTransform(matrix);
      if (Math.abs(start.y - end.y) > 1) return 'sideways';
      return tip.y > start.y ? 'down' : 'up';
    });
    await expectAlignedEdit();
    await expect.poll(chevronDirection).toBe('down');
    await page.screenshot({ path: testInfo.outputPath(`controls-collapsed-${width}.png`), fullPage: true });
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expectAlignedEdit();
    await expect.poll(chevronDirection).toBe('up');
    await page.screenshot({ path: testInfo.outputPath(`controls-expanded-${width}.png`), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`요약은 약 이름을 숨기고 펼친 긴 이름은 줄바꿈한다 (${width})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/medications');
    const toggle = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
    const card = page.locator('article').filter({ has: toggle });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(card.getByText(LONG_NAME, { exact: false })).toHaveCount(0);
    await expect(card.getByText('5일 남음', { exact: true })).toBeVisible();
    await expect(card.getByText('2026년 9월 5일 ~ 14일', { exact: true })).toBeVisible();
    await expect(card.getByText(/약 2개|08:00|13:00|19:00/)).toHaveCount(0);
    await expectUnclipped(card.getByText(LONG_ALIAS, { exact: true }));
    const colors = [];
    for (const slot of ['아침', '점심', '저녁']) {
      const chip = card.getByText(slot, { exact: true });
      await expect(chip).toBeVisible();
      colors.push(await chip.evaluate((element) => getComputedStyle(element).backgroundColor));
    }
    expect(new Set(colors).size).toBe(3);
    await page.screenshot({ path: testInfo.outputPath(`summary-${width}.png`), fullPage: true });
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const details = card.getByRole('region', { name: '2026년 9월 5일 처방 상세' });
    await expectUnclipped(details.getByText(LONG_NAME, { exact: false }));
    await expect(details.getByText('필요할 때만 · 알림 없음')).toBeVisible();
    await expect(details.getByText('끝까지 복용')).toBeVisible();
    await expect(details.getByText('자기전', { exact: true })).toBeVisible();
    await expect(details.getByRole('button', { name: /복용 시간 수정/ })).toHaveCount(0);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`expanded-${width}.png`), fullPage: true });
    await toggle.focus();
    await page.keyboard.press('Space');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(details).toHaveCount(0);
  });
}

test('연필만 기존 편집창을 열고 선택 모드는 편집과 펼침 없이 삭제 대상을 고른다', async ({ page }) => {
  await page.goto('/medications');
  const toggle = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
  const card = page.locator('article').filter({ has: toggle });
  const edit = card.getByRole('button', { name: '처방 수정 · 2026년 9월 5일', exact: true });
  await expect(edit).toBeVisible();
  await edit.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: '처방 편집' });
  await expect(dialog.getByRole('textbox', { name: '복약 별칭', exact: true })).toHaveValue(LONG_ALIAS);
  await expect(dialog.getByRole('button', { name: `${LONG_NAME} 아침약`, exact: true })).toHaveAttribute('aria-pressed', 'true');
  await dialog.getByRole('button', { name: '닫기' }).click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(edit).toHaveCount(0);
  await toggle.click();
  await expect(page.getByRole('checkbox', { name: '2026년 9월 5일 처방 선택' })).toBeChecked();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: '선택한 처방 삭제', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('연필로 수정한 별칭과 시간대를 기존 API에 저장하고 요약에 반영한다', async ({ page }) => {
  const saved: Array<{ method: string; path: string; body: unknown }> = [];
  await page.route('**/api/v1/med/**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fallback();
      return;
    }
    saved.push({ method: route.request().method(), path: new URL(route.request().url()).pathname,
      body: route.request().postDataJSON() });
    await json(route, { saved: true });
  });
  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 수정 · 2026년 9월 5일', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '처방 편집' });
  await dialog.getByRole('textbox', { name: '복약 별칭', exact: true }).fill('변경한 별칭');
  await dialog.getByRole('button', { name: `${LONG_NAME} 점심약`, exact: true }).click();
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('변경한 별칭', { exact: true })).toBeVisible();
  expect(saved).toEqual([
    { method: 'PUT', path: '/api/v1/med/medication/schedule/391', body: {
      start: { date: '2026-09-05', slot: 'morning' },
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [{ medicationId: 3910, slots: ['morning', 'evening', 'bedtime'] }],
    } },
    { method: 'PATCH', path: '/api/v1/med/episodes/391/alias', body: { alias: '변경한 별칭' } },
  ]);
  const card = page.locator('article').filter({ hasText: '변경한 별칭' });
  await expect(card.getByText('점심', { exact: true })).toHaveCount(0);
  await expect(card.getByRole('button', { expanded: false })).toBeVisible();
});

test('완료 처방은 펼쳐 읽을 수 있지만 수정하지 못한다', async ({ page }) => {
  await page.goto('/medications');
  const toggle = page.getByRole('button', { name: /2026년 8월 1일 처방.*복용 완료/ });
  const card = page.locator('article').filter({ has: toggle });
  await expect(card.getByText(/일 남음/)).toHaveCount(0);
  await toggle.click();
  await expect(card.getByRole('region')).toContainText(LONG_NAME);
  await expect(card.getByRole('button', { name: /처방 수정|복용 시간 수정/ })).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
