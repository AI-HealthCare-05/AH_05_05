import { expect, test, type Page } from 'playwright/test';

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'withdrawal-e2e-token');
    window.sessionStorage.setItem('poke.account-principal', 'withdrawal@example.com');
    window.sessionStorage.removeItem('poke:splash-seen');
  });
  await page.goto('/home');
  await page.goto('/my');
}

async function openWithdrawalDialog(page: Page) {
  await page.getByRole('button', { name: '회원 탈퇴' }).click();
  return page.getByRole('dialog', { name: '정말 탈퇴하시겠어요?' });
}

test('회원 탈퇴는 로그아웃과 같은 외곽선 버튼에서 빨간 글씨로 경고 팝업에 들어간다', async ({
  page,
}) => {
  await authenticate(page);

  const entry = page.getByRole('button', { name: '회원 탈퇴' });
  await expect(entry).toHaveClass(/w-full/);
  await expect(entry).toHaveClass(/border-border/);
  await expect(entry).toHaveClass(/text-danger-strong/);
  await expect(entry).not.toHaveClass(/bg-danger/);

  const dialog = await openWithdrawalDialog(page);
  await expect(dialog).toContainText('복약 기록과 등록한 영양제를 다시 볼 수 없어요.');
  await expect(dialog).toContainText('같은 이메일로 다시 가입할 수 있지만, 이전 기록은 복구되지 않아요.');
  await expect(dialog).not.toContainText('삭제');

  const password = dialog.getByLabel('비밀번호');
  const cancel = dialog.getByRole('button', { name: '취소' });
  const withdraw = dialog.getByRole('button', { name: '탈퇴하기' });
  await expect(password).toHaveAttribute('type', 'password');
  await expect(password).toHaveAttribute('autocomplete', 'current-password');
  await expect(withdraw).toBeDisabled();
  await expect(cancel).toHaveClass(/bg-primary/);

  await password.fill('password1234');
  await expect(withdraw).toBeEnabled();
  await expect(withdraw).toHaveClass(/bg-danger/);
  await cancel.click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/\/my$/);
});

test('틀린 비밀번호는 팝업 안에서 알리고 로그인 상태를 유지한다', async ({ page }) => {
  await authenticate(page);
  const dialog = await openWithdrawalDialog(page);

  await dialog.getByLabel('비밀번호').fill('wrong');
  await dialog.getByRole('button', { name: '탈퇴하기' }).click();

  await expect(dialog.getByText('비밀번호가 일치하지 않아요')).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(page).toHaveURL(/\/my$/);
  await expect
    .poll(() => page.evaluate(() => sessionStorage.getItem('poke.access-token')))
    .toBe('withdrawal-e2e-token');
});

test('탈퇴 성공은 세션을 비우고 스플래시로 replace 이동한다', async ({ page }) => {
  await authenticate(page);
  const dialog = await openWithdrawalDialog(page);

  await dialog.getByLabel('비밀번호').fill('password1234');
  await dialog.getByRole('button', { name: '탈퇴하기' }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect
    .poll(() =>
      page.evaluate(() => ({
        token: sessionStorage.getItem('poke.access-token'),
        principal: sessionStorage.getItem('poke.account-principal'),
      })),
    )
    .toEqual({ token: null, principal: null });
  await expect(page.getByText('탈퇴되었습니다')).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveURL(/\/home$/);
});
