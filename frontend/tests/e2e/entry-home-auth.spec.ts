import { expect, test, type Page } from 'playwright/test';

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('이메일').fill('patient@example.com');
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await expect(page).toHaveURL(/\/home$/);
}

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

test('신규 회원은 약을 등록하기 전에 빈 복약 상태로 시작한다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
  await page.getByLabel('이메일').fill('new-patient@example.com');
  await page.getByLabel('비밀번호', { exact: true }).fill('password1234');
  await page.getByLabel('비밀번호 확인').fill('password1234');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('status', { name: '복약 정보 불러오는 중' })).toBeVisible();
  await expect(page.getByText('약봉투를 등록해 주세요')).toBeVisible();
  await expect(page.getByText('오늘의 복약')).toHaveCount(0);
});

test('신규 회원이 약봉투와 복약 시간을 저장하면 홈이 복약 중 상태로 바뀐다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
  await page.getByLabel('이메일').fill('new-patient@example.com');
  await page.getByLabel('비밀번호', { exact: true }).fill('password1234');
  await page.getByLabel('비밀번호 확인').fill('password1234');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page.getByText('약봉투를 등록해 주세요')).toBeVisible();

  await page.getByRole('button', { name: '약봉투 등록', exact: true }).click();
  await page.locator('input[type="file"]').nth(1).setInputFiles({
    name: '조제약봉투_01.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake-png-for-medication-registration'),
  });
  await page.getByRole('button', { name: '등록하기' }).click();
  await page.getByRole('button', { name: '저장하고 복약 시간 설정' }).click();
  await page.getByRole('button', { name: '확인 후 저장' }).click();
  await page.getByRole('button', { name: '기본 시간으로 건너뛰기' }).focus();
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText('오늘의 복약')).toBeVisible();
  await expect(page.getByText('약봉투를 등록해 주세요')).toHaveCount(0);
});

test('로그인 홈은 약 없음·복약 중·복약 종료 상태를 모두 표현한다', async ({ page }) => {
  await page.goto('/dev/home-data-empty');
  await expect(page.getByText('약봉투를 등록해 주세요')).toBeVisible();

  await page.goto('/dev/home-active');
  await expect(page.getByText('오늘의 복약')).toBeVisible();

  await page.goto('/dev/home-data-ended');
  await expect(page.getByText('복용이 끝났어요')).toBeVisible();
  await expect(page.getByRole('button', { name: '새 약봉투 등록' })).toBeVisible();
});

test('로그인 홈은 조회 중 등록 카드를 띄우지 않고 실제 복약 데이터로 바뀐다', async ({ page }) => {
  await logIn(page);

  await expect(page.getByRole('status', { name: '복약 정보 불러오는 중' })).toBeVisible();
  await expect(page.getByText('약봉투를 등록해 주세요')).toHaveCount(0);
  await expect(page.getByText('오늘의 복약')).toBeVisible();
});

test('복약 조회 실패는 팝업 대신 홈 안의 카드로 보여준다', async ({ page }) => {
  await page.goto('/dev/home-load-error');

  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('시간 설정 저장 뒤 홈과 탭 재진입에서 복약 데이터를 다시 보여준다', async ({ page }) => {
  await logIn(page);
  await expect(page.getByText('오늘의 복약')).toBeVisible();

  await page.evaluate(() => {
    window.history.pushState({}, '', '/dev/medication-schedule');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/dev\/medication-schedule$/);
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText('오늘의 복약')).toBeVisible();

  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page).toHaveURL(/\/supplements$/);
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page.getByRole('status', { name: '복약 정보 불러오는 중' })).toBeVisible();
  await expect(page.getByText('오늘의 복약')).toBeVisible();
});

test('복약 중 홈은 지난·현재·다음 복약을 한 타임라인 카드로 보여준다', async ({ page }) => {
  await page.goto('/dev/home-active');

  const today = page.getByRole('region', { name: '오늘의 복약' });
  await expect(today.getByText('4일째 · 3일 남음')).toBeVisible();

  const timeline = today.getByRole('group', { name: '하루 복약 시간표' });
  const past = timeline.getByRole('group', { name: '지난 복약' });
  const current = timeline.getByRole('group', { name: '현재 복약' });
  const lunch = timeline.getByRole('group', { name: '다음 복약 점심' });
  const evening = timeline.getByRole('group', { name: '다음 복약 저녁' });

  await expect(past).toContainText('기상 후 07:00');
  await expect(past).toContainText('먹었어요');
  await expect(current.getByText('아침 08:00')).toBeVisible();
  await expect(current.getByText('지금', { exact: true })).toBeVisible();
  await expect(current.getByText('셀레콕시브 200mg')).toBeVisible();
  await expect(current.getByText('리바록사반 10mg')).toBeVisible();
  await expect(current.getByText('파모티딘 20mg')).toBeVisible();
  await expect(current.getByText('식사 후에 드세요')).toBeVisible();
  await expect(current.getByRole('button', { name: '3개 먹었어요' })).toBeVisible();
  await expect(lunch).toContainText('점심 13:00');
  await expect(lunch).toContainText('1개');
  await expect(evening).toContainText('저녁 19:00');
  await expect(evening).toContainText('3개');
  await expect(today.getByText('7일 중 4일째')).toHaveCount(0);
  await expect(today.getByText('8월 22일 시작')).toHaveCount(0);

  const medicineListBox = await current.getByRole('list', { name: '지금 먹을 약' }).boundingBox();
  const takenButtonBox = await current.getByRole('button', { name: '3개 먹었어요' }).boundingBox();
  expect(medicineListBox).not.toBeNull();
  expect(takenButtonBox).not.toBeNull();
  expect(Math.abs((medicineListBox?.x ?? 0) - (takenButtonBox?.x ?? 0))).toBeLessThanOrEqual(1);

  const timelineOverflow = await timeline.evaluate((element) => getComputedStyle(element).overflow);
  const pastBackground = await past.evaluate((element) => getComputedStyle(element).backgroundColor);
  const currentStyle = await current.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      background: style.backgroundColor,
      borderTop: style.borderTopWidth,
      borderBottom: style.borderBottomWidth,
    };
  });
  const lunchBackground = await lunch.evaluate(
    (element) => getComputedStyle(element).backgroundColor,
  );
  expect(timelineOverflow).toBe('hidden');
  expect(currentStyle.background).not.toBe(pastBackground);
  expect(currentStyle.background).not.toBe(lunchBackground);
  expect(currentStyle.borderTop).toBe('0px');
  expect(currentStyle.borderBottom).toBe('0px');

  await expect(page.getByRole('button', { name: /복용약 관리/ })).toContainText(
    '약 4개 · 8월 28일까지',
  );
  await expect(page.getByRole('button', { name: /영양제 관리/ })).toContainText(
    '비타민 A 상한 초과',
  );

  const featureIconBackgrounds = await Promise.all(
    ['복용약 관리', '영양제 관리', 'AI 상담'].map((name) =>
      page
        .getByRole('button', { name: new RegExp(name) })
        .locator(':scope > span')
        .first()
        .evaluate((element) => getComputedStyle(element).backgroundColor),
    ),
  );
  expect(new Set(featureIconBackgrounds).size).toBe(1);
  expect(featureIconBackgrounds[0]).not.toBe(currentStyle.background);
  await expect(page.getByRole('region', { name: '포케 기능 소개' })).toHaveCount(0);
});

test('빈 상태와 종료 상태에서는 주요 기능 행을 복약 중보다 위로 당긴다', async ({ page }) => {
  await page.goto('/dev/home-active');
  const activeBox = await page.getByRole('button', { name: /복용약 관리/ }).boundingBox();
  expect(activeBox).not.toBeNull();

  for (const route of ['/dev/home-data-empty', '/dev/home-data-ended']) {
    await page.goto(route);
    const compactBox = await page.getByRole('button', { name: /복용약 관리/ }).boundingBox();
    expect(compactBox).not.toBeNull();
    expect((compactBox?.y ?? 0) + 100).toBeLessThan(activeBox?.y ?? 0);
  }
});
