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
  await sheet.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await sheet.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심' }).click();
  await page.touchscreen.tap(5, 5);
  await expect(sheet).toBeHidden();
  await expect(omega).toContainText('하루 2회 · 1회 1정');
  await expect(omega).toContainText('아침 · 저녁');
  await omega.click();
  await expect(sheet.getByText('1 정', { exact: true })).toBeVisible();
  await expect(sheet.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심' })).toHaveAttribute('aria-pressed', 'false');
  await sheet.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await sheet.getByRole('group', { name: '복용 시간' }).getByRole('button', { name: '점심' }).click();
  await sheet.getByRole('button', { name: '저장', exact: true }).click();
  await expect(sheet).toBeHidden();
  await expect(omega).toContainText('하루 3회 · 1회 2정');
});
