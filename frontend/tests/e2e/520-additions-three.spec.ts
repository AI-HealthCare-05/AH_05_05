import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-08T03:00:00Z'));
});

test('이후 일정은 접어서 시작하고 펼쳐도 하단 작업 버튼은 탭바 바로 위에 유지된다', async ({ page }, testInfo) => {
  await page.goto('/dev/my-visits');
  const later = page.getByRole('button', { name: '이후 일정 펼치기' });
  await expect(later).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('button', { name: /9월 16일.*늘봄병원/ })).toHaveCount(0);
  const actions = page.getByRole('region', { name: '진료일정 작업' });
  const before = await actions.boundingBox();
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  await expect.poll(async () => {
    const box = await launcher.boundingBox();
    return box!.y + box!.height <= before!.y;
  }).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('visits-collapsed.png') });
  await later.click();
  await expect(page.getByRole('button', { name: /9월 16일.*늘봄병원/ })).toBeVisible();
  await page.getByRole('button', { name: '지난 일정 보기' }).click();
  await expect(page.getByText('지난 진료')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 600 });
  const main = page.getByRole('main');
  await main.evaluate(element => { element.scrollTop = element.scrollHeight; });
  const after = await actions.boundingBox();
  const nav = await page.getByRole('navigation', { name: '주요 화면' }).boundingBox();
  expect(before).not.toBeNull();
  expect(after!.y + after!.height).toBeCloseTo(nav!.y, 0);
  await expect(actions.getByRole('button', { name: '진료일정 추가' })).toBeInViewport();
  await page.setViewportSize({ width: 390, height: 844 });
  expect((await actions.boundingBox())!.y).toBeCloseTo(before!.y, 0);
  await page.screenshot({ path: testInfo.outputPath('visits-expanded.png') });
  await page.getByRole('button', { name: '이후 일정 접기' }).click();
  await expect(later).toHaveAttribute('aria-expanded', 'false');
});

test('다른 정렬 항목에 다녀와도 항목별 마지막 정렬 방향을 유지한다', async ({ page }) => {
  await page.goto('/dev/supplements?tab=browse');
  await page.getByPlaceholder('제품명 또는 성분 검색').fill('센트룸');
  const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
  await sorts.getByRole('button', { name: '이름순 ▲', exact: true }).click();
  await expect(sorts.getByRole('button', { name: '이름순 ▼', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await sorts.getByRole('button', { name: '등록순', exact: true }).click();
  await sorts.getByRole('button', { name: '등록순 ▼', exact: true }).click();
  await sorts.getByRole('button', { name: '이름순', exact: true }).click();
  await expect(sorts.getByRole('button', { name: '이름순 ▼', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await sorts.getByRole('button', { name: '등록순', exact: true }).click();
  await expect(sorts.getByRole('button', { name: '등록순 ▲', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('영양제 복용 정보 수정은 바깥 영역으로 닫으면 버리고 저장할 때만 반영한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const omega = page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /오메가3/ });
  await omega.click();
  const sheet = page.getByRole('dialog', { name: '오메가3' });
  await expect(sheet.getByRole('button', { name: '제품 정보 보기', exact: true })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '1회 섭취량 늘리기' })).toHaveCount(0);
  await sheet.getByRole('button', { name: '복용 정보 수정', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '복용 정보 수정', exact: true });
  await editor.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await editor.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심' }).click();
  await page.touchscreen.tap(5, 5);
  await expect(editor).toBeHidden();
  await expect(sheet).toBeVisible();
  await sheet.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(omega).toContainText('하루 2회 · 1회 1정');
  await expect(omega).toContainText('아침 · 저녁');
  await omega.click();
  await sheet.getByRole('button', { name: '복용 정보 수정', exact: true }).click();
  await expect(editor.getByText('1 정', { exact: true })).toBeVisible();
  await expect(editor.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심' })).toHaveAttribute('aria-pressed', 'false');
  await editor.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await editor.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심' }).click();
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toBeHidden();
  await expect(sheet.getByRole('button', { name: /오메가3 제품 상세정보/ })).toContainText('2정');
  await sheet.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(omega).toContainText('하루 3회 · 1회 2정');
});

test('복용 시간을 모두 해제한 초안을 취소해도 별점 저장을 막지 않는다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /오메가3/ }).click();
  const overview = page.getByRole('dialog', { name: '오메가3' });
  await overview.getByRole('button', { name: '복용 정보 수정', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '복용 정보 수정', exact: true });
  await editor.getByRole('button', { name: '아침', exact: true }).click();
  await editor.getByRole('button', { name: '저녁', exact: true }).click();
  await expect(editor.getByRole('button', { name: '저장', exact: true })).toBeDisabled();
  await editor.getByRole('button', { name: '닫기', exact: true }).click();
  await overview.getByRole('button', { name: '별점 수정' }).click();
  const rating = page.getByRole('dialog', { name: '별점 수정' });
  await rating.getByRole('button', { name: '별 5점' }).click();
  await rating.getByRole('button', { name: '저장', exact: true }).click();
  await expect(rating).toBeHidden();
  await expect(overview.getByLabel('별 5점')).toBeVisible();
  await expect(overview.getByRole('button', { name: /제품 상세정보/ })).toContainText('아침 · 저녁');
});

test('영양제 요약 카드는 상세로 이동하고 복용 정보 수정과 내 기록 순으로 표시한다', async ({ page }, testInfo) => {
  await page.goto('/dev/supplements');
  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /오메가3/ }).click();
  const sheet = page.getByRole('dialog', { name: '오메가3' });
  const product = sheet.getByRole('button', { name: '오메가3 제품 상세정보' });
  const edit = sheet.getByRole('button', { name: '복용 정보 수정', exact: true });
  const records = sheet.getByRole('heading', { name: '내 기록', exact: true });
  await expect(sheet.getByRole('button', { name: /^(저장|복용 중단하기|복용취소)$/ })).toHaveCount(0);
  expect((await product.boundingBox())!.y).toBeLessThan((await edit.boundingBox())!.y);
  expect((await edit.boundingBox())!.y).toBeLessThan((await records.boundingBox())!.y);
  await page.screenshot({ path: testInfo.outputPath('supplement-overview.png'), animations: 'disabled' });
  await edit.click();
  const editor = page.getByRole('dialog', { name: '복용 정보 수정', exact: true });
  await expect(editor.getByRole('button', { name: '저장', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('supplement-dose-editor.png'), animations: 'disabled' });
  await editor.getByRole('button', { name: '닫기', exact: true }).click();
  await product.click();
  await expect(page).toHaveURL(/\/dev\/supplements\/product\//);
});
