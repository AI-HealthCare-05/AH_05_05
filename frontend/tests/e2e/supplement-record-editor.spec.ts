import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);

async function expectNameContained(name: ReturnType<Page['locator']>, container: ReturnType<Page['locator']>) {
  await expect(name).toBeVisible();
  const metrics = await name.evaluate((element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      textOverflow: style.textOverflow,
      rect: { left: rect.left, right: rect.right },
    };
  });
  const containerRect = await container.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right };
  });
  expect(metrics.textOverflow).not.toBe('ellipsis');
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
  expect(metrics.scrollHeight).toBeLessThanOrEqual(metrics.clientHeight + 1);
  expect(metrics.rect.left).toBeGreaterThanOrEqual(containerRect.left - 1);
  expect(metrics.rect.right).toBeLessThanOrEqual(containerRect.right + 1);
}

async function expectNoHorizontalOverflow(container: ReturnType<Page['locator']>) {
  expect(await container.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
}

async function openDetail(page: Page, options: {
  failSave?: boolean;
  name?: string;
  note?: string | null;
  reviewBody?: string | null;
} = {}) {
  const patches: Record<string, unknown>[] = [];
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'record-editor-test');
    sessionStorage.setItem('poke.account-principal', 'record-editor@example.com');
  });
  if (IS_REAL_API) {
    let registration = {
      id: 502, custom_name: options.name ?? '종합비타민', dose_amount: '1.000', dose_unit: '정',
      start_date: '2026-09-01', end_date: null, status: 'ACTIVE', score: null,
      note: options.note ?? null, review_body: options.reviewBody ?? null,
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
      if (options.failSave) {
        options.failSave = false;
        await route.fulfill({ status: 500, json: { detail: '일시적인 저장 실패' } });
        return;
      }
      registration = { ...registration, ...body, slots: body.slots.map((slot: string) => ({ slot, time: '07:30:00' })) };
      await route.fulfill({ json: registration });
    });
  }
  await page.goto('/supplements');
  const name = options.name ?? '종합비타민';
  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: new RegExp(name) }).click();
  const detail = page.getByRole('dialog', { name, exact: true });
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

test('메모와 후기 CTA는 해당 입력만 열고 저장과 삭제 시 다른 기록을 보존한다', async ({ page }) => {
  const { detail, patches } = await openDetail(page);
  await detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '메모 편집', exact: true });
  await expect(editor).toBeVisible();
  await expect(editor.getByRole('textbox')).toHaveCount(1);
  await expect(editor.getByRole('textbox', { name: /^후기/ })).toHaveCount(0);
  await editor.getByRole('textbox', { name: /^메모/ }).fill('  아침 식후  ');
  if (process.env.SUPPLEMENT_EDITOR_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.SUPPLEMENT_EDITOR_SCREENSHOT_DIR}/supplement-memo-editor-${IS_REAL_API ? 'real' : 'mock'}.png` });
  }
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  const memo = detail.getByRole('group', { name: '내 메모' });
  const review = detail.getByRole('group', { name: '내 후기' });
  await expect(memo.getByText('아침 식후', { exact: true })).toBeVisible();
  await expect(memo.getByRole('button', { name: '수정하기' })).toBeVisible();
  await review.getByRole('button', { name: '등록하기' }).click();
  const reviewEditor = page.getByRole('dialog', { name: '후기 편집', exact: true });
  await expect(reviewEditor.getByRole('textbox')).toHaveCount(1);
  await expect(reviewEditor.getByRole('textbox', { name: /^메모/ })).toHaveCount(0);
  await reviewEditor.getByRole('textbox', { name: /^후기/ }).fill('  먹기 편해요  ');
  if (process.env.SUPPLEMENT_EDITOR_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.SUPPLEMENT_EDITOR_SCREENSHOT_DIR}/supplement-review-editor-${IS_REAL_API ? 'real' : 'mock'}.png` });
  }
  await reviewEditor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(reviewEditor).toBeHidden();
  await expect(memo.getByText('아침 식후', { exact: true })).toBeVisible();
  await expect(review.getByText('먹기 편해요', { exact: true })).toBeVisible();
  await memo.getByRole('button', { name: '수정하기' }).click();
  await expect(editor.getByRole('textbox', { name: /^메모/ })).toHaveValue('아침 식후');
  await editor.getByRole('textbox', { name: /^메모/ }).fill('');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(memo.getByRole('button', { name: '등록하기' })).toBeVisible();
  await expect(review.getByText('먹기 편해요', { exact: true })).toBeVisible();
  await review.getByRole('button', { name: '수정하기' }).click();
  await expect(reviewEditor.getByRole('textbox', { name: /^후기/ })).toHaveValue('먹기 편해요');
  await reviewEditor.getByRole('textbox', { name: /^후기/ }).fill('  ');
  await reviewEditor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(reviewEditor).toBeHidden();
  await expect(review.getByRole('button', { name: '등록하기' })).toBeVisible();
  if (IS_REAL_API) expect(patches).toEqual([
    { dose_amount: 1, slots: ['MORNING'], note: '아침 식후' },
    { dose_amount: 1, slots: ['MORNING'], review_body: '먹기 편해요' },
    { dose_amount: 1, slots: ['MORNING'], note: null },
    { dose_amount: 1, slots: ['MORNING'], review_body: null },
  ]);
});

test('기록 편집 취소는 카드 값을 바꾸지 않고 다시 열면 저장된 값으로 시작한다', async ({ page }) => {
  const { detail, patches } = await openDetail(page);
  const memo = detail.getByRole('group', { name: '내 메모' });
  await memo.getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '메모 편집', exact: true });
  await editor.getByRole('textbox', { name: /^메모/ }).fill('저장하지 않을 메모');
  await editor.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(memo.getByText('작성한 메모가 없어요.')).toBeVisible();
  await memo.getByRole('button', { name: '등록하기' }).click();
  await expect(editor.getByRole('textbox', { name: /^메모/ })).toHaveValue('');
  expect(patches).toHaveLength(0);
});

test('기록 저장 실패는 편집창과 draft를 유지하고 같은 payload로 재시도한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { detail, patches } = await openDetail(page, { failSave: true });
  await detail.getByRole('group', { name: '내 후기' }).getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '후기 편집', exact: true });
  await expect(editor.getByRole('textbox', { name: /^메모/ })).toHaveCount(0);
  await editor.getByRole('textbox', { name: /^후기/ }).fill('유지할 후기');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  const error = page.getByRole('dialog', { name: '영양제 정보를 저장하지 못했어요' });
  await expect(error).toBeVisible();
  await error.getByRole('button', { name: '확인', exact: true }).click();
  await expect(editor).toBeVisible();
  await expect(editor.getByRole('textbox', { name: /^후기/ })).toHaveValue('유지할 후기');
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(detail.getByRole('group', { name: '내 후기' })).toContainText('유지할 후기');
  expect(patches).toHaveLength(2);
  expect(patches[0]).toEqual({ dose_amount: 1, slots: ['MORNING'], review_body: '유지할 후기' });
  expect(patches[1]).toEqual(patches[0]);
});

test('긴 영양제 이름은 목록과 상세 및 중첩 팝업에서 전체가 줄바꿈된다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  test.setTimeout(120_000);
  const longName = `초고함량프리미엄종합비타민${'SUPPLEMENT'.repeat(18)}알약`;

  for (const width of [320, 375, 430, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const { detail } = await openDetail(page, { name: longName });
    const summaryName = detail
      .getByRole('region', { name: '내 영양제 요약' })
      .getByRole('heading', { name: longName, exact: true });
    await expectNameContained(summaryName, detail);
    await expectNoHorizontalOverflow(detail);

    await detail.getByRole('button', { name: '별점 수정' }).click();
    const rating = page.getByRole('dialog', { name: '별점 수정' });
    await expectNameContained(rating.getByText(`${longName}는 어떠셨나요?`, { exact: true }), rating);
    await expectNoHorizontalOverflow(rating);
    await rating.getByRole('button', { name: '닫기' }).click();

    await detail.getByRole('button', { name: '복용 중단하기' }).click();
    const stop = page.getByRole('dialog', { name: new RegExp(`${longName} 복용을 중단할까요`) });
    await expectNameContained(stop.getByRole('heading'), stop);
    await expectNameContained(stop.getByText(new RegExp(`^${longName} ·`)), stop);
    await expectNoHorizontalOverflow(stop);
    await stop.getByRole('button', { name: '취소' }).click();
    await detail.getByRole('button', { name: '닫기' }).click();

    const list = page.getByRole('region', { name: '먹고 있는 영양제' });
    const normalRow = list.getByRole('button', { name: new RegExp(longName) });
    await expectNameContained(normalRow.getByText(longName, { exact: true }), normalRow);
    const arrow = normalRow.locator('svg').last();
    expect((await arrow.boundingBox())?.width).toBe(20);

    await page.getByRole('button', { name: '삭제', exact: true }).click();
    const deleteRow = list.getByText(longName, { exact: true });
    const deleteLabel = list.locator('label').filter({ hasText: longName });
    await expectNameContained(deleteRow, deleteLabel);
    await expect(list.getByRole('checkbox', { name: `${longName} 선택` })).toBeVisible();
    await expectNoHorizontalOverflow(list);
    await page.getByRole('button', { name: '완료', exact: true }).click();
  }
});

test('메모와 후기는 100자를 보여주고 101번째 입력을 저장하지 않는다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const { detail, patches } = await openDetail(page);
  const memo = detail.getByRole('group', { name: '내 메모' });
  await memo.getByRole('button', { name: '등록하기' }).click();
  const editor = page.getByRole('dialog', { name: '메모 편집', exact: true });
  const textbox = editor.getByRole('textbox', { name: /^메모/ });
  const oneHundred = '메'.repeat(100);
  await textbox.fill(`${oneHundred}초`);

  await expect(textbox).toHaveValue(oneHundred);
  await expect(editor.getByText('100 / 100', { exact: true })).toBeVisible();
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  expect(patches.at(-1)).toMatchObject({ note: oneHundred });

  await detail.getByRole('group', { name: '내 후기' }).getByRole('button', { name: '등록하기' }).click();
  const reviewEditor = page.getByRole('dialog', { name: '후기 편집', exact: true });
  const reviewTextbox = reviewEditor.getByRole('textbox', { name: /^후기/ });
  const review = '후'.repeat(100);
  await reviewTextbox.fill(`${review}초`);
  await expect(reviewTextbox).toHaveValue(review);
  await expect(reviewEditor.getByText('100 / 100', { exact: true })).toBeVisible();
});

test('기존 100자 초과 기록은 그대로 보여주되 줄이기 전에는 저장하지 않는다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const legacyNote = '기'.repeat(120);
  const { detail, patches } = await openDetail(page, { note: legacyNote });
  await detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '수정하기' }).click();
  const editor = page.getByRole('dialog', { name: '메모 편집', exact: true });
  const textbox = editor.getByRole('textbox', { name: /^메모/ });
  const save = editor.getByRole('button', { name: '저장', exact: true });

  await expect(textbox).toHaveValue(legacyNote);
  await expect(editor.getByText('120 / 100', { exact: true })).toBeVisible();
  await expect(editor.getByRole('alert')).toContainText('100자 이내로 줄여주세요.');
  await expect(save).toBeDisabled();
  await save.evaluate((button) => {
    button.removeAttribute('disabled');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  expect(patches).toHaveLength(0);

  const shortened = '기'.repeat(100);
  await textbox.fill(shortened);
  await expect(save).toBeEnabled();
  await save.click();
  await expect(editor).toBeHidden();
  expect(patches.at(-1)).toMatchObject({ note: shortened });
});

test('기존 100자 초과 기록은 용량·별점·다른 기록 저장 payload에서 제외한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  const legacyNote = '기'.repeat(120);
  const legacyReview = '후'.repeat(120);
  const { detail, patches } = await openDetail(page, {
    note: legacyNote,
    reviewBody: legacyReview,
  });

  await detail.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await detail.getByRole('button', { name: '저장', exact: true }).click();
  await expect(detail).toBeHidden();
  expect(patches[0]).toEqual({ dose_amount: 2, slots: ['MORNING'] });

  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /종합비타민/ }).click();
  await detail.getByRole('button', { name: '별점 수정' }).click();
  const rating = page.getByRole('dialog', { name: '별점 수정' });
  await rating.getByRole('button', { name: '별 3점' }).click();
  await rating.getByRole('button', { name: '저장', exact: true }).click();
  expect(patches[1]).toEqual({ dose_amount: 2, slots: ['MORNING'], score: 3 });

  await detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '수정하기' }).click();
  const memoEditor = page.getByRole('dialog', { name: '메모 편집', exact: true });
  await memoEditor.getByRole('textbox', { name: /^메모/ }).fill('줄인 메모');
  await memoEditor.getByRole('button', { name: '저장', exact: true }).click();
  expect(patches[2]).toEqual({ dose_amount: 2, slots: ['MORNING'], note: '줄인 메모' });
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
  const editor = page.getByRole('dialog', { name: '메모 편집', exact: true });
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
    { dose_amount: 1, slots: ['MORNING'], score: 3 },
    { dose_amount: 1, slots: ['MORNING'], note: '기록만 먼저 저장' },
    { dose_amount: 2, slots: ['MORNING', 'LUNCH'] },
  ]);
});
