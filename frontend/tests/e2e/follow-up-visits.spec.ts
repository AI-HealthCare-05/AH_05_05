import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

// 브라우저 타임존과 무관하게 한국 달력일을 기준으로 계산해야 합니다.
test.use({ timezoneId: 'UTC' });

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-08T03:00:00Z'));
});

test('진료일정은 기존 미정 상태와 지난 일정 토글을 보여준다', async ({ page }) => {
  await page.goto('/dev/my-visits');

  await expect(page.getByRole('heading', { name: '진료일정' })).toBeVisible();
  await expect(page.getByText('시간 미정')).toBeVisible();
  await expect(page.getByText('병원 미정')).toBeVisible();
  await expect(page.getByText('병원과 시간을 정해보세요.')).toHaveCount(0);
  await expect(page.getByText('지난 진료')).toHaveCount(0);
  await page.getByRole('button', { name: '지난 일정 보기' }).click();
  await expect(page.getByText('지난 진료')).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test('한국 시간 기준 오늘은 진료일로 저장할 수 없고 내일부터 선택한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-08T15:30:00Z'));
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();

  const sheet = page.getByRole('dialog', { name: '진료일정 추가' });
  const date = sheet.getByLabel('진료일');
  const save = sheet.getByRole('button', { name: '저장' });
  await expect(date).toHaveAttribute('min', '2026-09-10');

  await date.fill('2026-09-09');
  await expect(sheet.getByText('진료일은 내일부터 선택해주세요.')).toBeVisible();
  await expect(save).toBeDisabled();

  await date.fill('2026-09-10');
  await sheet.getByLabel('병원').fill('내과');
  await expect(sheet.getByText('진료일은 내일부터 선택해주세요.')).toHaveCount(0);
  await expect(save).toBeEnabled();
});

test('시트를 열어둔 사이 한국 자정을 넘기면 저장 시점에 날짜를 다시 검증한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-08T14:59:00Z'));
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();

  const sheet = page.getByRole('dialog', { name: '진료일정 추가' });
  await sheet.getByLabel('진료일').fill('2026-09-09');
  await sheet.getByLabel('병원').fill('자정경계병원');
  await expect(sheet.getByRole('button', { name: '저장' })).toBeEnabled();

  await page.clock.setFixedTime(new Date('2026-09-08T15:01:00Z'));
  await sheet.getByRole('button', { name: '저장' }).click();

  await expect(sheet).toBeVisible();
  await expect(sheet.getByLabel('진료일')).toHaveAttribute('min', '2026-09-10');
  await expect(sheet.getByLabel('진료일')).toBeFocused();
  await expect(sheet.getByText('진료일은 내일부터 선택해주세요.')).toBeVisible();
  await expect(sheet.getByLabel('병원')).toHaveValue('자정경계병원');
});

test('진료 시간은 네이티브 입력 대신 10분 단위 옵션으로 선택한다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();

  const visitSheet = page.getByRole('dialog', { name: '진료일정 추가' });
  await visitSheet.getByRole('button', { name: '진료 시간 시간 미정' }).click();

  const timeSheet = page.getByRole('dialog', { name: '시간 선택' });
  await timeSheet.getByLabel('분').click();
  await expect(page.getByRole('option', { name: /^(00|10|20|30|40|50)분$/ })).toHaveCount(6);
  await expect(page.getByRole('option', { name: '05분', exact: true })).toHaveCount(0);
  await page.getByRole('option', { name: '40분', exact: true }).click();
  await timeSheet.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(
    visitSheet.getByRole('button', { name: '진료 시간 08:40' }),
  ).toBeVisible();
});

test('빈 병원명과 공백은 저장할 수 없고 진료과만 입력하면 시간 없이 등록한다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();

  const sheet = page.getByRole('dialog', { name: '진료일정 추가' });
  await sheet.getByLabel('진료일').fill('2026-09-20');
  const hospital = sheet.getByLabel('병원');
  await expect(hospital).toHaveAttribute('required', '');
  const save = sheet.getByRole('button', { name: '저장' });
  await expect(save).toBeDisabled();
  await hospital.fill(' \u3000 ');
  await expect(save).toBeDisabled();
  await hospital.fill('  내과  ');
  await expect(save).toBeEnabled();
  await sheet.getByRole('button', { name: '저장' }).click();

  const created = page.getByRole('button', { name: /9월 20일.*내과.*시간 미정/ });
  await expect(created).toBeVisible();
  await created.click();
  await expect(page.getByRole('dialog', { name: '진료일정 수정' }).getByLabel('병원')).toHaveValue('내과');
});

test('진료일정 수정에서 병원명은 지울 수 없고 시간만 지울 수 있다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: /9월 16일.*늘봄병원.*10:30/ }).click();

  const sheet = page.getByRole('dialog', { name: '진료일정 수정' });
  await sheet.getByLabel('병원').fill('');
  await sheet.getByRole('button', { name: '시간 지우기' }).click();
  await expect(sheet.getByRole('button', { name: '저장' })).toBeDisabled();
  await sheet.getByLabel('병원').fill('   ');
  await expect(sheet.getByRole('button', { name: '저장' })).toBeDisabled();
  await sheet.getByLabel('병원').fill('  ○○이비인후과  ');
  await sheet.getByRole('button', { name: '저장' }).click();

  await expect(
    page.getByRole('button', { name: /9월 16일.*○○이비인후과.*시간 미정/ }),
  ).toBeVisible();
});

test('병원이 없는 기존 일정은 병원명을 입력해야 수정할 수 있다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: /9월 18일.*병원 미정.*14:30/ }).click();
  const sheet = page.getByRole('dialog', { name: '진료일정 수정' });
  await expect(sheet.getByLabel('병원')).toHaveValue('');
  await expect(sheet.getByRole('button', { name: '저장' })).toBeDisabled();
  await sheet.getByLabel('병원').fill('내과');
  await sheet.getByRole('button', { name: '저장' }).click();
  await expect(page.getByRole('button', { name: /9월 18일.*내과.*14:30/ })).toBeVisible();
});

test('진료일정을 삭제하기 전에 연결된 알림 삭제를 안내한다', async ({ page }) => {
  await page.goto('/dev/my-visits');
  const target = page.getByRole('button', { name: /9월 18일.*병원 미정.*14:30/ });
  await target.click();
  await page.getByRole('dialog', { name: '진료일정 수정' }).getByRole('button', { name: '삭제' }).click();

  const dialog = page.getByRole('dialog', { name: '진료일정 삭제' });
  await expect(dialog).toContainText('연결된 알림도 함께 삭제돼요.');
  await dialog.getByRole('button', { name: '삭제하기' }).click();
  await expect(target).toHaveCount(0);
});

for (const width of [320, 375]) {
  test(`${width}px 진료일정 시트에서 병원 입력 안내와 예시가 잘리지 않는다`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/dev/my-visits');
    await page.getByRole('button', { name: '진료일정 추가' }).click();
    const sheet = page.getByRole('dialog', { name: '진료일정 추가' });
    const hospital = sheet.getByLabel('병원');
    const placeholderFits = await hospital.evaluate((input: HTMLInputElement) => {
      const style = getComputedStyle(input);
      const context = document.createElement('canvas').getContext('2d')!;
      context.font = style.font;
      const availableWidth = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      return context.measureText(input.placeholder).width <= availableWidth;
    });
    expect(placeholderFits).toBe(true);
    await expect(hospital).toHaveAccessibleDescription(/이비인후과.*내과/);
    expect(await sheet.evaluate((element) => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: testInfo.outputPath(`follow-up-visit-${width}.png`) });
  });
}
