import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('RNI를 우선한 기준선과 상한선을 표시하고 초과를 세 가지 단서로 알린다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  const exceededCard = totals.getByRole('article', { name: '비타민 A 성분 합계' });
  const exceeded = exceededCard.getByRole('heading', { name: '비타민 A', exact: true });
  const neutral = totals.getByText('비타민 D', { exact: true });
  await expect(exceeded).toBeVisible();
  await expect(exceededCard.getByText('상한 초과', { exact: true })).toBeVisible();
  await expect(exceededCard.getByText('3,200', { exact: true })).toBeVisible();
  const baseLabel = exceededCard.locator('[data-threshold-label="base"]');
  const upperLabel = exceededCard.locator('[data-threshold-label="upper-limit"]');
  await expect(baseLabel.getByText('권장', { exact: true })).toBeVisible();
  await expect(baseLabel.getByText('800', { exact: true })).toBeVisible();
  await expect(upperLabel.getByText('상한', { exact: true })).toBeVisible();
  await expect(upperLabel.getByText('3,000', { exact: true })).toBeVisible();
  await expect(exceededCard.getByRole('meter')).toHaveAttribute('aria-valuenow', '3000');
  await expect(exceededCard.getByRole('meter')).toHaveAttribute('aria-valuetext', /3,200/);
  await expect(exceededCard.locator('[data-threshold="upper-limit"]')).toBeVisible();
  await expect(neutral).toBeVisible();

  const exceededBox = await exceeded.boundingBox();
  const neutralBox = await neutral.boundingBox();
  expect(exceededBox?.y).toBeLessThan(neutralBox?.y ?? 0);
});

test('기준 미달과 권장 범위를 판정 가능한 범위 안에서 중립 문구로 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  const calcium = totals.getByRole('article', { name: '칼슘 성분 합계' });
  const vitaminD = totals.getByRole('article', { name: '비타민 D 성분 합계' });
  await expect(calcium.getByText('권장량의 50%예요', { exact: true })).toBeVisible();
  await expect(vitaminD.getByText('권장 범위예요', { exact: true })).toBeVisible();
  await expect(totals.getByText('부족', { exact: false })).toHaveCount(0);
  await expect(totals.getByText('권장~충분', { exact: false })).toHaveCount(0);
  await expect(vitaminD.getByText('상한 초과', { exact: true })).toHaveCount(0);
});

test('기준과 상한의 누락 조합을 숨기거나 임의 판정하지 않는다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  const baseOnly = totals.getByRole('article', { name: '비타민 C 성분 합계' });
  const upperOnly = totals.getByRole('article', { name: '아연 성분 합계' });
  const noStandards = totals.getByRole('article', { name: '셀레늄 성분 합계' });

  const baseOnlyLabel = baseOnly.locator('[data-threshold-label="base"]');
  const baseOnlyUpperLabel = baseOnly.locator('[data-threshold-label="upper-limit"]');
  await expect(baseOnlyLabel.getByText('권장', { exact: true })).toBeVisible();
  await expect(baseOnlyLabel.getByText('100', { exact: true })).toBeVisible();
  await expect(baseOnlyUpperLabel.getByText('상한', { exact: true })).toBeVisible();
  await expect(baseOnlyUpperLabel.getByText('2,000', { exact: true })).toBeVisible();
  await expect(upperOnly.locator('[data-threshold-label="upper-limit"]')).toHaveCount(0);
  await expect(upperOnly.getByRole('meter')).toHaveCount(0);
  await expect(noStandards.getByText('55', { exact: true })).toBeVisible();
  await expect(noStandards.getByText('이 성분은 섭취 기준이 없어요', { exact: true })).toHaveCount(0);
  await expect(noStandards.getByRole('meter')).toHaveCount(0);
});

test('사용자 기준 정보와 합계 범위의 필수 고지를 모두 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  await expect(page.getByText('기준 · 2025 한국인 영양소 섭취기준 · 만 26세 남성')).toBeVisible();
  await expect(
    page.getByText(
      '등록한 영양제의 성분만 더한 값이에요',
    ),
  ).toBeVisible();
  await expect(
    page.getByText('직접 입력한 0개는 성분을 알 수 없어 합계에 포함하지 않았습니다.'),
  ).toHaveCount(0);
});

test('생년월일이나 성별이 없으면 기준을 숨기고 기본정보 입력으로 안내한다', async ({ page }) => {
  await page.goto('/dev/supplements-profile-missing');

  const totals = page.getByRole('region', { name: '성분 합계' });
  await expect(totals.getByText('3,200', { exact: true })).toBeVisible();
  await expect(totals.getByRole('meter')).toHaveCount(0);
  await expect(totals.getByText('상한 초과', { exact: true })).toHaveCount(0);
  await expect(totals.getByText('이 성분은 섭취 기준이 없어요', { exact: true })).toHaveCount(0);
  const profileLink = page.getByRole('button', {
    name: '생년월일과 성별을 입력하면 나이·성별에 맞는 기준을 보여드려요',
  });
  await expect(profileLink).toBeVisible();
  await profileLink.click();
  await expect(page).toHaveURL(/\/my\/profile$/);
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

test('제품을 고르면 하나의 행만 펼쳐지고 1회 섭취량과 추천 슬롯을 확인한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  const search = sheet.getByRole('searchbox', { name: '영양제 제품 검색' });
  await search.fill('종합비타민');

  const results = sheet.getByRole('list', { name: '검색 결과' });
  const first = results.getByRole('listitem').filter({ hasText: '센트룸 실버 우먼' });
  const second = results.getByRole('listitem').filter({ hasText: '고려은단 멀티비타민 올인원' });
  await first.getByRole('button', { name: /센트룸 실버 우먼/ }).click();
  await expect(first.getByText('1회에')).toBeVisible();
  await expect(first.getByText('1 정', { exact: true })).toBeVisible();
  const slots = first.getByRole('group', { name: '복용 시간' });
  await expect(slots.getByRole('button')).toHaveCount(4);
  await expect(slots.getByRole('button', { name: '아침' })).toHaveAttribute('aria-pressed', 'true');
  await expect(slots.getByRole('button', { name: '자기전' })).toHaveAttribute('aria-pressed', 'false');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(first.getByText('제품 표시사항의 섭취방법을 채워놨어요.')).toBeVisible();

  await second.getByRole('button', { name: /고려은단 멀티비타민 올인원/ }).click();
  await expect(first.getByText('1회에')).toHaveCount(0);
  await expect(second.getByText('2 정', { exact: true })).toBeVisible();
  await expect(second.getByRole('button', { name: '1회 섭취량 늘리기' })).toBeVisible();
  await expect(second.getByRole('button', { name: '1회 섭취량 줄이기' })).toBeVisible();
});

test('복용 슬롯은 1회 섭취량과 독립적으로 선택하고 최소 하나를 강제한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('센트룸 실버 우먼');
  const product = sheet.getByRole('listitem').filter({ hasText: '센트룸 실버 우먼' });
  await product.getByRole('button', { name: /센트룸 실버 우먼/ }).click();

  const slots = product.getByRole('group', { name: '복용 시간' });
  await slots.getByRole('button', { name: '저녁' }).click();
  await expect(product.getByText('1 정', { exact: true })).toBeVisible();
  await expect(product.getByRole('button', { name: '1회 섭취량 줄이기' })).toBeDisabled();

  await slots.getByRole('button', { name: '아침' }).click();
  await slots.getByRole('button', { name: '저녁' }).click();
  await expect(product.getByText('복용 시간을 하나 이상 선택해주세요.')).toBeVisible();
  await expect(product.getByRole('button', { name: '추가하기' })).toBeDisabled();
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
  await expect(product.getByRole('button', { name: '1회 섭취량 줄이기' })).toBeDisabled();

  const increase = product.getByRole('button', { name: '1회 섭취량 늘리기' });
  await increase.click();
  await expect(product.getByText('2 정', { exact: true })).toBeVisible();
});

test('표준 제품을 추가하면 회당 수량과 슬롯 수를 합계에 곱하고 목록 맨 위에 놓는다', async ({ page }) => {
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
  await expect(supplementList.getByRole('button').first()).toContainText(
    '하루 1회 · 1회 2정 · 아침',
  );
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
  const slots = sheet.getByRole('group', { name: '복용 시간' });
  await expect(slots.getByRole('button')).toHaveCount(4);
  await slots.getByRole('button', { name: '자기전' }).click();
  await slots.getByRole('button', { name: '아침' }).click();
  await expect(sheet.getByText('성분을 입력', { exact: false })).toHaveCount(0);
  await sheet.getByRole('textbox', { name: '직접 입력 제품명' }).fill('우리집 영양제');
  await sheet.getByRole('button', { name: '추가하기' }).click();

  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  const manual = supplementList.getByRole('button').first();
  await expect(manual).toContainText('우리집 영양제');
  await expect(manual).toContainText('성분 정보 없음');
  await expect(manual).toContainText('하루 1회 · 1회 1정 · 자기전');
  await expect(
    page.getByText('직접 입력한 1개는 성분을 알 수 없어 합계에 포함하지 않았어요.'),
  ).toBeVisible();
  await expect(
    page.getByText(
      '등록한 영양제의 성분만 더한 값이에요',
    ),
  ).toBeVisible();
});

test('목록 카드에서 회당 수량과 슬롯을 편집하면 카드와 성분 합계가 즉시 바뀐다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  await supplementList.getByRole('button', { name: /오메가3/ }).click();

  const sheet = page.getByRole('dialog', { name: '오메가3' });
  await expect(sheet.getByText('1 정', { exact: true })).toBeVisible();
  const slots = sheet.getByRole('group', { name: '복용 시간' });
  await expect(slots.getByRole('button', { name: '아침' })).toHaveAttribute('aria-pressed', 'true');
  await expect(slots.getByRole('button', { name: '저녁' })).toHaveAttribute('aria-pressed', 'true');
  await slots.getByRole('button', { name: '점심' }).click();
  await sheet.getByRole('button', { name: '저장' }).click();

  const omega = supplementList.getByRole('button', { name: /오메가3/ });
  await expect(omega).toContainText('하루 3회 · 1회 1정 · 아침 · 점심 · 저녁');
  await expect(page.getByText('3,500', { exact: true })).toBeVisible();
});

test('목록에는 채운 별만 읽기 전용으로 표시하고 별점이 없으면 숨긴다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  const omega = supplementList.getByRole('button', { name: /오메가3/ });
  const multivitamin = supplementList.getByRole('button', { name: /종합비타민/ });

  const omegaScore = omega.getByLabel('별 4점');
  await expect(omegaScore).toBeVisible();
  await expect(omegaScore.locator('svg')).toHaveCount(4);
  await expect(omega.getByRole('button')).toHaveCount(0);
  await expect(multivitamin.getByLabel(/별 \d점/)).toHaveCount(0);
});

test('별점 별도 창 취소는 기존 값을 유지하고 메모를 비우면 등록 CTA로 돌아간다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  const omega = supplementList.getByRole('button', { name: /오메가3/ });
  await omega.click();

  const sheet = page.getByRole('dialog', { name: '오메가3' });
  await sheet.getByRole('button', { name: '별점 수정' }).click();
  const rating = page.getByRole('dialog', { name: '별점 수정' });
  const stars = rating.getByRole('group', { name: '별점 선택' });
  const scoreFour = stars.getByRole('button', { name: '별 4점' });
  await expect(stars.getByRole('button')).toHaveCount(5);
  await expect(scoreFour).toHaveAttribute('aria-pressed', 'true');
  await stars.getByRole('button', { name: '별 2점' }).click();
  await expect(scoreFour).toHaveAttribute('aria-pressed', 'false');
  await rating.getByRole('button', { name: '닫기' }).click();
  await sheet.getByRole('button', { name: '닫기' }).click();
  await expect(omega.getByLabel('별 4점')).toBeVisible();
  await omega.click();
  const reopenedSheet = page.getByRole('dialog', { name: '오메가3' });
  await reopenedSheet.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '수정하기' }).click();
  const records = page.getByRole('dialog', { name: '메모 편집' });
  const reopenedNote = records.getByRole('textbox', { name: /^메모/ });
  await expect(reopenedNote).toHaveValue('아침 식후에 먹기');
  await reopenedNote.fill('   ');
  await records.getByRole('button', { name: '저장' }).click();
  await expect(records).toBeHidden();
  await expect(reopenedSheet.getByRole('group', { name: '내 메모' }).getByRole('button', { name: '등록하기' })).toBeVisible();
});

test('편집 시트는 비공개 메모와 공개 후기를 구분하고 마스킹 이름을 미리 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  await supplementList.getByRole('button', { name: /오메가3/ }).click();

  const sheet = page.getByRole('dialog', { name: '오메가3' });
  await sheet.getByRole('group', { name: '내 후기' }).getByRole('button', { name: '수정하기' }).click();
  const records = page.getByRole('dialog', { name: '후기 편집' });
  await expect(records.getByText('나만 볼 수 있어요')).toHaveCount(0);
  await expect(records.getByText('김*훈 으로 다른 사람에게 보여요')).toBeVisible();
  const review = records.getByRole('textbox', { name: /후기/ });
  await review.fill('꾸준히 먹기 편했어요.');
  await records.getByRole('button', { name: '저장' }).click();
  await expect(records).toBeHidden();
  await sheet.getByRole('group', { name: '내 후기' }).getByRole('button', { name: '수정하기' }).click();
  await expect(records.getByRole('textbox', { name: /후기/ }))
    .toHaveValue('꾸준히 먹기 편했어요.');
});

test('복용 중단을 확인하면 삭제 문구 없이 활성 목록과 성분 합계에서 제외한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const supplementList = page.getByRole('region', { name: '먹고 있는 영양제' });
  await supplementList.getByRole('button', { name: /비타민 D/ }).click();
  const editSheet = page.getByRole('dialog', { name: '비타민 D' });
  await expect(editSheet.getByText('삭제', { exact: false })).toHaveCount(0);
  await editSheet.getByRole('button', { name: '복용 중단하기' }).click();

  const confirm = page.getByRole('dialog', { name: '비타민 D 복용을 중단할까요?' });
  await expect(confirm.getByText('성분 합계에서 제외됩니다. 다시 추가할 수 있어요.')).toBeVisible();
  await expect(confirm.getByText('삭제', { exact: false })).toHaveCount(0);
  await confirm.getByRole('button', { name: '중단하기' }).click();

  await expect(supplementList.getByRole('button', { name: /비타민 D/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '먹고 있는 영양제 2개' })).toBeVisible();
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
