import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);

async function openDetail(page: Page, failSave = false) {
  const patches: Record<string, unknown>[] = [];
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'record-editor-test');
    sessionStorage.setItem('poke.account-principal', 'record-editor@example.com');
  });
  if (IS_REAL_API) {
    let registration = {
      id: 502, custom_name: '종합비타민', dose_amount: '1.000', dose_unit: '정',
      start_date: '2026-09-01', end_date: null, status: 'ACTIVE', score: null,
      note: null as string | null, review_body: null as string | null,
      created_at: '2026-09-01T09:00:00+09:00', updated_at: null,
      slots: [{ slot: 'MORNING', time: '07:30:00' }], supplement: null,
    };
    await page.route('**/api/v1/users/me', route => route.fulfill({ json: {
      name: '테스트', maskedName: '테*트', phoneNumber: null, birthDate: null, gender: null,
    } }));
    await page.route('**/api/v1/med/user-suppl-nutr**', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { items: [registration], total: 1, offset: 0, limit: 100, nutrient_standard: null } });
        return;
      }
      expect(route.request().method()).toBe('PATCH');
      expect(new URL(route.request().url()).pathname).toBe('/api/v1/med/user-suppl-nutr/502');
      const body = route.request().postDataJSON();
      patches.push(body);
      if (failSave) {
        failSave = false;
        await route.fulfill({ status: 500, json: { detail: '일시적인 저장 실패' } });
        return;
      }
      registration = { ...registration, ...body, slots: body.slots.map((slot: string) => ({ slot, time: '07:30:00' })) };
      await route.fulfill({ json: registration });
    });
  }
  await page.goto('/supplements');
  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /종합비타민/ }).click();
  const detail = page.getByRole('dialog', { name: '종합비타민', exact: true });
  await expect(detail).toBeVisible();
  return { detail, patches };
}

test('기본 영양제 상세는 기록 조회와 등록 버튼만 표시하고 중복 기록 입력은 없다', async ({ page }) => {
  const { detail } = await openDetail(page);
  await expect(detail.locator('textarea')).toHaveCount(0);
  await expect(detail.getByRole('button', { name: /^별 [1-5]점$/ })).toHaveCount(0);
  await expect(detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '등록하기' })).toBeVisible();
  await expect(detail.getByRole('group', { name: '내 후기' }).getByRole('button', { name: '등록하기' })).toBeVisible();
  await expect(detail.getByRole('heading', { name: '복용 정보 수정' })).toBeVisible();
  await expect(detail.getByRole('button', { name: '복용 중단하기' })).toBeVisible();
});

test('메모 등록 후 카드와 CTA가 갱신되고 후기 수정 창에서 두 기록을 비울 수 있다', async ({ page }) => {
  const { detail, patches } = await openDetail(page);
  await detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '내 기록 편집', exact: true });
  await editor.getByRole('textbox', { name: /^메모/ }).fill('  아침 식후  ');
  await editor.getByRole('textbox', { name: /^후기/ }).fill('  먹기 편해요  ');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  const memo = detail.getByRole('group', { name: '내 메모' });
  const review = detail.getByRole('group', { name: '내 후기' });
  await expect(memo.getByText('아침 식후', { exact: true })).toBeVisible();
  await expect(memo.getByRole('button', { name: '수정하기' })).toBeVisible();
  await expect(review.getByText('먹기 편해요', { exact: true })).toBeVisible();
  await review.getByRole('button', { name: '수정하기' }).click();
  await expect(editor.getByRole('textbox', { name: /^메모/ })).toHaveValue('아침 식후');
  await editor.getByRole('textbox', { name: /^메모/ }).fill('');
  await editor.getByRole('textbox', { name: /^후기/ }).fill('  ');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(memo.getByRole('button', { name: '등록하기' })).toBeVisible();
  await expect(review.getByRole('button', { name: '등록하기' })).toBeVisible();
  if (IS_REAL_API) expect(patches).toEqual([
    { dose_amount: 1, slots: ['MORNING'], score: null, note: '아침 식후', review_body: '먹기 편해요' },
    { dose_amount: 1, slots: ['MORNING'], score: null, note: null, review_body: null },
  ]);
});

test('기록 편집 취소는 카드 값을 바꾸지 않고 다시 열면 저장된 값으로 시작한다', async ({ page }) => {
  const { detail, patches } = await openDetail(page);
  const memo = detail.getByRole('group', { name: '내 메모' });
  await memo.getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '내 기록 편집', exact: true });
  await editor.getByRole('textbox', { name: /^메모/ }).fill('저장하지 않을 메모');
  await editor.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(memo.getByText('작성한 메모가 없어요.')).toBeVisible();
  await memo.getByRole('button', { name: '등록하기' }).click();
  await expect(editor.getByRole('textbox', { name: /^메모/ })).toHaveValue('');
  expect(patches).toHaveLength(0);
});

test('기록 저장 실패는 편집창과 draft를 유지하고 같은 payload로 재시도한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { detail, patches } = await openDetail(page, true);
  await detail.getByRole('group', { name: '내 후기' }).getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '내 기록 편집', exact: true });
  await editor.getByRole('textbox', { name: /^메모/ }).fill('유지할 메모');
  await editor.getByRole('textbox', { name: /^후기/ }).fill('유지할 후기');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  const error = page.getByRole('dialog', { name: '영양제 정보를 저장하지 못했어요' });
  await expect(error).toBeVisible();
  await error.getByRole('button', { name: '확인', exact: true }).click();
  await expect(editor).toBeVisible();
  await expect(editor.getByRole('textbox', { name: /^메모/ })).toHaveValue('유지할 메모');
  await expect(editor.getByRole('textbox', { name: /^후기/ })).toHaveValue('유지할 후기');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(detail.getByRole('group', { name: '내 메모' })).toContainText('유지할 메모');
  expect(patches).toHaveLength(2);
  expect(patches[0]).toEqual({ dose_amount: 1, slots: ['MORNING'], score: null, note: '유지할 메모', review_body: '유지할 후기' });
  expect(patches[1]).toEqual(patches[0]);
});

test('기록 저장은 미저장 복용정보를 보내지 않고 별도 복용정보 저장은 기록을 유지한다', async ({ page }) => {
  const { detail, patches } = await openDetail(page);
  await detail.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await detail.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심', exact: true }).click();
  await detail.getByRole('button', { name: '별점 수정' }).click();
  const rating = page.getByRole('dialog', { name: '별점 수정' });
  await rating.getByRole('button', { name: '별 3점' }).click();
  await rating.getByRole('button', { name: '저장', exact: true }).click();
  await expect(rating).toBeHidden();
  await detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '내 기록 편집', exact: true });
  await editor.getByRole('textbox', { name: /^메모/ }).fill('기록만 먼저 저장');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(detail.getByText('2 정', { exact: true })).toBeVisible();
  await expect(detail.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await detail.getByRole('button', { name: '저장', exact: true }).click();
  await expect(detail).toBeHidden();
  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /종합비타민/ }).click();
  await expect(detail.getByRole('group', { name: '내 메모' })).toContainText('기록만 먼저 저장');
  await expect(detail.getByText('2 정', { exact: true })).toBeVisible();
  if (IS_REAL_API) expect(patches).toEqual([
    { dose_amount: 1, slots: ['MORNING'], score: 3, note: null, review_body: null },
    { dose_amount: 1, slots: ['MORNING'], score: 3, note: '기록만 먼저 저장', review_body: null },
    { dose_amount: 2, slots: ['MORNING', 'LUNCH'], score: 3, note: '기록만 먼저 저장', review_body: null },
  ]);
});
