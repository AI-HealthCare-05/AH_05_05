import { expect, test, type Locator } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
test.use({ isMobile: true, hasTouch: true, locale: 'ko-KR' });

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'focus-556-test');
    sessionStorage.setItem('poke.account-principal', 'focus-556@example.invalid');
  });
});

async function expectReadableInput(control: Locator) {
  await expect(control).toBeVisible();
  const metrics = await control.evaluate(el => {
    const box = el.getBoundingClientRect();
    return { font: parseFloat(getComputedStyle(el).fontSize), left: box.left, right: box.right, viewport: innerWidth };
  });
  expect(metrics.font).toBeGreaterThanOrEqual(16);
  expect(metrics.left).toBeGreaterThanOrEqual(0);
  expect(metrics.right).toBeLessThanOrEqual(metrics.viewport);
}

const screens = [
  { name: '로그인', path: '/login', labels: ['이메일', '비밀번호'] },
  { name: '영양제 검색', path: '/dev/supplements?tab=browse', labels: ['영양제 제품 검색'] },
  { name: '내 정보', path: '/dev/my-profile', labels: ['이름', '전화번호', '생년월일'] },
  { name: 'OCR 결과', path: '/dev/ocr-review', labels: ['복약 별칭', '병원명', '조제일'] },
  { name: '복용 일정', path: '/dev/medication-schedule', labels: ['복용 시작 날짜'] },
  { name: '챗봇', path: '/dev/chat', labels: ['질문 입력'] },
];

for (const screen of screens) {
  test(`${screen.name} 입력은 실제 렌더링에서 16px 이상이며 화면 안에 들어온다`, async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 852 });
    if (screen.path === '/login') await page.addInitScript(() => sessionStorage.clear());
    await page.goto(screen.path, { waitUntil: 'domcontentloaded' });
    for (const label of screen.labels) {
      const control = page.getByLabel(label, { exact: true });
      await expect(control).toBeEnabled();
      await control.focus();
      await expectReadableInput(control);
    }
  });
}

test('영양제 추가와 직접 입력의 포커스를 유지하면서 작은 입력 글자를 제거한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: /영양제 추가/ }).click();
  const search = page.getByRole('searchbox', { name: '영양제 제품 검색' });
  await expect(search).toBeFocused();
  await expectReadableInput(search);
  await page.getByRole('button', { name: '직접 입력', exact: true }).click();
  const product = page.getByLabel('직접 입력 제품명');
  await expect(product).toBeFocused();
  await expectReadableInput(product);
});

test('진료일정의 날짜와 병원명은 팝업 자동 포커스에서도 16px 이상이다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가', exact: true }).click();
  const date = page.getByLabel('진료일', { exact: true });
  await expect(date).toBeFocused();
  await expectReadableInput(date);
  await expectReadableInput(page.getByLabel('병원명 (필수)', { exact: true }));
});

for (const width of [375, 430, 1280]) {
  test(`긴 검색어와 챗봇 초안은 ${width}px에서 입력·전송 버튼을 밀어내지 않는다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/dev/supplements?tab=browse');
    const search = page.getByRole('searchbox', { name: '영양제 제품 검색' });
    const longText = '길이가 긴 합성 입력 내용입니다. '.repeat(6);
    await search.fill(longText);
    await expectReadableInput(search);
    await expect(search).toHaveValue(longText);
    await page.goto('/dev/chat');
    const composer = page.getByLabel('질문 입력');
    await expect(composer).toBeEnabled();
    await composer.fill(longText);
    await expectReadableInput(composer);
    await expect(composer).toHaveValue(longText);
    const send = page.getByRole('button', { name: '보내기', exact: true });
    await expect(send).toBeEnabled();
    const edges = await send.evaluate(el => ({ right: el.getBoundingClientRect().right, viewport: innerWidth }));
    expect(edges.right).toBeLessThanOrEqual(edges.viewport);
  });
}

for (const width of [375, 390, 393, 414, 430]) {
  test(`메모 입력은 ${width}px에서 iOS 확대 유발 작은 글자를 사용하지 않는다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 852 });
    await page.goto('/medications/notes/new');
    await page.getByLabel('처방', { exact: true }).selectOption({ index: 1 });
    for (const name of ['처방', '복용 일시', '건강상태 기록']) {
      const control = page.getByLabel(name, { exact: true });
      await control.focus();
      // WebKit iOS focus scaling uses standardFontSize / fontSize.
      // This validates rendered CSS, not the actual iOS keyboard or scale.
      expect(await control.evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    }
  });
}
