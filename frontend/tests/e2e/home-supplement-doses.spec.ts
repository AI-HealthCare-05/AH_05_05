import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
const DATE = '2026-09-05';
type Dose = { supplementId: number; date: string; slot: string; taken: boolean };

async function openHome(page: Page, options: {
  failId?: number;
  failLookup?: boolean;
  at?: string;
  longName?: string;
  initialRecords?: Dose[];
  slotTimeOverrides?: Partial<Record<string, string>>;
} = {}) {
  const requests: Dose[] = [];
  let records: Dose[] = options.initialRecords ?? [];
  let failId = options.failId;
  let failLookup = options.failLookup;
  await page.clock.setFixedTime(new Date(`${DATE}T${options.at ?? '12:00:00'}+09:00`));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'supplement-dose-test');
    if (!sessionStorage.getItem('poke.account-principal')) {
      sessionStorage.setItem('poke.account-principal', 'supplement-dose-a@example.com');
    }
  });
  if (IS_REAL_API) {
    await page.route('**/api/v1/users/me', route => route.fulfill({ json: {
      name: '테스트', maskedName: '테*트', phoneNumber: null, birthDate: null, gender: null,
    } }));
    await page.route('**/api/v1/display/med/nutr/rank', route => route.fulfill({ status: 204 }));
    await page.route('**/api/v1/med/user-suppl-nutr?**', route => route.fulfill({ json: {
      items: [
        { id: 501, name: options.longName ?? '오메가3', slots: ['MORNING', 'EVENING'] },
        { id: 502, name: '종합비타민', slots: ['MORNING'] },
        { id: 503, name: '비타민 D', slots: ['EVENING'] },
      ].map(item => ({
        id: item.id, custom_name: item.name, dose_amount: '1.000', dose_unit: '정',
        start_date: '2026-09-01', end_date: null, status: 'ACTIVE', score: null,
        review_body: null, note: null, created_at: '2026-09-01T09:00:00+09:00', updated_at: null,
        slots: item.slots.map(slot => ({
          slot,
          time: options.slotTimeOverrides?.[slot]
            ?? (slot === 'MORNING' ? '07:30:00' : '18:00:00'),
        })),
        supplement: null,
      })), total: 3, offset: 0, limit: 100, nutrient_standard: null,
    } }));
    await page.route('**/api/v1/med/supplement-doses**', async route => {
      if (route.request().method() === 'GET') {
        if (failLookup) {
          await route.fulfill({ status: 500, json: { detail: 'lookup failure' } });
          return;
        }
        expect(new URL(route.request().url()).searchParams.get('date')).toBe(DATE);
        await route.fulfill({ json: records });
        return;
      }
      expect(route.request().method()).toBe('PUT');
      const payload = route.request().postDataJSON() as Dose;
      requests.push(payload);
      if (payload.supplementId === failId) {
        failId = undefined;
        await route.fulfill({ status: 500, json: { detail: 'save failure' } });
        return;
      }
      records = records.filter(item => !(item.supplementId === payload.supplementId && item.slot === payload.slot));
      if (payload.taken) records.push(payload);
      await route.fulfill({ json: payload });
    });
  }
  await page.goto('/dev/home-empty');
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  return {
    requests,
    recoverLookup: () => { failLookup = false; },
    failNextSave: (id: number) => { failId = id; },
    morning: page.getByRole('group', { name: '아침 영양제' }),
  };
}

test('영양제는 현재 이전의 가장 가까운 시간대 하나만 보이고 제목을 반복하지 않는다', async ({ page }) => {
  const { morning } = await openHome(page, { at: '06:00:00' });
  const panel = page.getByRole('tabpanel', { name: '오늘의 영양제' });
  await expect(panel.getByRole('heading', { name: '오늘의 영양제', exact: true })).toHaveCount(0);
  await expect(morning).toBeVisible();
  await expect(panel.getByRole('group', { name: '저녁 영양제' })).toHaveCount(0);

  await page.clock.setFixedTime(new Date(`${DATE}T19:30:00+09:00`));
  await page.reload();
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  await expect(panel.getByRole('group', { name: '아침 영양제' })).toHaveCount(0);
  await expect(panel.getByRole('group', { name: '저녁 영양제' })).toBeVisible();
});

test('영양제 회차는 API 시간순으로 고르고 누락 시간은 기본 시간으로 계산한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { morning } = await openHome(page, {
    at: '12:00:00',
    slotTimeOverrides: { MORNING: '10:00:00', EVENING: '' },
  });
  const panel = page.getByRole('tabpanel', { name: '오늘의 영양제' });
  await expect(morning).toContainText('10:00');
  await expect(panel.getByRole('group', { name: '저녁 영양제' })).toHaveCount(0);

  await page.reload();
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  await expect(morning).toBeVisible();
});

test('영양제 카드는 선택할 때 나타나는 선택 원과 compact 2열 복용 액션을 제공한다', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { morning } = await openHome(page);

  await expect(morning.getByText('개별 선택', { exact: true })).toHaveCount(0);
  const omega = morning.getByRole('button', { name: '오메가3 선택' });
  await expect(omega).toHaveAttribute('aria-pressed', 'false');
  await expect(omega.locator('[data-dose-selection]')).toHaveCSS('width', '0px');

  const indicatorBox = await omega.locator('[data-supplement-selection-indicator]').boundingBox();
  const rowBox = await omega.boundingBox();
  const cardBox = await morning.locator('..').boundingBox();
  expect(indicatorBox).not.toBeNull();
  expect(indicatorBox!.width).toBe(24);
  expect(indicatorBox!.height).toBe(24);
  expect(rowBox).not.toBeNull();
  expect(rowBox!.height).toBeGreaterThanOrEqual(44);
  expect(cardBox).not.toBeNull();
  expect(cardBox!.height).toBeLessThanOrEqual(220);

  const selectedAction = morning.getByRole('button', { name: '0개 먹었어요' });
  const allAction = morning.getByRole('button', { name: '다 먹었어요' });
  await expect(selectedAction).toBeDisabled();
  const [selectedActionBox, allActionBox] = await Promise.all([
    selectedAction.boundingBox(),
    allAction.boundingBox(),
  ]);
  expect(selectedActionBox).not.toBeNull();
  expect(allActionBox).not.toBeNull();
  expect(Math.abs(selectedActionBox!.y - allActionBox!.y)).toBeLessThanOrEqual(1);
  expect(Math.abs(selectedActionBox!.width - allActionBox!.width)).toBeLessThanOrEqual(2);
  expect(selectedActionBox!.height).toBeGreaterThanOrEqual(44);
  expect(allActionBox!.height).toBeGreaterThanOrEqual(44);
  expect(selectedActionBox!.y).toBeGreaterThan(rowBox!.y + rowBox!.height);

  await omega.click();
  await expect(omega).toHaveAttribute('aria-pressed', 'true');
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(1);
  const completedOmega = morning.getByRole('button', { name: '오메가3 복용 완료' });
  const completedBadge = completedOmega.locator('[data-supplement-completed-badge]');
  const indicator = completedOmega.locator('[data-supplement-selection-indicator]');
  await expect(completedOmega).toBeVisible();
  await expect(completedOmega.locator('[data-dose-selection]')).toHaveCSS('width', '0px');
  await expect(completedBadge).toBeVisible();
  await expect(completedBadge).toHaveAttribute('aria-hidden', 'true');
  await expect(completedBadge).toHaveText('복용 완료');
  const badgeBox = (await completedBadge.boundingBox())!;
  const nameBox = (await completedOmega.getByText('오메가3', { exact: true }).boundingBox())!;
  expect(badgeBox.y + badgeBox.height).toBeLessThanOrEqual(nameBox.y);
  expect(Math.abs(badgeBox.x - nameBox.x)).toBeLessThanOrEqual(1);
  await expect(completedOmega).toHaveAttribute('aria-pressed', 'false');
  await expect(indicator).toHaveClass(/bg-card/);
  await expect(indicator.locator('svg')).toHaveCount(0);
  await expect(morning.getByRole('button', { name: '0개 먹었어요' })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath('353-home-supplement-completion-390.png'), fullPage: true });

  await completedOmega.click();
  await expect(completedOmega).toHaveAttribute('aria-pressed', 'true');
  await expect(indicator).toHaveClass(/bg-primary/);
  await expect(indicator.locator('svg')).toHaveCount(1);
  await expect(morning.getByRole('button', { name: '1개 되돌리기' })).toBeEnabled();
  await expect(completedBadge).toHaveText('복용 완료');
});

test('긴 영양제 이름은 모든 화면 폭에서 완료 배지와 선택 원을 밀지 않고 전체가 보인다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  test.setTimeout(120_000);
  const longName = `활력충전종합영양제${'SUPPLEMENT'.repeat(18)}캡슐`;
  const record = { supplementId: 501, date: DATE, slot: 'morning', taken: true };
  const { morning } = await openHome(page, { longName, initialRecords: [record] });

  for (const width of [320, 390, 430, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.reload();
    await page.getByRole('tab', { name: '오늘의 영양제' }).click();
    const row = morning.getByRole('button', { name: `${longName} 복용 완료` });
    const name = row.getByText(longName, { exact: true });
    const badge = row.locator('[data-supplement-completed-badge]');
    const glyph = row.locator('[data-supplement-selection-indicator]');
    const [rowBox, nameBox, badgeBox, glyphBox] = await Promise.all([
      row.boundingBox(), name.boundingBox(), badge.boundingBox(), glyph.boundingBox(),
    ]);

    expect(rowBox).not.toBeNull();
    expect(nameBox).not.toBeNull();
    expect(badgeBox).not.toBeNull();
    expect(glyphBox).not.toBeNull();
    expect(await name.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect(badgeBox!.y + badgeBox!.height).toBeLessThanOrEqual(nameBox!.y);
    expect(Math.abs(badgeBox!.x - nameBox!.x)).toBeLessThanOrEqual(1);
    expect(glyphBox!.width).toBe(24);
    expect(badgeBox!.x + badgeBox!.width).toBeLessThanOrEqual(rowBox!.x + rowBox!.width + 1);
    expect(await morning.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);

    await row.click();
    await expect(row).toHaveAttribute('aria-pressed', 'true');
    await row.click();
  }
});

test('일부 영양제만 기록하면 새로고침 뒤 유지되고 완료 항목을 선택해 되돌린다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await morning.getByRole('button', { name: '오메가3 선택' }).click();
  await expect(page).toHaveURL(/\/dev\/home-empty$/);
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(1);
  if (IS_REAL_API) expect(requests).toEqual([{ supplementId: 501, date: DATE, slot: 'morning', taken: true }]);
  await page.reload();
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(1);
  await morning.getByRole('button', { name: '오메가3 복용 완료' }).click();
  await morning.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  if (IS_REAL_API) expect(requests.at(-1)).toEqual({ supplementId: 501, date: DATE, slot: 'morning', taken: false });
});

test('전체 복용은 해당 시간대 미완료 제품만 기록하고 다른 시간대는 유지한다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(1);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  await expect(morning.getByRole('button', { name: '다 먹었어요' })).toBeDisabled();
  await expect(page.getByRole('group', { name: '저녁 영양제' }).locator('[data-supplement-completed-badge]')).toHaveCount(0);
  if (IS_REAL_API) expect(requests).toEqual([
    { supplementId: 501, date: DATE, slot: 'morning', taken: true },
    { supplementId: 502, date: DATE, slot: 'morning', taken: true },
  ]);
});

test('실 API 일괄 복용 부분 실패는 성공한 제품을 다시 저장하지 않고 실패만 재시도한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { morning, requests } = await openHome(page, { failId: 502 });
  await expect(morning).toContainText('07:30');
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.getByRole('alert')).toBeVisible();
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(1);
  const saved = morning.getByRole('button', { name: '오메가3 복용 완료' });
  const failed = morning.getByRole('button', { name: '종합비타민 선택' });
  await expect(saved).toHaveAttribute('aria-pressed', 'false');
  await expect(saved.locator('[data-supplement-selection-indicator] svg')).toHaveCount(0);
  await expect(failed).toHaveAttribute('aria-pressed', 'true');
  await expect(failed.locator('[data-supplement-selection-indicator] svg')).toHaveCount(1);
  await morning.getByRole('button', { name: '다시 시도' }).click();
  await expect(morning.getByRole('alert')).toHaveCount(0);
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(1);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  expect(requests.map(item => item.supplementId)).toEqual([501, 502, 502]);
});

test('복용 기록 조회 실패 중에는 저장할 수 없고 조회를 재시도한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { morning, requests, recoverLookup } = await openHome(page, { failLookup: true });
  const panel = page.getByRole('tabpanel', { name: '오늘의 영양제' });
  await expect(panel.getByRole('alert')).toBeVisible();
  await expect(panel.getByRole('button', { name: '다 먹었어요' })).toHaveCount(0);
  expect(requests).toHaveLength(0);
  recoverLookup();
  await panel.getByRole('button', { name: '다시 시도' }).click();
  await expect(morning.getByRole('button', { name: '다 먹었어요' })).toBeEnabled();
});

test('목업 영양제 복용 기록은 로그인 계정별로 분리한다', async ({ page }) => {
  test.skip(IS_REAL_API, '목업 저장소 계정 격리 검증');
  const { morning } = await openHome(page);
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(1);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  await page.evaluate(() => sessionStorage.setItem('poke.account-principal', 'supplement-dose-b@example.com'));
  await page.reload();
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  await expect(morning.getByRole('button', { name: '다 먹었어요' })).toBeEnabled();
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
});

test('완료와 미완료를 섞어 선택하지 않으며 선택을 비우면 전체 복용으로 돌아간다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  const omega = morning.getByRole('button', { name: '오메가3 선택' });
  const multi = morning.getByRole('button', { name: '종합비타민 선택' });
  await omega.click();
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  const completedOmega = morning.getByRole('button', { name: '오메가3 복용 완료' });
  await completedOmega.click();
  await expect(morning.getByRole('button', { name: '1개 되돌리기' })).toBeVisible();
  await multi.click();
  await expect(completedOmega).toHaveAttribute('aria-pressed', 'false');
  await expect(morning.getByRole('button', { name: '1개 먹었어요' })).toBeVisible();
  await multi.click();
  await expect(morning.getByRole('button', { name: '0개 먹었어요' })).toBeDisabled();
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(1);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  if (IS_REAL_API) expect(requests.map(item => item.supplementId)).toEqual([501, 502]);
});

test('되돌리기 실패는 완료 상태를 유지하고 같은 false 요청으로 재시도한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { morning, requests, failNextSave } = await openHome(page);
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(1);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  failNextSave(501);
  await morning.getByRole('button', { name: '오메가3 복용 완료' }).click();
  await morning.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect(morning.getByRole('alert')).toBeVisible();
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(1);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(0);
  await morning.getByRole('button', { name: '다시 시도' }).click();
  await expect(morning.locator('[data-supplement-completed-summary]')).toHaveCount(0);
  await expect(morning.locator('[data-supplement-completed-badge]')).toHaveCount(1);
  expect(requests.slice(-2)).toEqual([
    { supplementId: 501, date: DATE, slot: 'morning', taken: false },
    { supplementId: 501, date: DATE, slot: 'morning', taken: false },
  ]);
});

test('홈 영양제 살펴보기는 둘러보기 탭으로 진입한다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await expect(morning.getByRole('button', { name: '종합비타민 선택' })).toBeVisible();
  await page.getByRole('button', { name: '영양제 살펴보기' }).click();
  await expect(page).toHaveURL(/\/supplements\?tab=browse$/);
  await expect(page.getByRole('button', { name: '둘러보기' })).toHaveAttribute('aria-pressed', 'true');
  expect(requests).toHaveLength(0);
});
