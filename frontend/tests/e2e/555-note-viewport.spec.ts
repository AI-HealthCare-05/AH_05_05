import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
test.use({ isMobile: true, hasTouch: true, locale: 'ko-KR' });

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'viewport-555-test');
    sessionStorage.setItem('poke.account-principal', 'viewport-555@example.invalid');
    sessionStorage.setItem('rxvita.mock.medication-aliases:viewport-555%40example.invalid', JSON.stringify({
      12: '길이가 긴 처방 이름을 가진 합성 데이터 처방 메모 작성 테스트',
    }));
  });
});

async function expectFits(page: Page, width: number) {
  // Root clipping must not turn a too-wide field into a passing layout test.
  await page.addStyleTag({ content: 'html,body,#root,main { overflow:visible!important; }' });
  const layout = await page.evaluate(() => ({
    inner: innerWidth,
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
    fields: [...document.querySelectorAll('main input, main select, main textarea')].map(el => {
      const rect = el.getBoundingClientRect();
      return { left: rect.left, right: rect.right };
    }),
  }));
  expect(layout.inner).toBe(width);
  expect(layout.client).toBe(width);
  expect(layout.scroll).toBe(width);
  expect(layout.fields).toHaveLength(3);
  for (const field of layout.fields) {
    expect(field.left).toBeGreaterThanOrEqual(0);
    expect(field.right).toBeLessThanOrEqual(width);
  }
}

for (const width of [375, 390, 393, 414, 430]) {
  test(`메모 입력은 ${width}px에서 iOS 확대 유발 작은 글자를 사용하지 않는다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 852 });
    await page.goto('/medications/notes/new');
    await page.getByLabel('처방').selectOption({ index: 1 });
    for (const name of ['처방', '복용 일시', '건강상태 기록']) {
      const control = page.getByLabel(name, { exact: true });
      await control.focus();
      // Contract based on WebKit iOS focus scaling (standardFontSize / fontSize).
      // This checks rendered CSS, NOT actual iOS keyboard/zoom behavior.
      expect(await control.evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    }
    await expectFits(page, width);
  });

  test(`메모 ${width}px 최초 진입·새로고침·복귀·resize에서 입력과 값을 유지한다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 852 });
    await page.goto('/medications/notes/new');
    await page.getByLabel('복용 일시').waitFor();
    await expectFits(page, width);
    await page.getByLabel('처방').selectOption({ index: 1 });
    await page.getByLabel('복용 일시').fill('2026-09-18T08:30');
    await page.getByLabel('건강상태 기록').fill('레이아웃 회귀 검증용 합성 메모');
    await expectFits(page, width);
    await page.getByRole('heading', { name: '복용시 건강상태 변화를 기록해 보세요.' }).click();
    await page.setViewportSize({ width: width + 20, height: 700 });
    await page.setViewportSize({ width, height: 852 });
    await expect(page.getByLabel('복용 일시')).toHaveValue('2026-09-18T08:30');
    await expect(page.getByLabel('건강상태 기록')).toHaveValue('레이아웃 회귀 검증용 합성 메모');
    await expectFits(page, width);
    await page.reload();
    await page.getByLabel('처방').selectOption({ index: 1 });
    await expectFits(page, width);
    await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
    await expect(page).toHaveURL(/\/medications\/notes$/);
    await page.getByRole('button', { name: /펼치기$/ }).first().click();
    await page.getByRole('button', { name: '이 처방에 메모 작성', exact: true }).click();
    await expect(page.getByLabel('처방', { exact: true })).toBeEnabled();
    await expectFits(page, width);
  });
}
