import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON, REAL_API_ONLY_REASON } from './helpers/mode';

interface Material {
  backgroundColor: string;
  backgroundImage: string;
  borderColor: string;
  borderRadius: string;
  borderWidth: string;
  boxShadow: string;
  height: number;
}

async function material(control: Locator): Promise<Material> {
  return control.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundColor: style.backgroundColor,
      backgroundImage: style.backgroundImage,
      borderColor: style.borderTopColor,
      borderRadius: style.borderTopLeftRadius,
      borderWidth: style.borderTopWidth,
      boxShadow: style.boxShadow,
      height: element.getBoundingClientRect().height,
    };
  });
}

async function expectAddAndSelectionSurfaces(reference: Locator, candidate: Locator) {
  await expect(reference).toHaveAttribute('data-variant', 'primary');
  await expect(candidate).toHaveAttribute('data-variant', 'secondary');
  const [referenceMaterial, candidateMaterial] = await Promise.all([material(reference), material(candidate)]);
  expect(candidateMaterial.backgroundColor).toBe('rgb(255, 255, 255)');
  expect(referenceMaterial.backgroundColor).not.toBe(candidateMaterial.backgroundColor);
  expect(referenceMaterial.height).toBe(candidateMaterial.height);
  expect(referenceMaterial.borderRadius).toBe(candidateMaterial.borderRadius);
  expect(candidateMaterial.height).toBeCloseTo(52, 1);
  expect(candidateMaterial.borderWidth).toBe('1px');
  expect(candidateMaterial.backgroundImage).not.toBe('none');
  expect(candidateMaterial.boxShadow).not.toBe('none');
}

async function expectNoOverlap(first: Locator, second: Locator) {
  const [a, b] = await Promise.all([first.boundingBox(), second.boundingBox()]);
  expect(a).not.toBeNull();
  expect(b).not.toBeNull();
  const overlaps = a!.x < b!.x + b!.width
    && a!.x + a!.width > b!.x
    && a!.y < b!.y + b!.height
    && a!.y + a!.height > b!.y;
  expect(overlaps).toBe(false);
}

async function expectNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

async function settleRevealAnimations(page: Page) {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => undefined)));
  });
}

async function movePointerAwayAndSettle(page: Page, control: Locator) {
  await page.mouse.move(0, 0);
  await expect.poll(() => control.evaluate((element) => element.matches(':hover'))).toBe(false);
  await control.evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
  });
  await expect.poll(() => control.evaluate((element) => element.matches(':hover'))).toBe(false);
}

async function capture(page: Page, name: string) {
  const directory = process.env.UI447_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await settleRevealAnimations(page);
  await page.screenshot({ path: path.join(directory, name), fullPage: true, animations: 'disabled' });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function productionMedicationOverview() {
  return {
    recordId: 12,
    alias: '혈압 관리 처방',
    documentImageUrl: '/api/v1/ocr/jobs/12/image',
    start: { date: '2026-08-22', slot: 'morning' },
    endDate: '2026-08-31',
    daysRemaining: 3,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [{
      medicationId: 120,
      name: '셀레콕시브',
      dose: '200mg',
      days: 7,
      daysRemaining: 3,
      slots: ['morning', 'evening'],
      asNeeded: false,
    }],
  };
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-02T12:00:00+09:00'));
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
});

for (const width of [320, 390, 1280]) {
  test(`처방 추가는 primary, 선택·취소는 secondary 52px 표면이며 선택 수만큼 삭제한다 (${width}px)`, async ({ page }) => {
    test.skip(IS_REAL_API, MOCK_ONLY_REASON);
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/dev/medications');
    await expect(page.getByRole('button', { name: /2026년 8월 24일 처방/ })).toBeVisible();
    await settleRevealAnimations(page);

    const add = page.getByRole('button', { name: '처방 추가', exact: true });
    const select = page.getByRole('button', { name: '선택', exact: true });
    await expectAddAndSelectionSurfaces(add, select);
    const selectMaterial = await material(select);
    await expectNoOverlap(add, select);
    await expectNoOverflow(page);
    if (width <= 390) await capture(page, `task-3-medications-normal-${width}.png`);

    await select.click();
    await expect(page.getByRole('heading', { name: '복약', exact: true })).toBeVisible();
    await expect(add).toHaveCount(0);
    const cancel = page.getByRole('button', { name: '취소', exact: true });
    await expect(cancel).toHaveAttribute('data-variant', 'secondary');
    await movePointerAwayAndSettle(page, cancel);
    expect(await material(cancel)).toEqual(selectMaterial);
    await expect(page.getByRole('button', { name: /삭제 \d+개/ })).toHaveCount(0);
    await page.getByRole('checkbox', { name: /2026년 8월 24일 처방 선택/ }).check();
    const remove = page.getByRole('button', { name: '삭제 1개', exact: true });
    await expect(remove).toBeEnabled();
    await expect(remove).toHaveAttribute('data-variant', 'danger');
    await expectNoOverflow(page);
    if (width <= 390) await capture(page, `task-3-medications-selected-${width}.png`);

    await page.getByRole('button', { name: '취소', exact: true }).click();
    await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /처방 · 약/ })).toHaveCount(2);
  });
}

for (const width of [320, 390, 1280]) {
  test(`영양제 추가는 primary, 선택·취소는 secondary 52px 표면이고 선택 뒤 danger 삭제를 보인다 (${width}px)`, async ({ page }) => {
    test.skip(IS_REAL_API, MOCK_ONLY_REASON);
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/dev/supplements');
    await expect(page.getByRole('heading', { name: /영양제 \d+개/ })).toBeVisible();
    await settleRevealAnimations(page);

    const add = page.getByRole('button', { name: '영양제 추가', exact: true });
    const edit = page.getByRole('button', { name: '선택', exact: true });
    const selectionMaterial = await material(edit);
    await expectAddAndSelectionSurfaces(add, edit);
    await expectNoOverlap(add, edit);
    await expectNoOverflow(page);
    if (width <= 390) await capture(page, `task-3-supplements-normal-${width}.png`);

    await edit.click();
    await expect(add).toHaveCount(0);
    const cancel = page.getByRole('button', { name: '취소', exact: true });
    await expect(cancel).toHaveAttribute('data-variant', 'secondary');
    await movePointerAwayAndSettle(page, cancel);
    expect(await material(cancel)).toEqual(selectionMaterial);
    await expect(page.getByRole('button', { name: /삭제 \d+개/ })).toHaveCount(0);
    const firstSelection = page.getByRole('checkbox').first();
    await firstSelection.check();
    await expect(page.getByRole('button', { name: '삭제 1개', exact: true })).toBeEnabled();
    await expectNoOverflow(page);
    if (width <= 390) {
      await page.locator('main').evaluate(element => element.scrollTo(0, 0));
      await capture(page, `task-3-supplements-edit-${width}.png`);
    }

    await cancel.click();
    await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
    await expect(page.locator('section[aria-label="먹고 있는 영양제"] li')).not.toHaveCount(0);
  });
}

for (const width of [320, 390]) {
  test(`실제 복약 목록의 제목·primary 추가·secondary 선택 행은 겹치지 않는다 (${width}px)`, async ({ page }) => {
    test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', 'issue-447-list-token');
      sessionStorage.setItem('poke.account-principal', 'issue-447-list@example.com');
    });
    await page.route('**/api/v1/**', route =>
      fulfillJson(route, { code: 'FIXTURE_MISSING', message: '447 fixture missing' }, 503));
    await page.route('**/api/v1/medications', route =>
      fulfillJson(route, [productionMedicationOverview()]));
    await page.setViewportSize({ width, height: 844 });

    await page.goto('/medications');

    const heading = page.getByRole('heading', { name: '복용 중', exact: true });
    const episode = page.getByRole('button', { name: /2026년 8월 22일 처방/ });
    await expect(heading).toBeVisible();
    await expect(episode).toContainText('혈압 관리 처방');
    await settleRevealAnimations(page);
    const add = page.getByRole('button', { name: '처방 추가', exact: true });
    const select = page.getByRole('button', { name: '선택', exact: true });
    await expectAddAndSelectionSurfaces(add, select);
    await expectNoOverlap(add, select);
    await expectNoOverflow(page);
    await capture(page, `task-3-medications-production-normal-${width}.png`);

    await select.click();
    await expect(add).toHaveCount(0);
    await expect(page.getByRole('button', { name: /삭제 \d+개/ })).toHaveCount(0);
    await page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ }).check();
    const remove = page.getByRole('button', { name: '삭제 1개', exact: true });
    await expect(remove).toBeEnabled();
    await expectNoOverflow(page);
    await capture(page, `task-3-medications-production-selected-${width}.png`);
    await page.getByRole('button', { name: '취소', exact: true }).click();
    await expect(episode).toContainText('혈압 관리 처방');
  });
}

test('처방이 없으면 0개 헤더와 목록 작업 대신 등록 안내를 표시한다', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-520-empty-token');
    sessionStorage.setItem('poke.account-principal', 'issue-520-empty@example.com');
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/medications-empty-active');

  await expect(page.getByRole('heading', { name: '복용약을 등록하고 관리하기' })).toBeVisible();
  await expect(page.getByRole('region', { name: '복용 중' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '처방 추가', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '선택', exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('medications-first-registration.png') });
  await page.getByRole('button', { name: '복용약 등록하기', exact: true }).click();
  await expect(page).toHaveURL('/document-upload');
});

test('완료된 처방만 있어도 active 빈 상태는 완료 목록을 가리지 않는다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/medications-completed-only');

  await expect(page.getByRole('heading', { name: '현재 먹고 있는 약이 없어요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '복용약 등록하기', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '처방 추가', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '선택', exact: true })).toHaveCount(0);
  const completedSection = page.getByRole('region', { name: '완료된 처방' });
  await expect(completedSection).toBeVisible();
  await expect(completedSection.getByRole('button', { name: /복용 완료/ })).toBeVisible();
});
