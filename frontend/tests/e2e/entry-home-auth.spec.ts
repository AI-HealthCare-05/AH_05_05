import { expect, test } from 'playwright/test';

test('첫 진입은 버튼 없는 스플래시를 거쳐 게스트 홈으로 자동 이동한다', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('약봉투 한 장이면 충분해요')).toBeVisible();
  await expect(page.getByRole('button')).toHaveCount(0);
  await expect(page).toHaveURL(/\/home$/, { timeout: 3_000 });
  await expect(page.getByRole('heading', { name: '포케' })).toBeVisible();
});

test('같은 브라우저 세션의 두 번째 진입은 스플래시를 다시 기다리지 않는다', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/home$/, { timeout: 3_000 });

  await page.goto('/');
  await expect(page).toHaveURL(/\/home$/, { timeout: 500 });
});

test('게스트가 기능을 누르면 로그인 이유를 설명하는 시트가 열리고 닫힌다', async ({ page }) => {
  await page.goto('/home');

  await page.getByRole('button', { name: /복용약 관리/ }).click();
  const sheet = page.getByRole('dialog');
  await expect(sheet).toContainText('복용약과 영양제는 사람마다 달라 저장할 곳이 필요해요');
  await sheet.getByRole('button', { name: '다음에 할게요' }).click();
  await expect(sheet).toBeHidden();
  await expect(page).toHaveURL(/\/home$/);
});

test('게스트 탭은 조회 화면으로 가지 않고 같은 로그인 시트를 연다', async ({ page }) => {
  await page.goto('/home');

  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page).toHaveURL(/\/home$/);
});

test('회원가입은 두 필수 동의를 각각 선택해야 완료할 수 있다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();

  const submit = page.getByRole('button', { name: '회원가입 완료' });
  await expect(submit).toBeDisabled();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await expect(submit).toBeDisabled();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await expect(submit).toBeEnabled();
});

test('로그인 홈은 약 없음·복약 중·복약 종료 상태를 모두 표현한다', async ({ page }) => {
  await page.goto('/dev/home-empty');
  await expect(page.getByText('약봉투를 등록해 주세요')).toBeVisible();

  await page.goto('/dev/home-active');
  await expect(page.getByText('오늘의 복약')).toBeVisible();

  await page.goto('/dev/home-ended');
  await expect(page.getByText('복용이 끝났어요')).toBeVisible();
  await expect(page.getByRole('button', { name: '새 약봉투 등록' })).toBeVisible();
});

test('복약 중 홈은 오늘 약의 숫자 위계와 다음 시간을 한 카드에서 보여준다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const today = page.getByRole('region', { name: '오늘의 복약' });
  await expect(today.getByText('아침 08:00')).toBeVisible();
  await expect(today.getByText('3개 · 식후에 드세요')).toBeVisible();
  await expect(today.getByText('셀레콕시브 200mg')).toBeVisible();
  await expect(today.getByText('리바록사반 10mg')).toBeVisible();
  await expect(today.getByText('파모티딘 20mg')).toBeVisible();
  await expect(today.getByRole('button', { name: '먹었어요' })).toBeVisible();
  await expect(today.getByText('점심 13:00')).toBeVisible();
  await expect(today.getByText('1개', { exact: true })).toBeVisible();
  await expect(today.getByText('저녁 19:00')).toBeVisible();
  await expect(today.getByText('3개', { exact: true })).toBeVisible();
  await expect(today.getByText('7일 중 4일째')).toBeVisible();
  await expect(today.getByText('8월 22일 시작')).toBeVisible();
  await expect(page.getByRole('region', { name: '포케 기능 소개' })).toHaveCount(0);
});

test('홈 네 상태는 주요 기능 행이 같은 높이에서 시작한다', async ({ page }) => {
  await page.goto('/home');
  const guestBox = await page.getByRole('button', { name: /복용약 관리/ }).boundingBox();

  expect(guestBox).not.toBeNull();
  for (const route of ['/dev/home-empty', '/dev/home-active', '/dev/home-ended']) {
    await page.goto(route);
    const loggedInBox = await page.getByRole('button', { name: /복용약 관리/ }).boundingBox();
    expect(loggedInBox).not.toBeNull();
    expect(Math.abs((guestBox?.y ?? 0) - (loggedInBox?.y ?? 0))).toBeLessThanOrEqual(4);
  }
});
