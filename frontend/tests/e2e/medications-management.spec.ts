import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-02T12:00:00+09:00'));
});

test('처방 두 건을 같은 화면에서 독립적으로 펼친다', async ({ page }) => {
  await page.goto('/dev/medications');

  const first = page.getByRole('button', { name: /2026년 8월 22일 처방/ });
  const second = page.getByRole('button', { name: /2026년 8월 24일 처방/ });
  await first.click();
  await second.click();

  await expect(first).toHaveAttribute('aria-expanded', 'true');
  await expect(second).toHaveAttribute('aria-expanded', 'true');
  await expect(page).toHaveURL(/\/dev\/medications$/);
  await expect(page.getByRole('region', { name: '2026년 8월 22일 처방 상세' })).toBeVisible();
  await expect(page.getByRole('region', { name: '2026년 8월 24일 처방 상세' })).toBeVisible();
  await expect(
    page.getByRole('region', { name: '2026년 8월 22일 처방 상세' }).getByRole('button', {
      name: /복용 시간 수정/,
    }),
  ).toHaveCount(3);
  await expect(
    page.getByRole('region', { name: '2026년 8월 24일 처방 상세' }).getByRole('button', {
      name: /복용 시간 수정/,
    }),
  ).toHaveCount(0);
  await expect(page.getByRole('button', { name: '약봉투 사진 보기' })).toHaveCount(0);
});

test('연도를 넘는 처방 기간을 양쪽 연도와 함께 보여준다', async ({ page }) => {
  await page.goto('/dev/medications-cross-year');

  await expect(page.getByText('2026년 12월 28일 ~ 2027년 1월 3일 · 약 4개')).toBeVisible();
});

test('제거한 처방 상세 URL은 더 이상 상세 화면을 렌더링하지 않는다', async ({ page }) => {
  await page.goto(['/medications', '12'].join('/'));

  await expect(page.getByRole('heading', { name: '처방 상세' })).toHaveCount(0);
});

test('기간 필터는 URL에 남고 기본값은 쿼리를 제거한다', async ({ page }) => {
  await page.goto('/dev/medications');
  await expect(page).toHaveURL(/\/dev\/medications$/);
  await expect(page.getByRole('button', { name: '최근 6개월' })).toBeVisible();

  await page.getByRole('button', { name: '최근 6개월' }).click();
  await expect(page.getByRole('radio', { name: '최근 1개월' })).toHaveCount(0);
  await expect(page.getByRole('radio', { name: '최근 1년' })).toBeVisible();
  await page.getByRole('dialog').getByText('최근 3개월', { exact: true }).click();
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page).toHaveURL(/from=2026-06-02&to=2026-09-02/);

  await page.goBack();
  await expect(page).toHaveURL(/\/dev\/medications$/);
  await expect(page.getByRole('button', { name: '최근 6개월' })).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(/from=2026-06-02&to=2026-09-02/);

  await page.getByRole('button', { name: '최근 3개월' }).click();
  await page.getByRole('dialog').getByText('최근 6개월', { exact: true }).click();
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page).toHaveURL(/\/dev\/medications$/);

  await page.getByRole('button', { name: '최근 6개월' }).click();
  await page.getByRole('dialog').getByText('최근 1년', { exact: true }).click();
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page).toHaveURL(/from=2025-09-02&to=2026-09-02/);
});

test('직접 지정 역전 범위는 시트 안에서 막는다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '최근 6개월' }).click();
  await page.getByRole('dialog').getByText('직접 지정', { exact: true }).click();
  await page.getByLabel('시작일').fill('2026-09-02');
  await page.getByLabel('종료일').fill('2026-09-01');
  await page.getByRole('button', { name: '적용' }).click();

  await expect(page.getByRole('dialog')).toContainText('시작일은 종료일보다 늦을 수 없어요.');
});

test('직접 지정은 오늘부터 과거 2년까지만 허용한다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '최근 6개월' }).click();
  await page.getByRole('dialog').getByText('직접 지정', { exact: true }).click();
  await page.getByLabel('시작일').fill('2024-09-02');
  await page.getByLabel('종료일').fill('2026-09-02');
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page).toHaveURL(/from=2024-09-02&to=2026-09-02/);

  await page.getByRole('button', { name: '직접 지정' }).click();
  await page.getByLabel('시작일').fill('2024-09-01');
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page.getByRole('dialog')).toContainText(
    '조회 기간은 오늘부터 과거 2년까지만 선택할 수 있어요.',
  );

  await page.getByLabel('시작일').fill('2026-09-02');
  await page.getByLabel('종료일').fill('2026-09-03');
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page.getByRole('dialog')).toContainText(
    '조회 기간은 오늘부터 과거 2년까지만 선택할 수 있어요.',
  );
});

test('처방 기록은 조회 결과 전체를 처음부터 표시한다', async ({ page }) => {
  await page.goto('/dev/medications-many');

  const cards = page.getByRole('button', { name: /처방 · 약/ });
  await expect(page.getByText('41개', { exact: true })).toBeVisible();
  await expect(cards).toHaveCount(41);
});

test('선택 모드에서는 카드 클릭이 펼침 대신 선택이고 순차 삭제한다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('button', { name: '삭제하기' })).toHaveCount(0);
  await expect(page.getByRole('checkbox')).toHaveCount(2);
  await expect(page.getByRole('checkbox', { name: /전체/ })).toHaveCount(0);

  const first = page.getByRole('button', { name: /2026년 8월 22일 처방/ });
  await first.click();
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('checkbox', { name: /2026년 8월 24일 처방 선택/ }).check();
  await expect(page.getByRole('heading', { name: '2개 선택' })).toBeVisible();

  await page.getByRole('button', { name: '삭제하기' }).click();
  await expect(page.getByRole('dialog')).toContainText('2개를 삭제할까요?');
  await page.getByRole('dialog').getByRole('button', { name: '삭제하기' }).click();

  await expect(page.getByText('2개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('이 기간에 등록한 처방이 없어요')).toBeVisible();
  await expect(page.getByRole('button', { name: '기간 넓히기' })).toBeVisible();
  await expect(page.getByRole('button', { name: '약봉투 등록하기' })).toHaveCount(0);
});

test('375px에서 펼침·선택·필터 상태에 가로 스크롤이 없다', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /2026년 8월 22일 처방/ }).click();
  await page.getByRole('button', { name: /2026년 8월 24일 처방/ }).click();
  await page.getByRole('button', { name: '삭제', exact: true }).click();

  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
});
