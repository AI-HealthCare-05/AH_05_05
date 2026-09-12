import { expect, test } from 'playwright/test';

test.setTimeout(60_000);

for (const width of [375, 390, 1280]) {
  test(`챌린지 이동 탭은 버튼형 표면과 구분되고 ${width}px에서도 조작할 수 있다`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/dev/challenges');

    const navigation = page.getByRole('navigation', { name: '챌린지 보기' });
    const mine = navigation.getByRole('link', { name: '나의 챌린지', exact: true });
    const browse = navigation.getByRole('link', { name: '둘러보기', exact: true });

    await expect(mine).toHaveAttribute('aria-current', 'page');
    await expect(browse).not.toHaveAttribute('aria-current', 'page');
    for (const tab of [mine, browse]) {
      const bounds = await tab.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.height).toBeGreaterThanOrEqual(44);
      await expect(tab).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
      await expect(tab).toHaveCSS('box-shadow', 'none');
    }

    const activeIndicator = await mine.evaluate(element => {
      const style = getComputedStyle(element, '::after');
      return { color: style.backgroundColor, height: style.height };
    });
    expect(activeIndicator.color).toBe('rgb(7, 122, 116)');
    expect(Number.parseFloat(activeIndicator.height)).toBeGreaterThanOrEqual(3);

    await browse.focus();
    await expect(browse).toBeFocused();
    await expect(browse).not.toHaveCSS('outline-style', 'none');
    await browse.click();
    await expect(page).toHaveURL(/\/dev\/challenges\/browse$/);
    await expect(browse).toHaveAttribute('aria-current', 'page');
    await expect(mine).not.toHaveAttribute('aria-current', 'page');
    await page.screenshot({ path: testInfo.outputPath(`challenge-tabs-${width}.png`), fullPage: true });
  });
}

test('선택형 control은 pointer hover에서도 같은 선택 배경을 유지한다', async ({ page }) => {
  await page.goto('/tests/harness/clay-controls.html');
  const selected = page.getByRole('button', { name: '선택됨', exact: true });
  const unselected = page.getByRole('button', { name: '선택 안 됨', exact: true });
  await expect(selected).toHaveAttribute('aria-pressed', 'true');
  await expect(unselected).toHaveAttribute('aria-pressed', 'false');
  const appearances = new Map();
  for (const control of [selected, unselected]) {
    const before = await control.evaluate(element => {
      const style = getComputedStyle(element);
      return { backgroundColor: style.backgroundColor, backgroundImage: style.backgroundImage };
    });
    await control.hover();
    await expect.poll(() => control.evaluate(element => {
      const style = getComputedStyle(element);
      return { backgroundColor: style.backgroundColor, backgroundImage: style.backgroundImage };
    })).toEqual(before);
    appearances.set(control, before);
  }
  expect(appearances.get(selected).backgroundColor).not.toBe(appearances.get(unselected).backgroundColor);
});

for (const width of [390, 1280]) {
  test(`영양제 상위 view도 공통 underline 탭을 사용한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', 'shared-tabs-test');
      sessionStorage.setItem('poke.account-principal', 'shared-tabs@example.com');
    });
    await page.goto('/supplements');

    const tabs = page.getByRole('tablist', { name: '영양제 화면' });
    const mine = tabs.getByRole('tab', { name: '내 영양제', exact: true });
    const browse = tabs.getByRole('tab', { name: '둘러보기', exact: true });
    await expect(mine).toHaveAttribute('aria-selected', 'true');
    await expect(browse).toHaveAttribute('aria-selected', 'false');
    for (const tab of [mine, browse]) {
      expect((await tab.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await expect(tab).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
      await expect(tab).toHaveCSS('box-shadow', 'none');
    }
    const indicator = await mine.evaluate(element => getComputedStyle(element, '::after').backgroundColor);
    expect(indicator).toBe('rgb(7, 122, 116)');

    await browse.click();
    await expect(page).toHaveURL(/\/supplements\?tab=browse$/);
    await expect(browse).toHaveAttribute('aria-selected', 'true');
    await page.screenshot({ path: testInfo.outputPath(`supplement-tabs-${width}.png`), fullPage: true });
  });
}
