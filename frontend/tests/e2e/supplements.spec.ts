import { expect, test } from 'playwright/test';

test('초과 성분을 먼저 보여주고 색 외의 경고와 상한 임계값을 함께 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  const exceeded = totals.getByRole('heading', { name: '비타민 A', exact: true });
  const neutral = totals.getByText('비타민 D', { exact: true });
  await expect(exceeded).toBeVisible();
  await expect(page.getByText('상한 초과', { exact: true })).toBeVisible();
  await expect(page.getByText('3,200', { exact: true })).toBeVisible();
  await expect(page.getByText('상한 3,000', { exact: true })).toBeVisible();
  await expect(neutral).toBeVisible();

  const exceededBox = await exceeded.boundingBox();
  const neutralBox = await neutral.boundingBox();
  expect(exceededBox?.y).toBeLessThan(neutralBox?.y ?? 0);
});

test('영양제 합계의 범위와 기준을 오해하지 않도록 두 고지 문구를 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  await expect(page.getByText('기준 · 2025 한국인 영양소 섭취기준 상한섭취량')).toBeVisible();
  await expect(
    page.getByText(
      '등록한 건강기능식품 3개만 더한 값입니다. 음식과 의약품을 통한 섭취량은 포함되지 않았습니다.',
    ),
  ).toBeVisible();
});

test('영양제 추가는 검색만 제공하고 과다 결과를 식별할 정보를 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();

  const sheet = page.getByRole('dialog');
  const search = sheet.getByRole('searchbox', { name: '영양제 제품 검색' });
  await expect(search).toBeVisible();
  await expect(sheet.getByText('바코드', { exact: false })).toHaveCount(0);

  await search.fill('종합비타민');
  await expect(sheet.getByText('24개가 찾아졌어요.')).toBeVisible();
  await expect(
    sheet.getByText('통 앞면의 브랜드를 함께 넣으면 빨리 찾아요 — 예: 센트룸 종합비타민'),
  ).toBeVisible();

  const results = sheet.getByRole('list', { name: '검색 결과' });
  await expect(results.getByRole('listitem')).toHaveCount(20);
  const firstResult = results.getByRole('listitem').first();
  await expect(firstResult.getByText('센트룸 실버 우먼', { exact: true })).toBeVisible();
  await expect(firstResult.getByText('한국화이자 · 정제 · 90정')).toBeVisible();

  await search.fill('센트룸');
  await expect(results.getByText('센트룸 실버 우먼', { exact: true })).toBeVisible();
  await expect(sheet.getByText(/개가 찾아졌어요/)).toHaveCount(0);
});

test('검색 결과는 20개씩 불러와 끝까지 내리면 다음 결과를 이어 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('종합비타민');

  const results = sheet.getByRole('list', { name: '검색 결과' });
  await expect(results.getByRole('listitem')).toHaveCount(20);
  await results.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(results.getByRole('listitem')).toHaveCount(24);
});

test('제품을 고르면 하나의 행만 펼쳐지고 표준 섭취 정수를 확인한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  const search = sheet.getByRole('searchbox', { name: '영양제 제품 검색' });
  await search.fill('종합비타민');

  const results = sheet.getByRole('list', { name: '검색 결과' });
  const first = results.getByRole('listitem').filter({ hasText: '센트룸 실버 우먼' });
  const second = results.getByRole('listitem').filter({ hasText: '고려은단 멀티비타민 올인원' });
  await first.getByRole('button', { name: /센트룸 실버 우먼/ }).click();
  await expect(first.getByText('하루에')).toBeVisible();
  await expect(first.getByText('1 정', { exact: true })).toBeVisible();
  await expect(first.getByText('제품 표시사항의 섭취방법을 채워놨어요.')).toBeVisible();

  await second.getByRole('button', { name: /고려은단 멀티비타민 올인원/ }).click();
  await expect(first.getByText('하루에')).toHaveCount(0);
  await expect(second.getByText('2 정', { exact: true })).toBeVisible();
  await expect(second.getByRole('button', { name: '하루 섭취량 늘리기' })).toBeVisible();
  await expect(second.getByRole('button', { name: '하루 섭취량 줄이기' })).toBeVisible();
});

test('표준 섭취량이 없으면 1정으로 시작하고 프리필 안내를 표시하지 않는다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('얼라이브 원스데일리 포 우먼');
  const product = sheet.getByRole('listitem').filter({ hasText: '얼라이브 원스데일리 포 우먼' });
  await product.getByRole('button', { name: /얼라이브 원스데일리 포 우먼/ }).click();

  await expect(product.getByText('1 정', { exact: true })).toBeVisible();
  await expect(product.getByText('제품 표시사항의 섭취방법을 채워놨어요.')).toHaveCount(0);
  await expect(product.getByRole('button', { name: '하루 섭취량 줄이기' })).toBeDisabled();

  const increase = product.getByRole('button', { name: '하루 섭취량 늘리기' });
  for (let count = 1; count < 20; count += 1) await increase.click();
  await expect(product.getByText('20 정', { exact: true })).toBeVisible();
  await expect(increase).toBeDisabled();
});

test('표준 제품을 추가하면 1일 정수를 합계에 곱하고 토스트 없이 목록 맨 위에 놓는다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('고려은단');
  const product = sheet.getByRole('listitem').filter({ hasText: '고려은단 멀티비타민 올인원' });
  await product.getByRole('button', { name: /고려은단 멀티비타민 올인원/ }).click();
  await expect(product.getByText('2 정', { exact: true })).toBeVisible();
  await product.getByRole('button', { name: '추가하기' }).click();

  await expect(sheet).toBeHidden();
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  await expect(supplementList.getByRole('button').first()).toContainText('고려은단 멀티비타민 올인원');
  await expect(supplementList.getByRole('button').first()).toContainText('1일 2정 · 아침');
  await expect(page.getByText('4,000', { exact: true })).toBeVisible();
  await expect(page.getByText('추가했어요')).toHaveCount(0);
});

test('검색하지 못한 제품은 이름만 직접 입력하고 성분 합계 제외를 알린다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('없는제품-12345');

  await expect(sheet.getByText('찾지 못했어요')).toBeVisible();
  await sheet.getByRole('button', { name: '직접 입력' }).first().click();
  await expect(sheet.getByRole('textbox', { name: '직접 입력 제품명' })).toBeVisible();
  await expect(sheet.getByRole('spinbutton')).toHaveCount(0);
  await expect(sheet.getByText('성분을 입력', { exact: false })).toHaveCount(0);
  await sheet.getByRole('textbox', { name: '직접 입력 제품명' }).fill('우리집 영양제');
  await sheet.getByRole('button', { name: '추가하기' }).click();

  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  const manual = supplementList.getByRole('button').first();
  await expect(manual).toContainText('우리집 영양제');
  await expect(manual).toContainText('성분 정보 없음');
  await expect(
    page.getByText('직접 입력한 1개는 성분을 알 수 없어 합계에 포함하지 않았습니다.'),
  ).toBeVisible();
  await expect(
    page.getByText(
      '등록한 건강기능식품 3개만 더한 값입니다. 음식과 의약품을 통한 섭취량은 포함되지 않았습니다.',
    ),
  ).toBeVisible();
});

test('성분 8개에서도 초과 항목을 중립 항목보다 먼저 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  await expect(totals.getByRole('article')).toHaveCount(8);
  const exceededBox = await totals.getByRole('article', { name: '비타민 A 성분 합계' }).boundingBox();
  const firstNeutralBox = await totals.getByRole('article', { name: '비타민 D 성분 합계' }).boundingBox();
  expect(exceededBox?.y).toBeLessThan(firstNeutralBox?.y ?? 0);
});

test('상한 초과가 3개여도 모든 경고를 구분하고 가로 넘침이 없다', async ({ page }) => {
  await page.goto('/dev/supplements-three-exceeded');

  await expect(page.getByText('상한 초과', { exact: true })).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
