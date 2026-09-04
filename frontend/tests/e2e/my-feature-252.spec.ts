import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('마이페이지는 관리 항목과 세 알림 토글을 보여주고 로그아웃한다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('heading', { name: '마이페이지' })).toBeVisible();
  await expect(page.getByRole('button', { name: /복용약 4개/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /영양제 3개/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /진료일정 예정 3개/ })).toBeVisible();
  await expect(page.getByRole('status', { name: '내 관리 불러오는 중' })).toHaveCount(0);
  await expect(page.getByRole('alert', { name: '관리 정보 불러오기 실패' })).toHaveCount(0);
  await expect(page.getByRole('switch', { name: '복약 알림' })).toHaveCount(1);
  await expect(page.getByRole('switch', { name: '영양제 알림' })).toHaveCount(1);
  await expect(page.getByRole('switch', { name: '일정 알림' })).toHaveCount(1);

  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test('기본정보는 이메일 없이 비밀번호 변경과 가장 아래 회원 탈퇴를 제공한다', async ({
  page,
}) => {
  await page.goto('/dev/my-profile');

  await expect(page.getByLabel('이메일')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '비밀번호 변경' })).toBeVisible();
  await expect(page.getByText('변경사항 저장', { exact: true })).toBeVisible();

  const withdrawal = page.getByText('회원 탈퇴', { exact: true });
  await expect(withdrawal).toBeVisible();
  const saveButton = page.getByText('변경사항 저장', { exact: true });
  const saveBox = await saveButton.boundingBox();
  const withdrawalBox = await withdrawal.boundingBox();
  expect(saveBox).not.toBeNull();
  expect(withdrawalBox).not.toBeNull();
  expect(withdrawalBox!.y).toBeGreaterThan(saveBox!.y);

  await withdrawal.click();
  const dialog = page.getByRole('dialog', { name: '정말 탈퇴하시겠어요?' });
  await expect(dialog).toContainText('같은 이메일로 다시 가입할 수 없어요.');
  await expect(dialog.getByLabel('비밀번호')).toHaveAttribute(
    'autocomplete',
    'current-password',
  );
});

test('진료일정은 다가오는 일정과 이후 일정으로 나뉘고 추가 시트를 연다', async ({ page }) => {
  await page.goto('/dev/my-visits');

  await expect(page.getByRole('heading', { name: '진료일정' })).toBeVisible();
  await expect(page.getByText('다가오는 일정', { exact: true })).toBeVisible();
  await expect(page.getByText('이후 일정', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '진료일정 추가' }).click();
  const sheet = page.getByRole('dialog', { name: '진료일정 추가' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByLabel('진료일')).toBeVisible();
  await expect(sheet.getByLabel('진료 시간')).toBeVisible();
  await expect(sheet.getByLabel('병원')).toBeVisible();
});

test('알림 시간 설정은 네 식사 슬롯을 유지하고 설명을 보여준다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();

  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText('언제 알려드릴까요?');
  await expect(sheet.getByLabel('아침 시')).toBeVisible();
  await expect(sheet.getByLabel('점심 시')).toBeVisible();
  await expect(sheet.getByLabel('저녁 시')).toBeVisible();
  await expect(sheet.getByLabel('자기전 시')).toBeVisible();
});
