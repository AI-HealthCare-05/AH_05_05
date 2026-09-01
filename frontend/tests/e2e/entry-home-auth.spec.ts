import { expect, test, type Page } from 'playwright/test';

test.setTimeout(20_000);

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

test('게스트 홈은 기능 중복 카드 없이 소개 배너와 탭바를 유지한다', async ({ page }) => {
  await page.goto('/home');

  await expect(page.getByRole('region', { name: '포케 기능 소개' })).toBeVisible();
  await expect(page.getByRole('button', { name: /복용약 관리/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /영양제 관리/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /AI 상담/ })).toHaveCount(0);
});

test('로그인 홈도 복약 상태 위에 소개 배너를 유지한다', async ({ page }) => {
  await page.goto('/dev/home-data-empty');

  await expect(page.getByRole('region', { name: '포케 기능 소개' })).toBeVisible();
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();
});

test('게스트 탭은 조회 화면으로 가지 않고 같은 로그인 시트를 연다', async ({ page }) => {
  await page.goto('/home');

  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page).toHaveURL(/\/home$/);
});

test('로그인하지 않고 챗봇 주소를 직접 열면 로그인 화면으로 보낸다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'principal-missing-token');
    sessionStorage.removeItem('poke.account-principal');
  });
  await page.goto('/chat');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: '로그인' })).toBeVisible();
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
  await page.getByLabel('이름').fill('신규 사용자');
  await page.getByLabel('전화번호').fill('01012345678');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();
});

test('신규 회원이 약봉투 OCR 결과를 확정하면 저장 완료 상태가 된다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
  await page.getByLabel('이메일').fill('new-patient@example.com');
  await page.getByLabel('비밀번호', { exact: true }).fill('password1234');
  await page.getByLabel('비밀번호 확인').fill('password1234');
  await page.getByLabel('이름').fill('신규 사용자');
  await page.getByLabel('전화번호').fill('01012345678');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '약봉투 등록하기', exact: true }).click();
  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
    name: '조제약봉투_01.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake-png-for-medication-registration'),
  });
  await page.getByRole('button', { name: '등록하기' }).click();
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible({ timeout: 7_000 });
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('button', { name: '확인 후 저장' }).click();
  await expect(page).toHaveURL(/\/medication-schedule\?recordId=12&ocrJobId=102$/);
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');
});

test('로그인 홈은 약 없음·복약 중·복약 종료 상태를 모두 표현한다', async ({ page }) => {
  await page.goto('/dev/home-data-empty');
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();

  await page.goto('/dev/home-active');
  await expect(page.getByText('오늘의 복약')).toBeVisible();

  await page.goto('/dev/home-data-ended');
  await expect(page.getByText('복용이 끝났어요')).toBeVisible();
  await expect(page.getByRole('button', { name: '새 약봉투 등록' })).toBeVisible();
});

test('로그인 홈 헤더는 탭바와 중복되는 마이 버튼을 두지 않는다', async ({ page }) => {
  await page.goto('/dev/home-active');

  await expect(page.getByRole('button', { name: '마이페이지' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '마이', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /복용약 관리/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /영양제 관리/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /AI 상담/ })).toHaveCount(0);
});

test('로그인 홈은 조회 중 등록 카드를 띄우지 않고 실제 복약 데이터로 바뀐다', async ({ page }) => {
  await logIn(page);

  await expect(page.getByText('복약정보를 등록하시면 시간에 맞춰 알림을 받으실 수 있어요.')).toHaveCount(0);
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
  await page
    .getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' })
    .getByRole('button', { name: '나중에' })
    .click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText('오늘의 복약')).toBeVisible();

  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page).toHaveURL(/\/supplements$/);
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page.getByText('오늘의 복약')).toBeVisible();
});

test('복약 중 홈은 overview의 시각과 슬롯별 약만 타임라인에 보여준다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');

  const today = page.getByRole('region', { name: '오늘의 복약' });
  await expect(today.getByText('4일째 · 3일 남음')).toBeVisible();

  const timeline = today.getByRole('group', { name: '하루 복약 시간표' });
  const morningDisclosure = timeline.getByRole('button', {
    name: /아침약 2개.*08:00.*자세히 보기/,
  });
  const eveningDisclosure = timeline.getByRole('button', {
    name: /저녁약 3개.*19:00.*자세히 보기/,
  });

  await expect(morningDisclosure).toContainText('지금');
  await expect(eveningDisclosure).toContainText('다음');
  await expect(timeline.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await morningDisclosure.click();
  const morning = timeline.getByRole('group', { name: '아침약 상세' });
  await expect(morning.getByText('셀레콕시브 200mg')).toBeVisible();
  await expect(morning.getByText('파모티딘 20mg')).toBeVisible();
  await expect(morning.getByText('리바록사반 10mg')).toHaveCount(0);
  await expect(morning.getByText('아세트아미노펜 650mg')).toHaveCount(0);
  await expect(morning.getByRole('button', { name: '2개 먹었어요' })).toBeVisible();
  await expect(timeline.getByText('기상 후 07:00')).toHaveCount(0);
  await expect(timeline.getByRole('button', { name: /점심약/ })).toHaveCount(0);
  await expect(timeline.getByRole('button', { name: /취침 전약/ })).toHaveCount(0);
  await expect(today.getByText('7일 중 4일째')).toHaveCount(0);
  await expect(today.getByText('8월 22일 시작')).toHaveCount(0);

  await expect(page.getByRole('region', { name: '포케 기능 소개' })).toBeVisible();
});

test('약 하나가 한 슬롯에만 있으면 타임라인도 한 칸과 실제 개수만 보여준다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-one-medication');

  const timeline = page.getByRole('group', { name: '하루 복약 시간표' });
  const disclosure = timeline.getByRole('button', { name: /아침약 1개.*08:00.*자세히 보기/ });
  await expect(disclosure).toBeVisible();
  await expect(timeline.getByRole('button', { name: /저녁약/ })).toHaveCount(0);
  await disclosure.click();
  await expect(timeline.getByRole('button', { name: '1개 먹었어요' })).toBeVisible();
});

test('약별 days가 지난 뒤에는 아직 복용 중인 약의 슬롯만 남는다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-29T12:00:00+09:00'));
  await page.goto('/dev/home-active');

  const timeline = page.getByRole('group', { name: '하루 복약 시간표' });
  const disclosure = timeline.getByRole('button', { name: /저녁약 1개.*19:00.*자세히 보기/ });
  await expect(disclosure).toBeVisible();
  await disclosure.click();
  await expect(timeline.getByText('리바록사반 10mg')).toBeVisible();
  await expect(timeline.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(timeline.getByText('파모티딘 20mg')).toHaveCount(0);
});

test('현재 시각이 바뀌면 접힌 복약 슬롯의 상태도 mealTimes를 따라 바뀐다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T07:30:00+09:00'));
  await page.goto('/dev/home-active');
  await expect(page.getByRole('button', { name: /아침약 2개.*자세히 보기/ })).toContainText('다음');

  await page.clock.setFixedTime(new Date('2026-08-25T20:00:00+09:00'));
  await page.reload();
  await expect(page.getByRole('button', { name: /저녁약 3개.*자세히 보기/ })).toContainText('지금');
});
test('먹었어요를 누르면 즉시 완료되고 다른 슬롯은 접힌 상태를 유지한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const timeline = page.getByRole('group', { name: '하루 복약 시간표' });

  await timeline.getByRole('button', { name: /아침약 2개.*자세히 보기/ }).click();
  await timeline.getByRole('button', { name: '2개 먹었어요' }).click();

  await expect(timeline.getByRole('button', { name: /아침약 2개.*간단히 보기/ })).toContainText('완료');
  await expect(timeline.getByRole('button', { name: /저녁약 3개.*자세히 보기/ })).toContainText('다음');
  await expect(timeline.getByRole('group', { name: '저녁약 상세' })).toHaveCount(0);
  await expect(page.getByText(/저장 중|기록 중/)).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('복약 기록 토스트의 되돌리기는 완료 칸을 다시 현재 칸으로 복구한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const timeline = page.getByRole('group', { name: '하루 복약 시간표' });

  await timeline.getByRole('button', { name: /아침약 2개.*자세히 보기/ }).click();
  await timeline.getByRole('button', { name: '2개 먹었어요' }).click();
  await page.getByRole('button', { name: '되돌리기' }).click();

  await expect(page.locator('[aria-controls="timeline-detail-morning"]')).toContainText('지금');
  await expect(timeline.getByRole('button', { name: '2개 먹었어요' })).toBeVisible();
});

test('다음 슬롯도 미리 기록할 수 있고 모두 기록하면 사실 문구만 보여준다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const timeline = page.getByRole('group', { name: '하루 복약 시간표' });

  await timeline.getByRole('button', { name: /아침약 2개.*자세히 보기/ }).click();
  await timeline.getByRole('button', { name: '2개 먹었어요' }).click();
  await timeline.getByRole('button', { name: /저녁약 3개.*자세히 보기/ }).click();
  await timeline.getByRole('button', { name: '3개 먹었어요' }).click();

  await expect(timeline.getByText('오늘 다 드셨어요')).toBeVisible();
  await expect(timeline.getByText(/잘하셨어요|훌륭/)).toHaveCount(0);
  await timeline.getByRole('group', { name: '아침약 상세' }).getByRole('button', {
    name: '복약 기록 되돌리기',
  }).click();
  await expect(timeline.getByRole('button', { name: /아침약 2개.*간단히 보기/ })).toContainText('지금');
  await expect(timeline.getByText('오늘 다 드셨어요')).toHaveCount(0);
});

test('복약 기록 저장 실패는 낙관적 표시를 원복하고 같은 화면에 오류 팝업을 띄운다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-dose-save-error');
  const timeline = page.getByRole('group', { name: '하루 복약 시간표' });

  await timeline.getByRole('button', { name: /아침약 2개.*자세히 보기/ }).click();
  await timeline.getByRole('button', { name: '2개 먹었어요' }).click();
  const dialog = page.getByRole('dialog', { name: '기록하지 못했어요' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('다시 시도해주세요.');
  await expect(page.locator('[aria-controls="timeline-detail-morning"]')).toContainText('지금');
  await expect(page).toHaveURL(/\/dev\/home-dose-save-error$/);
});

test('포커스 복귀 때 날짜가 바뀌었으면 오늘 기준 제목과 기록을 다시 조회한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  await expect(page.getByText('4일째 · 3일 남음')).toBeVisible();

  await page.clock.setFixedTime(new Date('2026-08-26T12:00:00+09:00'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));

  await expect(page.getByText('5일째 · 3일 남음')).toBeVisible();
});
