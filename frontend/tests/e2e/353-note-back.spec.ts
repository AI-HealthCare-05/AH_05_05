import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-back-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-back@example.com');
  });
});

test('홈에서 연 새 복약 메모의 뒤로가기는 홈으로 돌아간다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const medicationActions = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  await medicationActions.getByRole('button', { name: '복약 메모' }).click();
  await expect(page).toHaveURL('/medications/notes/new');

  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page).toHaveURL('/home');
});

test('복약 메모 목록에서 연 새 메모의 뒤로가기는 목록으로 돌아간다', async ({ page }) => {
  await page.goto('/medications/notes');
  await page.getByRole('button', { name: '새 메모 작성' }).click();
  await expect(page).toHaveURL('/medications/notes/new');

  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page).toHaveURL('/medications/notes');
});

test('직접 연 새 메모는 임의 리턴 경로 없이 목록으로 돌아간다', async ({ page }) => {
  await page.goto('/medications/notes/new');
  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page).toHaveURL('/medications/notes');
});
