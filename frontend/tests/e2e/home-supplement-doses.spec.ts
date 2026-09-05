import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
const DATE = '2026-09-05';
type Dose = { supplementId: number; date: string; slot: string; taken: boolean };

async function openHome(page: Page, options: { failId?: number; failLookup?: boolean } = {}) {
  const requests: Dose[] = [];
  let records: Dose[] = [];
  let failId = options.failId;
  let failLookup = options.failLookup;
  let removedRegistrationId: number | undefined;
  await page.clock.setFixedTime(new Date(`${DATE}T12:00:00+09:00`));
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
        { id: 501, name: '오메가3', slots: ['MORNING', 'EVENING'] },
        { id: 502, name: '종합비타민', slots: ['MORNING'] },
        { id: 503, name: '비타민 D', slots: ['EVENING'] },
      ].filter(item => item.id !== removedRegistrationId).map(item => ({
        id: item.id, custom_name: item.name, dose_amount: '1.000', dose_unit: '정',
        start_date: '2026-09-01', end_date: null, status: 'ACTIVE', score: null,
        review_body: null, note: null, created_at: '2026-09-01T09:00:00+09:00', updated_at: null,
        slots: item.slots.map(slot => ({ slot, time: slot === 'MORNING' ? '07:30:00' : '18:00:00' })),
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
    removeRegistration: (id: number) => { removedRegistrationId = id; },
    morning: page.getByRole('group', { name: '아침 영양제' }),
  };
}

test('일부 영양제만 기록하면 새로고침 뒤 유지되고 완료 항목을 선택해 되돌린다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await morning.getByRole('button', { name: '개별 선택' }).click();
  await expect(morning.getByRole('button', { name: '오메가3 관리' })).toHaveCount(0);
  await morning.getByRole('checkbox', { name: '오메가3 선택' }).check();
  await expect(page).toHaveURL(/\/dev\/home-empty$/);
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(morning.getByRole('checkbox', { name: '오메가3 선택' })).toHaveCount(0);
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(1);
  if (IS_REAL_API) expect(requests).toEqual([{ supplementId: 501, date: DATE, slot: 'morning', taken: true }]);
  await page.reload();
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(1);
  await morning.getByRole('button', { name: '개별 선택' }).click();
  await morning.getByRole('checkbox', { name: '오메가3 선택' }).check();
  await morning.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(0);
  if (IS_REAL_API) expect(requests.at(-1)).toEqual({ supplementId: 501, date: DATE, slot: 'morning', taken: false });
});

test('전체 복용은 해당 시간대 미완료 제품만 기록하고 다른 시간대는 유지한다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(2);
  await expect(morning.getByRole('button', { name: '다 먹었어요' })).toBeDisabled();
  await expect(page.getByRole('group', { name: '저녁 영양제' }).getByText('복용 완료', { exact: true })).toHaveCount(0);
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
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(1);
  await morning.getByRole('button', { name: '다시 시도' }).click();
  await expect(morning.getByRole('alert')).toHaveCount(0);
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(2);
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
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(2);
  await page.evaluate(() => sessionStorage.setItem('poke.account-principal', 'supplement-dose-b@example.com'));
  await page.reload();
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  await expect(morning.getByRole('button', { name: '다 먹었어요' })).toBeEnabled();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(0);
});

test('완료와 미완료를 섞어 선택하지 않으며 선택을 비우면 전체 복용으로 돌아간다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await morning.getByRole('button', { name: '개별 선택' }).click();
  await morning.getByRole('checkbox', { name: '오메가3 선택' }).check();
  await morning.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(morning.getByRole('button', { name: '개별 선택' })).toBeVisible();
  await morning.getByRole('button', { name: '개별 선택' }).click();
  await morning.getByRole('checkbox', { name: '오메가3 선택' }).check();
  await expect(morning.getByRole('button', { name: '1개 되돌리기' })).toBeVisible();
  await morning.getByRole('checkbox', { name: '종합비타민 선택' }).check();
  await expect(morning.getByRole('checkbox', { name: '오메가3 선택' })).not.toBeChecked();
  await expect(morning.getByRole('button', { name: '1개 먹었어요' })).toBeVisible();
  await morning.getByRole('checkbox', { name: '종합비타민 선택' }).uncheck();
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(2);
  if (IS_REAL_API) expect(requests.map(item => item.supplementId)).toEqual([501, 502]);
});

test('되돌리기 실패는 완료 상태를 유지하고 같은 false 요청으로 재시도한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { morning, requests, failNextSave } = await openHome(page);
  await morning.getByRole('button', { name: '다 먹었어요' }).click();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(2);
  failNextSave(501);
  await morning.getByRole('button', { name: '개별 선택' }).click();
  await morning.getByRole('checkbox', { name: '오메가3 선택' }).check();
  await morning.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect(morning.getByRole('alert')).toBeVisible();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(2);
  await morning.getByRole('button', { name: '다시 시도' }).click();
  await expect(morning.getByText('복용 완료', { exact: true })).toHaveCount(1);
  expect(requests.slice(-2)).toEqual([
    { supplementId: 501, date: DATE, slot: 'morning', taken: false },
    { supplementId: 501, date: DATE, slot: 'morning', taken: false },
  ]);
});

test('홈 영양제 행은 해당 등록의 관리 시트로 진입하고 닫은 뒤 다시 열리지 않는다', async ({ page }) => {
  const { morning, requests } = await openHome(page);
  await morning.getByRole('button', { name: '종합비타민 관리' }).click();
  await expect(page).toHaveURL(/\/supplements$/);
  const sheet = page.getByRole('dialog', { name: '종합비타민', exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('heading', { name: '내 영양제', exact: true })).toBeVisible();
  await expect(sheet.getByRole('group', { name: '내 메모' })).toBeVisible();
  await expect(sheet.getByRole('group', { name: '내 후기' })).toBeVisible();
  await expect(sheet.locator('textarea')).toHaveCount(0);
  expect(requests).toHaveLength(0);
  await sheet.getByRole('button', { name: '닫기', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('heading', { name: '먹고 있는 영양제 3개' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('홈 진입 후 소유 목록에서 사라진 등록은 관리 시트를 열지 않고 진입 상태를 소비한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { morning, removeRegistration } = await openHome(page);
  await expect(morning.getByRole('button', { name: '오메가3 관리' })).toBeVisible();
  removeRegistration(501);
  await morning.getByRole('button', { name: '오메가3 관리' }).click();
  await expect(page.getByRole('heading', { name: '먹고 있는 영양제 2개' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.history.state?.usr ?? null)).toBeNull();
});
