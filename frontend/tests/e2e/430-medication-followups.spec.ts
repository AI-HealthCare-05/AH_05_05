import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const TODAY = '2026-09-12';

const OVERVIEWS = [
  {
    recordId: 430,
    alias: '해맑은소아청소년과의원',
    documentImageUrl: '/api/v1/ocr/jobs/430/image',
    start: { date: '2026-09-10', slot: 'morning' },
    endDate: '2026-09-19',
    daysRemaining: 8,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [
      {
        medicationId: 4301,
        name: '세프디니르건조시럽',
        dose: '5mL',
        days: 10,
        daysRemaining: 8,
        slots: ['morning', 'lunch', 'evening'],
        asNeeded: false,
      },
    ],
  },
  {
    recordId: 431,
    alias: '저녁 처방',
    documentImageUrl: '/api/v1/ocr/jobs/431/image',
    start: { date: '2026-09-11', slot: 'morning' },
    endDate: '2026-09-20',
    daysRemaining: 9,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [
      {
        medicationId: 4311,
        name: '암브록솔시럽',
        dose: '5mL',
        days: 10,
        daysRemaining: 9,
        slots: ['morning'],
        asNeeded: false,
      },
    ],
  },
];

const OCR_RESULT = {
  batchId: '430',
  ocrStatus: 'ready_for_review',
  documentImageUrl: '/api/v1/ocr/jobs/430/image',
  fields: {
    hospitalName: { value: '해맑은소아청소년과의원', confidence: 'high' },
    dispensedDate: { value: TODAY, confidence: 'high' },
  },
  medications: [
    {
      tempId: '430-1',
      name: '세프디니르건조시럽',
      strength: '125mg/5mL',
      doseQuantity: '5mL',
      timesPerDay: 3,
      days: 5,
      confidence: 'low',
    },
  ],
  lowConfidenceCount: 1,
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-430-token');
    sessionStorage.setItem('poke.account-principal', 'feature-430@example.com');
  });
}

async function routeApp(page: Page, overviews = OVERVIEWS) {
  await page.route('**/api/v1/**', (route) => json(route, {}));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, (route) => json(route, overviews));
  await page.route('**/api/v1/medications/doses*', (route) => json(route, []));
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    json(route, { items: [], total: 0, offset: 0, limit: 100 }),
  );
  await page.route('**/api/v1/med/supplement-doses*', (route) => json(route, []));
  await page.route('**/api/v1/display/med/nutr/rank*', (route) => json(route, { items: [] }));
  await page.route('**/api/v1/user/challenges*', (route) =>
    json(route, { items: [], totalCount: 0 }),
  );
  await page.route('**/api/v1/user/custom-challenge-participations*', (route) =>
    json(route, { items: [], totalCount: 0 }),
  );
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-12T12:00:00+09:00'));
  await authenticate(page);
});

test('홈 빈 복약과 빈 영양제는 같은 안내 구조와 각각의 CTA를 제공한다', async ({ page }, testInfo) => {
  await routeApp(page, []);
  await page.goto('/home');

  const medicationPanel = page.getByRole('tabpanel', { name: '오늘의 복약' });
  const medicationCard = medicationPanel.locator('.rx-card');
  await expect(medicationPanel.getByText('복약정보를 등록하시면 시간에 맞춰 알림을 받으실 수 있어요.')).toBeVisible();
  await expect(medicationPanel.getByRole('button', { name: '약봉투 등록하기' })).toBeVisible();
  const medicationStyle = await medicationCard.evaluate((element) => {
    const style = getComputedStyle(element);
    return { backgroundColor: style.backgroundColor, padding: style.padding, gap: style.gap };
  });

  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  const supplementPanel = page.getByRole('tabpanel', { name: '오늘의 영양제' });
  const supplementCard = supplementPanel.locator('.rx-card');
  await expect(supplementPanel.getByText('영양제를 등록하시면 시간에 맞춰 알림을 받으실 수 있어요.')).toBeVisible();
  const browse = supplementPanel.getByRole('button', { name: '영양제 살펴보기' });
  await expect(browse).toBeVisible();

  const supplementStyle = await supplementCard.evaluate((element) => {
    const style = getComputedStyle(element);
    return { backgroundColor: style.backgroundColor, padding: style.padding, gap: style.gap };
  });
  expect(supplementStyle).toEqual(medicationStyle);
  await page.screenshot({ path: testInfo.outputPath('home-empty-375.png'), fullPage: true });
  await browse.click();
  await expect(page).toHaveURL('/supplements?tab=browse');
});

for (const width of [390, 1280]) {
  test(`홈 복약은 일부 복용과 되돌리기를 유지하고 펼친 약명을 보통 굵기로 표시한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await routeApp(page);
    const doseWrites: Array<{ recordId: number; taken: boolean }> = [];
    await page.route('**/api/v1/medications/doses*', async (route) => {
      if (route.request().method() === 'GET') return json(route, []);
      const body = route.request().postDataJSON() as { recordId: number; taken: boolean };
      doseWrites.push(body);
      return json(route, body);
    });
    await page.goto('/home');

    const morning = page.getByRole('group', { name: '아침약 상세' });
    const doseAction = morning.getByRole('button', { name: '먹었어요', exact: true });
    await expect(doseAction).toBeVisible();
    const episode = morning.getByRole('article', { name: /해맑은소아청소년과의원/ });
    await episode.locator('[data-episode-row]').click();
    await expect(doseAction).toBeVisible();
    await expect(episode.locator('[data-episode-row]')).toHaveAttribute('aria-pressed', 'true');
    await doseAction.click();
    await expect.poll(() => doseWrites).toEqual([
      expect.objectContaining({ recordId: 430, taken: true }),
    ]);
    await episode.locator('[data-episode-row]').click();
    await morning.getByRole('button', { name: '복약 기록 되돌리기', exact: true }).click();
    await expect.poll(() => doseWrites).toEqual([
      expect.objectContaining({ recordId: 430, taken: true }),
      expect.objectContaining({ recordId: 430, taken: false }),
    ]);
    await episode.getByRole('button', { name: /처방 펼치기$/ }).click();
    const medicationName = episode.getByRole('group', { name: /처방 약 상세/ })
      .getByText('세프디니르건조시럽', { exact: true });
    expect(Number(await medicationName.evaluate((element) => getComputedStyle(element).fontWeight)))
      .toBeLessThan(600);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`home-medication-${width}.png`), fullPage: true });
  });
}

for (const width of [375, 390, 1280]) {
  test(`전체 완료도 건별 완료와 같은 처방명 위 태그를 유지한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const thirdOverview = {
      ...OVERVIEWS[1],
      recordId: 432,
      alias: '숨긴 처방',
      medications: [{
        ...OVERVIEWS[1].medications[0],
        medicationId: 4321,
        name: '카르보시스테인시럽',
      }],
    };
    await routeApp(page, [...OVERVIEWS, thirdOverview]);
    const doseRecords: Array<{ recordId: number; date: string; slot: string; taken: boolean }> = [];
    await page.route('**/api/v1/medications/doses*', async (route) => {
      if (route.request().method() === 'GET') return json(route, doseRecords);
      const body = route.request().postDataJSON() as typeof doseRecords[number];
      const existing = doseRecords.findIndex((record) => record.recordId === body.recordId);
      if (existing >= 0) doseRecords.splice(existing, 1);
      if (body.taken) doseRecords.push(body);
      return json(route, body);
    });
    await page.goto('/home');

    const detail = page.getByRole('group', { name: '아침약 상세' });
    const first = detail.getByRole('article', { name: /숨긴 처방/ });
    const second = detail.getByRole('article', { name: /저녁 처방/ });
    const completionBadges = detail.locator('[data-episode-completed-badge]');

    await first.locator('[data-episode-row]').click();
    await detail.getByRole('button', { name: '먹었어요', exact: true }).click();
    await expect(first.locator('[data-episode-completed-badge]')).toHaveText('복용 완료');
    await expect(second.locator('[data-episode-completed-badge]')).toHaveCount(0);
    await expect(page.locator('[data-medication-completed-summary]')).toHaveCount(0);

    await detail.getByRole('button', { name: '먹었어요', exact: true }).click();
    await expect(page.locator('[data-medication-completed-summary]')).toHaveCount(0);
    await expect(completionBadges).toHaveCount(2);
    await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
    await expect(completionBadges).toHaveCount(3);
    for (const article of await detail.getByRole('article').all()) {
      const [badgeBox, titleBox] = await Promise.all([
        article.locator('[data-episode-completed-badge]').boundingBox(),
        article.getByRole('heading').boundingBox(),
      ]);
      expect(badgeBox).not.toBeNull();
      expect(titleBox).not.toBeNull();
      expect(badgeBox!.y + badgeBox!.height).toBeLessThanOrEqual(titleBox!.y);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`home-completion-position-${width}.png`), fullPage: true });

    await second.locator('[data-episode-row]').click();
    await detail.getByRole('button', { name: '복약 기록 되돌리기', exact: true }).click();
    await expect(second.locator('[data-episode-completed-badge]')).toHaveCount(0);
    await expect(first.locator('[data-episode-completed-badge]')).toHaveText('복용 완료');
    await expect(detail.getByRole('article', { name: /해맑은소아청소년과의원/ })
      .locator('[data-episode-completed-badge]')).toHaveText('복용 완료');
    await expect(page.locator('[data-medication-completed-summary]')).toHaveCount(0);
  });
}

test('복약 상단은 처방 추가와 선택을 구분하고 선택 중 삭제와 취소 경로를 제공한다', async ({ page }, testInfo) => {
  await routeApp(page);
  await page.goto('/medications');

  const report = page.getByRole('button', { name: 'AI 보고서 받기' });
  const add = page.getByRole('button', { name: '처방 추가' });
  const select = page.getByRole('button', { name: '선택', exact: true });
  await expect(select).toBeVisible();
  expect(await report.evaluate((element) => getComputedStyle(element).backgroundColor))
    .not.toBe(await add.evaluate((element) => getComputedStyle(element).backgroundColor));

  await select.click();
  await expect(page.getByRole('heading', { name: '삭제할 처방을 선택하세요' })).toBeVisible();
  const remove = page.getByRole('button', { name: '삭제', exact: true });
  await expect(remove).toBeDisabled();
  await page.getByRole('checkbox', { name: /2026년 9월 10일 처방 선택/ }).check();
  await expect(remove).toBeEnabled();
  await expect(page.getByRole('button', { name: '취소', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('medication-selection-375.png'), fullPage: true });
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
});

for (const width of [390, 1280]) {
  test(`복용 중 카드의 시간대 범례와 중간톤 점을 유지한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await routeApp(page);
    await page.goto('/medications');
    const toggle = page.getByRole('button', { name: /2026년 9월 10일 처방.*복용 중/ });
    const card = page.locator('article').filter({ has: toggle });
    const edit = card.getByRole('button', { name: '처방 수정 · 2026년 9월 10일' });
    await expect(card.getByText('복용 중', { exact: true })).toBeVisible();
    const [chevronBox, pencilBox, editBox] = await Promise.all([
      toggle.locator('svg').last().boundingBox(),
      edit.locator('svg').boundingBox(),
      edit.boundingBox(),
    ]);
    expect(chevronBox).not.toBeNull();
    expect(pencilBox).not.toBeNull();
    expect(editBox).not.toBeNull();
    expect(Math.abs(
      chevronBox!.y + chevronBox!.height / 2 - (pencilBox!.y + pencilBox!.height / 2),
    )).toBeLessThanOrEqual(3);
    expect(editBox!.width).toBeGreaterThanOrEqual(44);
    expect(editBox!.height).toBeGreaterThanOrEqual(44);
    const memo = page.getByRole('button', { name: '복약 메모', exact: true });
    expect(await memo.evaluate((element) => getComputedStyle(element).boxShadow)).not.toBe('none');
    for (const label of ['아침', '점심', '저녁']) {
      await expect(card.getByText(label, { exact: true })).toBeVisible();
    }
    await toggle.click();
    const dots = card.getByRole('region').getByRole('img');
    await expect(dots).toHaveCount(3);
    const colors = await dots.evaluateAll((elements) =>
      elements.map((element) => getComputedStyle(element).backgroundColor),
    );
    expect(new Set(colors).size).toBe(3);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`medication-slots-${width}.png`), fullPage: true });
  });
}

for (const width of [375, 390, 1280]) {
  test(`OCR 미리보기 확대는 fitted baseline과 네 모서리 스크롤을 보장한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route('**/api/v1/ocr/jobs/430', (route) => json(route, OCR_RESULT));
    await page.route('**/api/v1/ocr/jobs/430/*image', (route) => route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1200"><rect width="900" height="1200" fill="white"/><text x="80" y="120" font-size="48">Rx envelope</text></svg>',
    }));
    await page.goto('/ocr-review?batchId=430');

    const medication = page.getByRole('article', { name: /세프디니르건조시럽/ });
    await expect(medication.locator('[aria-expanded]')).toHaveCount(0);
    await expect(medication.getByText('확인 필요', { exact: true })).toBeVisible();
    await expect(medication.locator('dl > div')).toHaveCount(4);
    const edit = medication.getByRole('button', { name: /세프디니르건조시럽.*수정/ });
    await expect(edit).toHaveText('');

    await page.getByRole('button', { name: '약봉투 크게 보기' }).click();
    const viewer = page.getByRole('dialog', { name: '약봉투 이미지 크게 보기' });
    const scrollArea = viewer.getByLabel('확대한 약봉투 이동 영역');
    const image = viewer.getByRole('img', { name: '확대한 약봉투' });
    const zoomIn = viewer.getByRole('button', { name: '확대', exact: true });
    const zoomOut = viewer.getByRole('button', { name: '축소', exact: true });
    await expect(image).toBeVisible();
    await expect(zoomOut).toBeDisabled();
    const baselineBox = await image.boundingBox();
    expect(baselineBox).not.toBeNull();

    await zoomIn.focus();
    await page.keyboard.press('Enter');
    await expect(viewer.getByRole('status')).toHaveText('150%');
    await expect(zoomOut).toBeEnabled();
    const zoomedBox = await image.boundingBox();
    expect(zoomedBox).not.toBeNull();
    expect(zoomedBox!.width / baselineBox!.width).toBeGreaterThanOrEqual(1.49);
    expect(zoomedBox!.width / baselineBox!.width).toBeLessThanOrEqual(1.51);
    expect(zoomedBox!.height / baselineBox!.height).toBeGreaterThanOrEqual(1.49);
    expect(zoomedBox!.height / baselineBox!.height).toBeLessThanOrEqual(1.51);

    await scrollArea.evaluate((element) => element.scrollTo({ left: 0, top: 0 }));
    const [startAreaBox, startImageBox] = await Promise.all([
      scrollArea.boundingBox(),
      image.boundingBox(),
    ]);
    expect(startAreaBox).not.toBeNull();
    expect(startImageBox).not.toBeNull();
    expect(startImageBox!.x).toBeGreaterThanOrEqual(startAreaBox!.x - 1);
    expect(startImageBox!.y).toBeGreaterThanOrEqual(startAreaBox!.y - 1);

    await scrollArea.evaluate((element) => element.scrollTo({
      left: element.scrollWidth,
      top: element.scrollHeight,
    }));
    await expect.poll(() => scrollArea.evaluate((element) =>
      Math.abs(element.scrollLeft - (element.scrollWidth - element.clientWidth)) <= 1 &&
      Math.abs(element.scrollTop - (element.scrollHeight - element.clientHeight)) <= 1,
    )).toBe(true);
    const [endAreaBox, endImageBox] = await Promise.all([
      scrollArea.boundingBox(),
      image.boundingBox(),
    ]);
    expect(endAreaBox).not.toBeNull();
    expect(endImageBox).not.toBeNull();
    expect(endImageBox!.x + endImageBox!.width)
      .toBeLessThanOrEqual(endAreaBox!.x + endAreaBox!.width + 1);
    expect(endImageBox!.y + endImageBox!.height)
      .toBeLessThanOrEqual(endAreaBox!.y + endAreaBox!.height + 1);

    for (const control of [
      viewer.getByRole('button', { name: '선명하게 보기' }),
      viewer.getByRole('button', { name: '원본 보기' }),
      zoomOut,
      zoomIn,
      viewer.getByRole('button', { name: '닫기', exact: true }),
    ]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }

    await scrollArea.evaluate((element) => element.scrollTo({ left: 0, top: 0 }));
    expect(await viewer.evaluate((element) => element.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`ocr-preview-zoom-${width}.png`) });
    await zoomOut.click();
    await expect(viewer.getByRole('status')).toHaveText('100%');
    await image.click();
    await expect(viewer).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(viewer).toBeHidden();
  });
}
