import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-252-medication-token');
    sessionStorage.setItem('poke.account-principal', 'feature-252-medication@example.com');
  });
});

test('약봉투 등록은 OCR·별칭·복용 시간·첫 복용·알람의 5단계로 이어진다', async ({ page }) => {
  await page.goto('/dev/ocr-review');

  await expect(page.getByText('2 / 5', { exact: true })).toBeVisible();
  await expect(page.getByLabel('복약 별칭')).toBeVisible();
  await page.getByLabel('복약 별칭').fill('감기약');

  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '확인 후 저장' }).click();

  await expect(page).toHaveURL(/\/medication-schedule\?recordId=12&ocrJobId=b_mock_9f21/);
  await expect(page.getByText('3 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '약마다 먹는 시간을 확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '확인', exact: true }).click();

  await expect(page.getByText('4 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '처음 약을 언제 드셨나요?' })).toBeVisible();
  await page.getByRole('button', { name: '시작 점심약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();

  await expect(page.getByText('5 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '알람 시간을 확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
});

test('복약 목록은 활성 회차를 편집하고 완료 회차를 읽기 전용으로 연다', async ({ page }) => {
  await page.goto('/medications');

  await page.getByRole('button', { name: /2026년 8월 22일 처방/ }).click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: '처방 편집' })).toBeVisible();
  await expect(page.getByLabel('복약 별칭')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click();

  await page.getByRole('button', { name: /2026년 8월 24일 처방/ }).click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: '완료된 처방' })).toBeVisible();
  await expect(page.getByRole('dialog').getByText('완료된 처방은 내용만 확인할 수 있어요.')).toBeVisible();
});

test('복약 메모는 작성·수정·삭제할 수 있다', async ({ page }) => {
  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '새 메모 작성' }).click();
  await expect(page).toHaveURL('/medications/notes/new');
  await page.getByLabel('처방').selectOption('12');
  await page.getByLabel('약').selectOption('301');
  await page.getByLabel('복용 일시').fill('2026-09-03T15:20');
  await page.getByLabel('복용 후 느낀 점').fill('속이 편해졌어요.');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByText('속이 편해졌어요.')).toBeVisible();
  await page.getByRole('button', { name: /속이 편해졌어요/ }).click();
  await expect(page).toHaveURL(/\/medications\/notes\/[^/]+/);
  await page.getByLabel('복용 후 느낀 점').fill('수정한 메모예요.');
  await page.getByRole('button', { name: '수정 저장' }).click();
  await expect(page.getByText('수정한 메모예요.')).toBeVisible();

  await page.getByRole('button', { name: /수정한 메모예요/ }).click();
  await expect(page).toHaveURL(/\/medications\/notes\/[^/]+/);
  await page.getByRole('button', { name: '삭제' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByText('수정한 메모예요.')).toHaveCount(0);
});
