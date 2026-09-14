import { expect, test, type Locator, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON, REAL_API_ONLY_REASON } from './helpers/mode';

interface Surface {
  backgroundImage: string;
  borderColor: string;
  borderRadius: string;
  borderWidth: string;
  boxShadow: string;
  fontSize: string;
  fontWeight: string;
  height: number;
  paddingLeft: string;
}

async function surface(locator: Locator): Promise<Surface> {
  return locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundImage: style.backgroundImage,
      borderColor: style.borderTopColor,
      borderRadius: style.borderTopLeftRadius,
      borderWidth: style.borderTopWidth,
      boxShadow: style.boxShadow,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      height: element.getBoundingClientRect().height,
      paddingLeft: style.paddingLeft,
    };
  });
}

function expectRaisedMaterial(actual: Surface, owner: Surface) {
  expect(actual.backgroundImage).toBe(owner.backgroundImage);
  expect(actual.backgroundImage).not.toBe('none');
  expect(actual.boxShadow).toBe(owner.boxShadow);
  expect(actual.boxShadow).not.toBe('none');
  expect(actual.borderRadius).toBe(owner.borderRadius);
  expect(actual.borderWidth).toBe(owner.borderWidth);
}

async function expectNoDocumentOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
}

async function expectDateEntryContentFits(input: Locator) {
  const fit = await input.evaluate((element: HTMLInputElement) => {
    const style = getComputedStyle(element);
    const context = document.createElement('canvas').getContext('2d')!;
    context.font = style.font;
    const displayedDate = element.value || element.placeholder;
    const requiredWidth =
      parseFloat(style.paddingLeft) +
      context.measureText(displayedDate).width +
      parseFloat(style.paddingRight);
    return { clientWidth: element.clientWidth, requiredWidth };
  });
  expect(fit.clientWidth).toBeGreaterThanOrEqual(fit.requiredWidth);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '447-remaining-controls');
    sessionStorage.setItem('poke.account-principal', '447-remaining-controls@example.com');
  });
});

test('검색·날짜·메모·후기·진료 시간은 기존 Input과 같은 실제 표면을 쓴다', async ({ page }, testInfo) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  test.setTimeout(120_000);
  await page.clock.setFixedTime(new Date('2026-09-13T03:00:00Z'));
  await page.setViewportSize({ width: 320, height: 812 });

  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).click();
  const addSheet = page.getByRole('dialog', { name: '영양제 추가' });
  const inputOwner = addSheet.getByRole('searchbox', { name: '영양제 제품 검색' });
  await expect(inputOwner).toBeVisible();
  await inputOwner.blur();
  const inputOwnerSurface = await surface(inputOwner);
  await addSheet.getByRole('button', { name: '닫기', exact: true }).click();

  await page.goto('/dev/supplements?tab=browse');
  const browseSearch = page.getByRole('searchbox', { name: '영양제 제품 검색' });
  await expect(browseSearch).toHaveAttribute('type', 'search');
  await expect(browseSearch).toHaveAttribute('placeholder', '제품명 또는 성분 검색');
  const browseSurface = await surface(browseSearch);
  expectRaisedMaterial(browseSurface, inputOwnerSurface);
  expect(browseSurface.height).toBe(inputOwnerSurface.height);
  expect(browseSurface.paddingLeft).toBe('44px');
  const browseIcon = browseSearch.locator('xpath=../../preceding-sibling::*[name()="svg"]');
  await expect(browseIcon).toHaveCount(1);
  expect(await browseIcon.evaluate((icon) => getComputedStyle(icon).pointerEvents)).toBe('none');
  await expectNoDocumentOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('task-6-supplement-search-320.png'), fullPage: true });

  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();
  const visitSheet = page.getByRole('dialog', { name: '진료일정 추가' });
  const nativeDateOwner = visitSheet.getByLabel('진료일');
  await nativeDateOwner.blur();
  const nativeDateSurface = await surface(nativeDateOwner);
  const timeButton = visitSheet.getByRole('button', { name: '진료 시간 시간 미정' });
  const timeSurface = await surface(timeButton);
  expectRaisedMaterial(timeSurface, nativeDateSurface);
  expect(timeSurface.height).toBe(52);
  await expect(timeButton).toHaveAttribute('aria-label', '진료 시간 시간 미정');
  await visitSheet.getByRole('button', { name: '닫기', exact: true }).click();

  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '최근 6개월' }).click();
  const periodSheet = page.getByRole('dialog', { name: '조회 기간' });
  await periodSheet.getByText('직접 지정', { exact: true }).click();
  const from = periodSheet.getByLabel('시작일', { exact: true });
  const to = periodSheet.getByLabel('종료일', { exact: true });
  for (const date of [from, to]) {
    await expect(date).toHaveAttribute('type', 'text');
    await expect(date).toHaveAttribute('inputmode', 'numeric');
    const dateSurface = await surface(date);
    expectRaisedMaterial(dateSurface, nativeDateSurface);
    expect(Math.abs(dateSurface.height - nativeDateSurface.height)).toBeLessThan(0.1);
  }
  await expect(from).toHaveAttribute('min', '2024-09-13');
  await expect(from).toHaveAttribute('max', '2026-09-13');
  await from.fill('2026-09-01');
  await expect(to).toHaveAttribute('min', '2026-09-01');
  await expect(to).toHaveAttribute('max', '2026-09-13');
  await expectNoDocumentOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('task-6-medication-period-320.png'), fullPage: true });

  await page.goto('/medications/notes/new');
  const prescription = page.getByLabel('처방', { exact: true });
  const experience = page.getByLabel('건강상태 기록');
  const dateTime = page.getByLabel('복용 일시');
  await expect(prescription).toBeVisible();
  const noteOwnerSurface = await surface(dateTime);
  for (const field of [prescription, experience]) {
    expectRaisedMaterial(await surface(field), noteOwnerSurface);
  }
  await expect(experience).toHaveAttribute('rows', '5');
  await expect(experience).toHaveAttribute('maxlength', '500');
  expect(await experience.evaluate((element) => getComputedStyle(element).resize)).toBe('vertical');

  await page.goto('/supplements');
  const supplementRow = page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /종합비타민/ }).first();
  await supplementRow.click();
  const detail = page.getByRole('dialog', { name: /종합비타민/ }).first();
  await detail.getByRole('group', { name: '내 메모' }).getByRole('button', { name: /등록하기|수정하기/ }).click();
  const memoEditor = page.getByRole('dialog', { name: '메모 편집', exact: true });
  const memo = memoEditor.getByRole('textbox', { name: /^메모/ });
  await memo.blur();
  expectRaisedMaterial(await surface(memo), inputOwnerSurface);
  await expect(memo).toHaveAttribute('rows', '3');
  await expect(memo).toHaveAttribute('maxlength', '100');
  expect(await memo.evaluate((element) => getComputedStyle(element).resize)).toBe('none');
  await memoEditor.getByRole('button', { name: '닫기', exact: true }).click();
  await detail.getByRole('group', { name: '내 후기' }).getByRole('button', { name: /등록하기|수정하기/ }).click();
  const reviewEditor = page.getByRole('dialog', { name: '후기 편집', exact: true });
  const review = reviewEditor.getByRole('textbox', { name: /^후기/ });
  await review.blur();
  expectRaisedMaterial(await surface(review), inputOwnerSurface);
  await expect(review).toHaveAttribute('rows', '3');
  await expect(review).toHaveAttribute('maxlength', '100');
  expect(await review.evaluate((element) => getComputedStyle(element).resize)).toBe('none');
});

for (const width of [320, 390]) {
  test(`${width}px 직접 지정 날짜는 직접 입력 가능한 반응형 열을 사용한다`, async ({ page }, testInfo) => {
    test.skip(IS_REAL_API, MOCK_ONLY_REASON);
    await page.clock.setFixedTime(new Date('2026-09-13T03:00:00Z'));
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/dev/medications');
    await page.getByRole('button', { name: '최근 6개월' }).click();
    const periodSheet = page.getByRole('dialog', { name: '조회 기간' });
    await periodSheet.getByText('직접 지정', { exact: true }).click();
    const from = periodSheet.getByLabel('시작일', { exact: true });
    const to = periodSheet.getByLabel('종료일', { exact: true });

    const [emptyFromBox, emptyToBox] = await Promise.all([from.boundingBox(), to.boundingBox()]);
    expect(emptyFromBox).not.toBeNull();
    expect(emptyToBox).not.toBeNull();
    if (width < 360) {
      expect(Math.abs(emptyFromBox!.x - emptyToBox!.x)).toBeLessThan(1);
      expect(emptyToBox!.y).toBeGreaterThanOrEqual(emptyFromBox!.y + emptyFromBox!.height);
    } else {
      expect(Math.abs(emptyFromBox!.y - emptyToBox!.y)).toBeLessThan(1);
      expect(emptyToBox!.x).toBeGreaterThanOrEqual(emptyFromBox!.x + emptyFromBox!.width);
    }
    await expectDateEntryContentFits(from);
    await expectDateEntryContentFits(to);
    await expectNoDocumentOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`task-6-period-empty-${width}.png`), fullPage: true });

    await from.fill('2026-09-01');
    await to.fill('2026-09-13');
    await expect(from).toHaveAttribute('min', '2024-09-13');
    await expect(from).toHaveAttribute('max', '2026-09-13');
    await expect(to).toHaveAttribute('min', '2026-09-01');
    await expect(to).toHaveAttribute('max', '2026-09-13');
    await expectDateEntryContentFits(from);
    await expectDateEntryContentFits(to);
    await expectNoDocumentOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`task-6-period-populated-${width}.png`), fullPage: true });
  });
}

test('MY 실행 버튼과 비밀번호 이동 행은 기존 Button과 ManagementRow 역할을 따른다', async ({ page }, testInfo) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto('/dev/supplements');
  const secondaryOwner = page.getByRole('button', { name: '영양제 추가', exact: true });
  await expect(secondaryOwner).toBeVisible();
  const secondarySurface = await surface(secondaryOwner);

  await page.goto('/dev/my-authenticated');
  const managementOwner = page.getByRole('button', { name: /영양제 \d+개/ });
  const managementSurface = await surface(managementOwner);
  const managementLabelSurface = await surface(managementOwner.getByText('영양제', { exact: true }));
  const logout = page.getByRole('button', { name: '로그아웃', exact: true });
  const logoutSurface = await surface(logout);
  expectRaisedMaterial(logoutSurface, secondarySurface);
  expect(logoutSurface.height).toBe(52);
  await page.screenshot({ path: testInfo.outputPath('task-6-my-actions-390.png'), fullPage: true });

  await page.goto('/dev/my-profile');
  const passwordRow = page.getByRole('button', { name: '비밀번호 변경', exact: true });
  const passwordSurface = await surface(passwordRow);
  expect(passwordSurface.height).toBe(managementSurface.height);
  expect(passwordSurface.height).toBeGreaterThanOrEqual(64);
  expect(passwordSurface.paddingLeft).toBe(managementSurface.paddingLeft);
  expect(passwordSurface.fontSize).toBe(managementLabelSurface.fontSize);
  expect(passwordSurface.fontWeight).toBe(managementLabelSurface.fontWeight);
  expect(passwordSurface.borderColor).toBe(managementSurface.borderColor);

  const withdrawal = page.getByRole('button', { name: '회원 탈퇴', exact: true });
  const withdrawalSurface = await surface(withdrawal);
  expectRaisedMaterial(withdrawalSurface, secondarySurface);
  expect(withdrawalSurface.height).toBe(52);
  await expect(withdrawal).toHaveCSS('color', 'rgb(176, 63, 60)');
  await page.screenshot({ path: testInfo.outputPath('task-6-profile-actions-390.png'), fullPage: true });
});

test('프로필 재시도는 compact secondary Button 표면과 기존 callback을 유지한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  let profileAttempts = 0;
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/v1/users/me') {
      profileAttempts += 1;
      if (profileAttempts <= 2) return route.fulfill({ status: 503, json: { message: '프로필 조회 실패' } });
      return route.fulfill({ json: { name: '재시도 성공', maskedName: '재**', phoneNumber: null, birthDate: null, gender: null } });
    }
    if (pathname === '/api/v1/medications') return route.fulfill({ json: [] });
    if (pathname === '/api/v1/med/user-suppl-nutr' || pathname === '/api/v1/user/follow-up-visits') {
      return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } });
    }
    if (pathname === '/api/v1/me/settings') {
      return route.fulfill({ json: { notifyMedication: false, notifySupplement: false, notifySchedule: false, notifyConsentedAt: null, morningMedicationTime: '08:00', lunchMedicationTime: '13:00', eveningMedicationTime: '19:00', bedtimeMedicationTime: '22:00' } });
    }
    return route.abort();
  });

  await page.goto('/reports/new?source=medications');
  const secondaryOwner = page.getByRole('button', { name: '복약으로 돌아가기' });
  const secondarySurface = await surface(secondaryOwner);
  await page.goto('/dev/my-authenticated');
  const retry = page.getByRole('button', { name: '프로필 다시 시도' });
  await expect(retry).toBeVisible();
  const retrySurface = await surface(retry);
  expectRaisedMaterial(retrySurface, secondarySurface);
  expect(retrySurface.height).toBe(44);
  expect(await retry.evaluate((element) => element.getBoundingClientRect().width < innerWidth / 2)).toBe(true);
  await retry.click();
  await expect(page.getByRole('button', { name: /재시도 성공.*기본정보/ })).toBeVisible();
});
