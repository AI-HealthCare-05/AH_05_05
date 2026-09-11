import { expect, test, type Locator } from 'playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.goto('/tests/harness/clay-controls.html');
});

async function surface(button: Locator) {
  return button.evaluate(element => {
    const style = getComputedStyle(element);
    return { border: style.borderWidth, shadow: style.boxShadow, radius: style.borderRadius, transform: style.transform, height: element.getBoundingClientRect().height };
  });
}

async function seekPill(pill: Locator, time: number) {
  await pill.evaluate((element, currentTime) => {
    [element, ...element.querySelectorAll('[data-continuous-ink]')].forEach(layer => {
      layer.getAnimations().forEach(animation => { animation.pause(); animation.currentTime = currentTime; });
    });
  }, time);
}

function colorChannels(value: string) {
  const srgb = value.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
  if (srgb) return srgb.slice(1, 4).map(Number);
  const rgb = value.match(/rgba?\(\s*([\d.]+)[, ]+\s*([\d.]+)[, ]+\s*([\d.]+)/);
  if (!rgb) throw new Error(`Unrecognized color: ${value}`);
  return rgb.slice(1, 4).map(channel => Number(channel) / 255);
}

function contrast(first: string, second: string) {
  const luminance = (value: string) => colorChannels(value)
    .map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4)
    .reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0);
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + .05) / (values[1] + .05);
}

test('before-after sequence records actual home and slot interactions', async ({ page }, testInfo) => {
  await page.screenshot({ path: testInfo.outputPath('sequence-start.png') });
  const home = page.getByRole('tablist', { name: '오늘의 홈 탭' });
  await home.getByRole('tab', { name: '오늘의 영양제' }).click();
  await page.waitForTimeout(90);
  await page.screenshot({ path: testInfo.outputPath('sequence-moving.png') });
  await home.getByRole('tab', { name: '오늘의 복약' }).click();
  const med = page.getByRole('tablist', { name: '복약 시간대' });
  await med.getByRole('tab', { name: '자기전', exact: true }).click();
  await page.waitForTimeout(80);
  await med.getByRole('tab', { name: '점심', exact: true }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: testInfo.outputPath('sequence-end.png') });
});

test('cancel and save use equal rim and depth geometry in rest, focus, press and disabled states', async ({ page }, testInfo) => {
  const cancel = page.getByRole('button', { name: '취소', exact: true });
  const save = page.getByRole('button', { name: '저장', exact: true });
  await page.screenshot({ path: testInfo.outputPath('buttons-rest.png') });
  expect(await surface(cancel)).toEqual(await surface(save));
  expect((await surface(save)).height).toBeGreaterThanOrEqual(44);
  for (const button of [cancel, save]) {
    await button.focus();
    await expect(button).toBeFocused();
    await expect(button).toHaveCSS('outline-style', 'solid');
  }
  const pressed = [];
  for (const button of [cancel, save]) {
    await button.hover(); await page.mouse.down();
    await expect.poll(() => button.evaluate(element => getComputedStyle(element).transform)).not.toBe('none');
    await page.waitForTimeout(160);
    pressed.push(await surface(button));
    await page.mouse.move(0, 0); await page.mouse.up();
  }
  expect(pressed[0]).toEqual(pressed[1]);
  expect(await surface(page.getByRole('button', { name: '취소 불가' }))).toEqual(await surface(page.getByRole('button', { name: '저장 불가' })));
  await page.getByRole('group', { name: '비활성 작업' }).getByRole('button').evaluateAll(buttons => buttons.forEach(button => (button as HTMLButtonElement).click()));
  await expect(page.getByRole('status', { name: '작업 횟수' })).toHaveText('0');
});

test('home tabs keep one sliding pill and cross intermediate positions on fast reversal', async ({ page }, testInfo) => {
  const tabs = page.getByRole('tablist', { name: '오늘의 홈 탭' });
  const pill = tabs.locator('[data-continuous-pill]');
  await expect(pill).toHaveCount(1);
  const first = await pill.boundingBox();
  const lastTab = tabs.getByRole('tab', { name: '오늘의 영양제' });
  const destination = await lastTab.boundingBox();
  await lastTab.click();
  // Seek the browser's actual animation for deterministic intermediate layout.
  await seekPill(pill, 90);
  const middle = (await pill.boundingBox())!;
  expect(middle.x).toBeGreaterThan(first!.x + 5);
  expect(middle.x).toBeLessThan(destination!.x - 5);
  const labelCenters = await tabs.evaluate(element => {
    const buttons = Array.from(element.querySelectorAll('.rx-continuous-trigger'));
    const ink = Array.from(element.querySelectorAll('[data-continuous-ink] > span'));
    return buttons.map((button, index) => {
      const base = button.getBoundingClientRect(); const overlay = ink[index].getBoundingClientRect();
      return Math.abs(base.x + base.width / 2 - overlay.x - overlay.width / 2);
    });
  });
  expect(labelCenters.every(delta => delta < 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('tabs-moving.png') });
  const previous = await pill.elementHandle();
  await tabs.getByRole('tab', { name: '오늘의 복약' }).click();
  await seekPill(pill, 0);
  expect(Math.abs((await pill.boundingBox())!.x - middle.x)).toBeLessThan(2);
  expect(await previous!.evaluate(element => element.isConnected)).toBe(true);
  await seekPill(pill, 600);
  await expect.poll(async () => Math.abs((await pill.boundingBox())!.x - first!.x)).toBeLessThan(1);
});

test('tab instances stay independent, roving keys preserve slot inputs, and resize aligns the pill', async ({ page }) => {
  const home = page.getByRole('tablist', { name: '오늘의 홈 탭' });
  const med = page.getByRole('tablist', { name: '복약 시간대' });
  const supp = page.getByRole('tablist', { name: '영양제 시간대' });
  await page.getByRole('textbox', { name: 'morning 메모' }).fill('보존할 값');
  await med.getByRole('tab', { name: '아침', exact: true }).focus();
  await page.keyboard.press('End');
  await expect(med.getByRole('tab', { name: '자기전', exact: true })).toBeFocused();
  await expect(supp.getByRole('tab', { name: '아침', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(home.getByRole('tab', { name: '오늘의 복약' })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Home');
  await expect(page.getByRole('textbox', { name: 'morning 메모' })).toHaveValue('보존할 값');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('tabpanel', { name: '점심' })).toBeFocused();
  await page.setViewportSize({ width: 320, height: 844 });
  const pill = med.locator('[data-continuous-pill]');
  const tab = med.getByRole('tab', { selected: true });
  await expect(pill).toHaveCount(1);
  await expect.poll(async () => Math.abs((await pill.boundingBox())!.x - (await tab.boundingBox())!.x)).toBeLessThan(1);
  expect(Math.abs((await pill.boundingBox())!.width - (await tab.boundingBox())!.width)).toBeLessThan(1);
  const ids = await page.getByRole('tab').evaluateAll(elements => elements.map(element => element.id));
  expect(new Set(ids).size).toBe(ids.length);
});

test('the visible tab ink and semantic action surfaces keep readable contrast', async ({ page }) => {
  for (const name of ['저장', '삭제']) {
    const colors = await page.getByRole('button', { name, exact: true }).evaluate(element => {
      const style = getComputedStyle(element);
      return { text: style.color, surface: style.backgroundImage };
    });
    expect(contrast(colors.text, colors.surface)).toBeGreaterThanOrEqual(4.5);
  }
  const tabs = page.getByRole('tablist', { name: '오늘의 홈 탭' });
  const colors = await tabs.evaluate(element => ({
    active: getComputedStyle(element.querySelector('[data-continuous-ink]')!).color,
    activeSurface: getComputedStyle(element.querySelector('[data-continuous-pill]')!).backgroundImage,
    inactive: getComputedStyle(element.querySelector('button')!).color,
    track: getComputedStyle(element).backgroundImage,
  }));
  expect(contrast(colors.active, colors.activeSurface)).toBeGreaterThanOrEqual(4.5);
  expect(contrast(colors.inactive, colors.track)).toBeGreaterThanOrEqual(4.5);
});

for (const width of [320, 390, 1280]) {
  test(`controls remain readable, 44px and contained at ${width}px with reduced motion`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const tabs = page.getByRole('tablist', { name: '오늘의 홈 탭' });
    await tabs.getByRole('tab', { name: '오늘의 영양제' }).click();
    const pill = tabs.locator('[data-continuous-pill]');
    await expect(pill).toHaveCount(1);
    expect(await pill.evaluate(element => element.getAnimations().filter(animation => animation.playState === 'running').length)).toBe(0);
    expect(Math.abs((await pill.boundingBox())!.x - (await tabs.getByRole('tab', { selected: true }).boundingBox())!.x)).toBeLessThan(1);
    const buttons = page.getByRole('tab');
    for (const button of await buttons.all()) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`controls-${width}.png`), fullPage: true });
  });
}

test('auth mode slider preserves same-mode values and real mode reset and intro behavior', async ({ page }, testInfo) => {
  await page.goto('/login');
  const modes = page.getByRole('group', { name: '인증 방식' });
  await page.getByLabel('이메일', { exact: true }).fill('keep@example.com');
  await modes.getByRole('button', { name: '로그인', exact: true }).click();
  await expect(page.getByLabel('이메일', { exact: true })).toHaveValue('keep@example.com');
  await modes.getByRole('button', { name: '회원가입', exact: true }).click();
  await expect(page.getByRole('heading', { name: '이메일을 알려주세요' })).toBeVisible();
  await expect(page.getByLabel('이메일', { exact: true })).toHaveValue('');
  await expect(modes.locator('[data-continuous-pill]')).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath('auth-slider.png') });
});
