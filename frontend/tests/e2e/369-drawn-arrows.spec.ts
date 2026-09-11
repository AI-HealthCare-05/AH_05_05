import { expect, test } from 'playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/api/'), route => route.abort());
  await page.goto('/tests/harness/drawn-arrows.html');
});

test('새로 나타나는 뒤로 화살표는 중간 선에서 완성되며 hitbox는 즉시 활성화된다', async ({ page }, info) => {
  const back = page.getByRole('button', { name: '뒤로 가기', exact: true });
  await expect(back).toBeEnabled();
  expect((await back.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const path = back.locator('svg path').first();
  const frames = await path.evaluate(async element => {
    const animation = element.getAnimations()[0];
    if (!animation) return [];
    animation.pause();
    const offsets: number[] = [];
    for (const time of [0, 100, 240]) {
      animation.currentTime = time;
      offsets.push(Number.parseFloat(getComputedStyle(element).strokeDashoffset));
    }
    animation.finish();
    return offsets;
  });
  expect(frames).toHaveLength(3);
  expect(frames[0]).toBeGreaterThan(frames[1]);
  expect(frames[1]).toBeGreaterThan(frames[2]);
  expect(frames[2]).toBe(0);
  await back.focus();
  await back.press('Enter');
  await expect(page.getByLabel('부수 효과')).toHaveText('뒤로 1, 저장 0, 종료 0');
  await page.screenshot({ path: info.outputPath('drawn-arrow-settled.png') });
});

test('펼침 회전은 부드럽게 바뀌고 완료한 선은 rerender나 scroll로 다시 그리지 않는다', async ({ page }) => {
  const trigger = page.getByRole('button', { name: '펼치기' });
  const path = trigger.locator('svg path').first();
  const hasDrawing = await path.evaluate(element => {
    const animation = element.getAnimations()[0];
    if (!animation) return false;
    animation.finish();
    (window as unknown as { settledArrow: Animation }).settledArrow = animation;
    return true;
  });
  expect(hasDrawing).toBe(true);
  await trigger.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  const rotation = trigger.locator('svg g');
  const transition = await rotation.evaluate(element => getComputedStyle(element).transitionDuration);
  expect(Number.parseFloat(transition)).toBeGreaterThan(0);
  await expect(rotation).toHaveCSS('transform', 'matrix(-1, 0, 0, -1, 0, 0)');
  await page.getByRole('button', { name: '내용 갱신' }).click();
  await page.evaluate(() => window.scrollTo(0, 100));
  expect(await path.evaluate(element => element.getAnimations()[0] === (window as unknown as { settledArrow: Animation }).settledArrow)).toBe(true);
  await expect(path).toHaveCSS('stroke-dashoffset', '0px');
});

test('움직임 줄이기는 선과 회전을 즉시 완성하고 키보드 입력을 지연하지 않는다', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  const path = page.getByRole('button', { name: '뒤로 가기', exact: true }).locator('svg path').first();
  await expect(path).toHaveCSS('stroke-dashoffset', '0px');
  await expect(path).toHaveCSS('animation-name', 'none');
  const trigger = page.getByRole('button', { name: '펼치기' });
  await trigger.focus();
  await trigger.press('Enter');
  const rotation = trigger.locator('svg g');
  await expect(rotation).toHaveCSS('transition-duration', '0s');
  await expect(rotation).toHaveCSS('transform', 'matrix(-1, 0, 0, -1, 0, 0)');
});

test('평가 단계에 새로 나타난 화살표도 그려지고 뒤로·닫기는 저장이나 종료를 하지 않는다', async ({ page }, info) => {
  await page.getByRole('button', { name: '평가 열기' }).click();
  await page.getByRole('button', { name: '좋아요', exact: true }).click();
  const back = page.getByRole('button', { name: '평가 선택으로 돌아가기' });
  const hasDraw = await back.locator('svg path').evaluateAll(paths => paths.every(path => path.getAnimations().length > 0));
  expect(hasDraw).toBe(true);
  for (const time of [0, 100, 240]) {
    await back.locator('svg path').evaluateAll((paths, currentTime) => paths.forEach(path => path.getAnimations().forEach(animation => { animation.pause(); animation.currentTime = currentTime; })), time);
    await page.screenshot({ path: info.outputPath(`feedback-arrow-${time}ms.png`) });
  }
  await back.focus();
  await back.press('Enter');
  await expect(page.getByRole('dialog', { name: '상담 종료' })).toBeVisible();
  await page.getByRole('button', { name: '평가 닫기' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByLabel('부수 효과')).toHaveText('뒤로 0, 저장 0, 종료 0');
});

test('공통 선택창도 열림 방향을 바꾸고 선택·닫힘 계약을 유지한다', async ({ page }) => {
  const select = page.getByRole('combobox', { name: '시간대', includeHidden: true });
  await select.click();
  await expect(select).toHaveAttribute('aria-expanded', 'true');
  await expect(select.locator('svg g')).toHaveCSS('transform', 'matrix(-1, 0, 0, -1, 0, 0)');
  await page.getByRole('option', { name: '저녁' }).click();
  await expect(select).toHaveText('저녁');
  await expect(select).toHaveAttribute('aria-expanded', 'false');
  await expect(select.locator('svg g')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)');
  await expect(page.getByLabel('부수 효과')).toHaveText('뒤로 0, 저장 0, 종료 0');
});
