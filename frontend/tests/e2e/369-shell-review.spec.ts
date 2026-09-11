import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(45_000);

const prescription = {
  recordId: 369, alias: '꾸준한 복약', documentImageUrl: null,
  start: { date: '2026-09-05', slot: 'morning' }, endDate: '2026-09-14',
  daysRemaining: 5, isFinished: false,
  mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
  medications: [{ medicationId: 3690, name: '복합성분서방정500mg', dose: '500mg 1정', days: 10,
    daysRemaining: 5, slots: ['morning', 'lunch', 'evening', 'bedtime'], asNeeded: false,
    untilComplete: true }],
};

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '369-shell-token');
    sessionStorage.setItem('poke.account-principal', '369-shell@example.invalid');
  });
  await page.route('**/api/v1/**', route => route.fulfill({ json: {} }));
  await page.route('**/api/v1/medications', route => route.fulfill({ json: [prescription] }));
  await page.route('**/api/v1/users/me', route => route.fulfill({ json: {
    name: '테스트 사용자', phoneNumber: '01012345678', birthDate: '1990-01-01', gender: 'female',
  } }));
  await page.route('**/api/v1/me/settings', route => route.fulfill({ json: {
    notifyMedication: false, notifySupplement: false, notifySchedule: false, notifyConsentedAt: null,
    morningMedicationTime: '08:00', lunchMedicationTime: '13:00', eveningMedicationTime: '19:00', bedtimeMedicationTime: '22:30',
  } }));
  await page.route('**/api/v1/med/medication/schedule/369', route => route.fulfill({ json: {
    start: prescription.start, mealTimes: prescription.mealTimes,
    medications: [{ ...prescription.medications[0], timesPerDay: 4, timing: '식후' }],
  } }));
});

async function expectNavigationInViewport(page: Page) {
  const nav = page.getByRole('navigation', { name: '주요 화면' });
  await expect(nav).toBeInViewport({ ratio: 1 });
  const rect = await nav.boundingBox();
  expect(rect!.y + rect!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
  await expect(nav.getByRole('button')).toHaveText(['홈', '복약', '영양제', '챌린지', '마이']);
}

for (const width of [320, 1280]) {
  test(`long tab pages keep navigation visible before and after scrolling (${width})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 480 });
    for (const path of ['/dev/medications-many', '/my', '/my/profile']) {
      await page.goto(path);
      await expect(page.getByRole('navigation', { name: '주요 화면' })).toBeVisible();
      await expectNavigationInViewport(page);
      const main = page.locator('main');
      await expect.poll(() => main.evaluate(element => element.scrollHeight - element.clientHeight)).toBeGreaterThan(0);
      await main.hover();
      await page.mouse.wheel(0, 700);
      await expect.poll(() => main.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
      await expectNavigationInViewport(page);
      await main.evaluate(element => { element.scrollTop = element.scrollHeight; });
      const geometry = await main.evaluate(element => ({
        contentBottom: element.lastElementChild!.getBoundingClientRect().bottom,
        navTop: document.querySelector('nav[aria-label="주요 화면"]')!.getBoundingClientRect().top,
      }));
      expect(geometry.contentBottom).toBeLessThanOrEqual(geometry.navTop + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`${path.split('/').pop()}-${width}.png`) });
    }
    const nav = page.getByRole('navigation', { name: '주요 화면' });
    await nav.getByRole('button', { name: '홈', exact: true }).focus();
    await page.keyboard.press('Tab');
    await expect(nav.getByRole('button', { name: '복약', exact: true })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/medications$/);
  });
}

test('expanded medication uses legend-colored dots while editing preserves scheduled times', async ({ page }, testInfo) => {
  await page.goto('/medications');
  await page.getByRole('button', { name: /2026년 9월 5일 처방.*복용 중/ }).click();
  const detail = page.getByRole('region', { name: '2026년 9월 5일 처방 상세' });
  await expect(detail.locator('li p').first()).toHaveText('복합성분서방정500mg');
  await expect(detail).not.toContainText(/\d{2}:\d{2}/);
  const midpointColors = [[224, 172, 133], [113, 170, 166], [113, 138, 167], [166, 172, 172]];
  for (const [index, slot] of ['아침', '점심', '저녁', '자기전'].entries()) {
    const dot = detail.getByRole('img', { name: slot, exact: true });
    await expect(dot).toBeVisible();
    await expect(dot).toHaveText('');
    const rgb = await dot.evaluate(el => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d')!;
      context.fillStyle = getComputedStyle(el).backgroundColor;
      context.fillRect(0, 0, 1, 1);
      return Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3);
    });
    for (let channel = 0; channel < 3; channel++) {
      expect(Math.abs(rgb[channel] - midpointColors[index][channel]), `${slot}: ${rgb.join(',')}`).toBeLessThanOrEqual(1);
    }
  }
  await expect(detail.getByText('끝까지 복용')).toBeVisible();
  const chevron = page.locator('button[aria-controls="medication-episode-369"] svg');
  const pencil = page.getByRole('button', { name: '처방 수정 · 2026년 9월 5일', exact: true }).locator('svg');
  const c = (await chevron.boundingBox())!;
  const p = (await pencil.boundingBox())!;
  expect(Math.abs(c.x + c.width / 2 - p.x - p.width / 2)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: testInfo.outputPath('expanded-meal-dots.png'), animations: 'disabled' });
  let saved: unknown;
  await page.route('**/api/v1/med/medication/schedule/369', async route => {
    if (route.request().method() === 'GET') return route.fallback();
    saved = route.request().postDataJSON();
    await route.fulfill({ json: { saved: true } });
  });
  await page.getByRole('button', { name: '처방 수정 · 2026년 9월 5일', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '처방 편집' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('복용 중', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('prescription-edit.png'), animations: 'disabled' });
  await expect(page.getByRole('button', { name: '챗봇', exact: true })).toBeHidden();
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(saved).toMatchObject({ mealTimes: {
    morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30',
  } });
  await expectNavigationInViewport(page);
});

test('launcher displays the existing chick-pill picture and keeps its chat destination', async ({ page }, testInfo) => {
  await page.goto('/medications');
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  const picture = launcher.locator('img');
  await expect(picture).toHaveAttribute('src', '/images/default-profile.png');
  await expect.poll(() => picture.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect(launcher).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: testInfo.outputPath('chick-pill-launcher.png') });
  await launcher.click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole('button', { name: '챗봇', exact: true })).toHaveCount(0);
});
