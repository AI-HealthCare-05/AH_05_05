import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const LONG_ALIAS = `퇴원후집중관리처방${'PRESCRIPTION'.repeat(12)}회차`;
const LONG_MEDICATION_NAME = `복합성분서방정${'MEDICATION'.repeat(14)}정`;
const MEAL_TIMES = {
  morning: '08:00',
  lunch: '13:00',
  evening: '19:00',
  bedtime: '22:30',
};

function overview(recordId: number, isFinished: boolean, daysRemaining: number) {
  return {
    recordId,
    alias: isFinished ? '지난 장기 처방' : LONG_ALIAS,
    documentImageUrl: `/api/v1/ocr/jobs/${recordId}/image`,
    start: { date: isFinished ? '2026-08-01' : '2026-09-05', slot: 'morning' },
    endDate: isFinished ? '2026-08-07' : '2026-09-14',
    daysRemaining,
    isFinished,
    mealTimes: MEAL_TIMES,
    medications: [
      {
        medicationId: recordId * 10,
        name: LONG_MEDICATION_NAME,
        dose: '125/500mg 2정',
        days: 10,
        daysRemaining,
        slots: ['morning', 'lunch', 'evening', 'bedtime'],
        asNeeded: false,
      },
      {
        medicationId: recordId * 10 + 1,
        name: '아세트아미노펜복합연질캡슐',
        dose: '650mg 1캡슐',
        days: 10,
        daysRemaining,
        slots: ['morning', 'evening'],
        asNeeded: false,
      },
    ],
  };
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function expectTextFits(locator: Locator) {
  await expect(locator).toBeVisible();
  const metrics = await locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      horizontal: element.scrollWidth <= element.clientWidth + 1,
      vertical: element.scrollHeight <= element.clientHeight + 1,
      overflow: style.overflow,
      textOverflow: style.textOverflow,
      whiteSpace: style.whiteSpace,
    };
  });
  expect(metrics.horizontal).toBe(true);
  expect(metrics.vertical).toBe(true);
  expect(metrics.textOverflow).not.toBe('ellipsis');
  expect(metrics.whiteSpace).not.toBe('nowrap');
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-353-medication-layout-token');
    sessionStorage.setItem('poke.account-principal', 'feature-353-medication-layout@example.com');
  });
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(353, false, 5), overview(354, true, 0)]),
  );
});

test('상태 행을 카드 왼쪽 위에 두고 모든 처방 정보를 폭별로 자르지 않는다', async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);

  for (const width of [320, 375, 390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/medications');

    const activeCard = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
    const title = activeCard.getByText(LONG_ALIAS, { exact: true });
    const status = activeCard.getByText('복용 중', { exact: true });
    const remaining = activeCard.getByText('5일 남음', { exact: true });
    const period = activeCard.getByText('2026년 9월 5일 ~ 14일', { exact: true });

    await expect(activeCard).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`after-medication-cards-${width}.png`), fullPage: true });

    const [statusBox, remainingBox, titleBox] = await Promise.all([
      status.boundingBox(),
      remaining.boundingBox(),
      title.boundingBox(),
    ]);
    expect(statusBox).not.toBeNull();
    expect(remainingBox).not.toBeNull();
    expect(titleBox).not.toBeNull();
    expect(
      Math.abs(
        statusBox!.y + statusBox!.height / 2 -
          (remainingBox!.y + remainingBox!.height / 2),
      ),
    ).toBeLessThanOrEqual(2);
    expect(Math.abs(statusBox!.x - titleBox!.x)).toBeLessThanOrEqual(2);
    expect(Math.max(statusBox!.y + statusBox!.height, remainingBox!.y + remainingBox!.height))
      .toBeLessThanOrEqual(titleBox!.y);

    for (const text of [title, period]) {
      await expectTextFits(text);
    }

    const chevron = activeCard.locator('svg').last();
    expect((await chevron.boundingBox())!.width).toBe(20);
    expect(await activeCard.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await activeCard.click();
    const details = page.getByRole('region', { name: '2026년 9월 5일 처방 상세' });
    await expectTextFits(details.getByText(new RegExp(LONG_MEDICATION_NAME)));
    await expect(details.getByText('자기전 22:30', { exact: true })).toBeVisible();

    const finishedCard = page.getByRole('button', { name: /2026년 8월 1일 처방.*복용 완료/ });
    const finishedStatus = finishedCard.getByText('복용 완료', { exact: true });
    const finishedTitle = finishedCard.getByText('지난 장기 처방', { exact: true });
    const [finishedStatusBox, finishedTitleBox] = await Promise.all([
      finishedStatus.boundingBox(),
      finishedTitle.boundingBox(),
    ]);
    expect(finishedStatusBox).not.toBeNull();
    expect(finishedTitleBox).not.toBeNull();
    expect(Math.abs(finishedStatusBox!.x - finishedTitleBox!.x)).toBeLessThanOrEqual(2);
    expect(finishedStatusBox!.y + finishedStatusBox!.height).toBeLessThanOrEqual(finishedTitleBox!.y);
    await expect(finishedCard.getByText(/일 남음|D-Day|D-\d+/)).toHaveCount(0);
  }
});

test('본 카드의 펼침과 연필 편집, 기본 카드 D-Day, 선택 모드를 유지한다', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/medications');

  const featureCard = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
  await expect(featureCard.getByText('5일 남음', { exact: true })).toBeVisible();
  await featureCard.click();
  await expect(page.getByRole('region', { name: '2026년 9월 5일 처방 상세' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: '처방 편집' })).toHaveCount(0);
  await featureCard.click();
  await page.getByRole('button', { name: '처방 수정 · 2026년 9월 5일', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '처방 편집' })).toBeVisible();
  await expect(page.getByRole('region', { name: '2026년 9월 5일 처방 상세' })).toHaveCount(0);
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click();

  await page.getByRole('button', { name: '삭제', exact: true }).click();
  const checkbox = page.getByRole('checkbox', { name: '2026년 9월 5일 처방 선택' });
  await featureCard.click();
  await expect(checkbox).toBeChecked();
  await expect(page.getByRole('dialog', { name: '처방 편집' })).toHaveCount(0);

  await page.goto('/dev/medications');
  const defaultCard = page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ });
  await expect(defaultCard.getByText('D-4', { exact: true })).toBeVisible();
  await defaultCard.click();
  await expect(defaultCard).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('region', { name: '2026년 9월 5일 처방 상세' })).toBeVisible();
});
