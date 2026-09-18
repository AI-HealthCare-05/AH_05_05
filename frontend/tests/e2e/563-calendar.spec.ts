import { expect, test } from 'playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { advanceSignupToProfile, fillSignupProfile } from './helpers/signup';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(45_000);
test.use({ viewport: { width: 393, height: 852 }, isMobile: true, hasTouch: true, timezoneId: 'Asia/Seoul' });
test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-18T05:00:00Z'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'calendar-test');
    sessionStorage.setItem('poke.account-principal', 'calendar@example.invalid');
  });
});

test('OCR 달력에서 오늘을 고르고 취소하면 원래 조제일을 유지하며 적용할 때만 바뀐다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  const field = page.getByLabel('조제일', { exact: true });
  await field.fill('2026-09-01');
  await field.click();
  const dialog = page.getByRole('dialog', { name: '조제일 선택', exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: '오늘', exact: true }).click();
  await dialog.getByRole('button', { name: '취소', exact: true }).click();
  await expect(field).toHaveValue('2026-09-01');
  await field.click();
  await dialog.getByRole('button', { name: '오늘', exact: true }).click();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(field).toHaveValue('2026-09-18');
  await expect(field).toBeFocused();
});

test('복약 메모 오늘 선택은 기존 시간을 보존하고 24시간 시분 선택을 적용한다', async ({ page }) => {
  await page.goto('/medications/notes/new');
  await page.getByLabel('처방', { exact: true }).selectOption({ index: 1 });
  const field = page.getByLabel('복용 일시', { exact: true });
  await field.fill('2026-09-17T18:37');
  await field.click();
  const dialog = page.getByRole('dialog', { name: '복용 일시 선택', exact: true });
  await dialog.getByRole('button', { name: '오늘', exact: true }).click();
  await expect(dialog.getByLabel('시 (24시간제)')).toHaveValue('18');
  await expect(dialog.getByLabel('분', { exact: true })).toHaveValue('37');
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(field).toHaveValue('2026-09-18T18:37');
  await field.click();
  await dialog.getByLabel('시 (24시간제)').selectOption('23');
  await dialog.getByLabel('분', { exact: true }).selectOption('59');
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(field).toHaveValue('2026-09-18T23:59');
  await field.click();
  await dialog.getByLabel('시 (24시간제)').selectOption('00');
  await dialog.getByLabel('분', { exact: true }).selectOption('00');
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(field).toHaveValue('2026-09-18T00:00');
});

test('진료일 달력은 내일부터 제한을 지켜 오늘을 비활성화하고 원래 시트로 복귀한다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가', exact: true }).click();
  const field = page.getByLabel('진료일', { exact: true });
  await field.click();
  const dialog = page.getByRole('dialog', { name: '진료일 선택', exact: true });
  await expect(dialog.getByRole('button', { name: '오늘', exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '2026년 9월 19일', exact: true }).click();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(field).toHaveValue('2026-09-19');
  await page.getByLabel('병원명 (필수)', { exact: true }).fill('테스트 병원');
  await expect(page.getByRole('dialog', { name: '진료일정 추가' }).getByRole('button', { name: '저장', exact: true })).toBeEnabled();
});

test('생년월일 달력은 연월을 이동하고 미래 날짜 및 범위 밖 직접 입력을 거부한다', async ({ page }) => {
  await page.goto('/dev/my-profile');
  const field = page.getByLabel('생년월일', { exact: true });
  await field.fill('1999-01-01');
  await field.click();
  const dialog = page.getByRole('dialog', { name: '생년월일 선택', exact: true });
  await dialog.getByLabel('연도', { exact: true }).fill('2000');
  await dialog.getByLabel('월', { exact: true }).selectOption('2');
  await dialog.getByRole('button', { name: '2000년 2월 29일', exact: true }).click();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(field).toHaveValue('2000-02-29');
  await field.click();
  await dialog.getByRole('button', { name: '오늘', exact: true }).click();
  await expect(dialog.getByRole('button', { name: '2026년 9월 19일', exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '취소', exact: true }).click();
  await field.fill('2000-02-30');
  expect(await field.evaluate((el: HTMLInputElement) => el.checkValidity())).toBe(false);
  await field.press('Tab');
  await expect(field).toHaveValue('');
  await field.focus();
  await field.pressSequentially('2000-02-29');
  await expect(field).toHaveValue('2000-02-29');
  await field.evaluate((input: HTMLInputElement) => input.setSelectionRange(0, 4));
  await field.pressSequentially('1996');
  await expect(field).toHaveValue('1996-02-29');
  await field.fill('1999-12-15');
  await field.click();
  await dialog.getByLabel('연도', { exact: true }).fill('2026');
  await dialog.getByLabel('연도', { exact: true }).press('Tab');
  await expect(dialog.getByLabel('월', { exact: true })).toHaveValue('9');
  await expect(dialog.getByRole('button', { name: '2026년 9월 18일', exact: true })).toBeEnabled();
  await expect(dialog.getByRole('button', { name: '이전 달', exact: true })).toBeEnabled();
});

for (const width of [320, 375, 430]) {
  test(`${width}px 날짜 달력은 화면 안에 들어오며 키보드 이동과 Escape 취소를 지원한다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/dev/ocr-review');
    const field = page.getByLabel('조제일', { exact: true });
    await field.fill('2026-09-18');
    await field.press('ArrowDown');
    const dialog = page.getByRole('dialog', { name: '조제일 선택', exact: true });
    await expect(dialog).toBeVisible();
    const rect = await dialog.boundingBox();
    expect(rect!.x).toBeGreaterThanOrEqual(0);
    expect(rect!.x + rect!.width).toBeLessThanOrEqual(width);
    const date = dialog.getByRole('button', { name: '2026년 9월 18일', exact: true });
    await date.focus();
    await date.press('ArrowRight');
    await expect(dialog.getByRole('button', { name: '2026년 9월 19일', exact: true })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(field).toHaveValue('2026-09-18');
  });
}

test('조회 기간의 오늘은 허용 범위에서만 선택되며 기존 적용 흐름을 유지한다', async ({ page }) => {
  await page.goto('/dev/medications?from=2026-09-01&to=2026-09-17');
  await page.getByRole('button', { name: '직접 지정', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: '조회 기간', exact: true });
  await sheet.getByRole('button', { name: '시작일 달력 열기' }).click();
  await expect(sheet.getByRole('button', { name: '오늘', exact: true })).toBeDisabled();
  await sheet.getByRole('button', { name: '종료일 달력 열기' }).click();
  await sheet.getByRole('button', { name: '오늘', exact: true }).click();
  await expect(sheet.getByLabel('종료일', { exact: true })).toHaveValue('2026-09-18');
  await sheet.getByRole('button', { name: '적용', exact: true }).click();
  await expect(page).toHaveURL(/from=2026-09-01&to=2026-09-18/);
});

test('회원가입 달력으로 생년월일을 적용한 뒤 필수 동의와 가입을 완료한다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  await advanceSignupToProfile(page);
  await page.getByLabel('생년월일', { exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '생년월일 선택', exact: true });
  await dialog.getByLabel('연도', { exact: true }).fill('1999');
  await dialog.getByLabel('연도', { exact: true }).press('Tab');
  await dialog.getByLabel('월', { exact: true }).selectOption('1');
  await dialog.getByRole('button', { name: '1999년 1월 1일', exact: true }).click();
  await dialog.getByRole('button', { name: '적용', exact: true }).click();
  await expect(page.getByLabel('생년월일', { exact: true })).toHaveValue('1999-01-01');
  await fillSignupProfile(page, { name: '테스트', phoneNumber: '01012345678', gender: '여성', serviceTerms: true, personalInformationTerms: true, ageTerms: true, recordTerms: true, aiTerms: true });
  await page.getByRole('button', { name: '회원가입 완료', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test('공통 달력 화면은 OCR·메모·진료일 각각의 날짜 제한과 24시간 입력을 표시한다', async ({ page }, testInfo) => {
  const directory = path.resolve('../artifacts/calendar-563/screenshots');
  mkdirSync(directory, { recursive: true });
  for (const entry of [
    { route: '/dev/ocr-review', label: '조제일', value: '2026-09-18', file: 'ocr' },
    { route: '/medications/notes/new', label: '복용 일시', value: '2026-09-18T18:37', file: 'memo-24h' },
    { route: '/dev/my-visits', label: '진료일', value: '2026-09-19', file: 'visit' },
  ]) {
    await page.goto(entry.route);
    if (entry.file === 'visit') await page.getByRole('button', { name: '진료일정 추가', exact: true }).click();
    const field = page.getByLabel(entry.label, { exact: true });
    await field.fill(entry.value);
    await field.click();
    const dialog = page.getByRole('dialog', { name: `${entry.label} 선택`, exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: '오늘', exact: true })).toBeVisible();
    await page.screenshot({ path: path.join(directory, `${entry.file}-${testInfo.project.name}-393.png`), animations: 'disabled' });
    await dialog.getByRole('button', { name: '취소', exact: true }).click();
    await expect(field).toHaveValue(entry.value);
  }
});
