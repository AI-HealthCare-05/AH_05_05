import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';
import {
  advanceSignupToPassword,
  advanceSignupToProfile,
  fillSignup,
  fillSignupProfile,
  openSignup,
} from './helpers/signup';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(20_000);

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('이메일').fill('patient@example.com');
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await expect(page).toHaveURL(/\/home$/);
}

async function seedSessionWithExpiry(page: Page, expiresAtSeconds: number) {
  await page.addInitScript((expiresAt) => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
    const token = `${encode({ alg: 'none', typ: 'JWT' })}.${encode({ exp: expiresAt })}.signature`;
    sessionStorage.setItem('poke.access-token', token);
    sessionStorage.setItem('poke.account-principal', 'expired-user@example.com');
  }, expiresAtSeconds);
}

test('첫 진입은 버튼 없는 스플래시를 거쳐 튜토리얼로 이동한다', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('약봉투 한 장이면 충분해요')).toBeVisible();
  await expect(page.getByRole('button')).toHaveCount(0);
  await expect(page).toHaveURL(/\/tutorial$/, { timeout: 3_000 });
  await expect(page.getByRole('heading', { name: /약봉투를 찍으면.*복약 일정이 만들어져요/ })).toBeVisible();
});

test('같은 브라우저 세션은 튜토리얼을 완료하기 전까지 다시 진입해도 튜토리얼을 유지한다', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/tutorial$/, { timeout: 3_000 });

  await page.goto('/');
  await expect(page).toHaveURL(/\/tutorial$/, { timeout: 500 });
});

test('게스트 홈은 기능 중복 카드 없이 소개 배너와 탭바를 유지한다', async ({ page }) => {
  await page.goto('/home');

  await expect(page.getByRole('region', { name: 'RxVita 기능 소개' })).toBeVisible();
  await expect(page.getByRole('button', { name: /복용약 관리/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /영양제 관리/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /AI 상담/ })).toHaveCount(0);
});

test('메인 하단에는 법적 안내 푸터를 표시하지 않는다', async ({ page }) => {
  await page.goto('/home');

  await expect(page.getByRole('contentinfo')).toHaveCount(0);
});

test('로그인 홈은 복약 상태를 탭 카드로 보여주고 소개 배너를 숨긴다', async ({ page }) => {
  await page.goto('/dev/home-data-empty');

  await expect(page.getByRole('region', { name: 'RxVita 기능 소개' })).toHaveCount(0);
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
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

test('로그인하지 않고 보호 화면을 직접 열면 로그인 화면으로 보낸다', async ({ page }) => {
  await page.goto('/supplements');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: '로그인' })).toBeVisible();
});

test('보호 화면에서 로그인하면 원래 요청한 화면으로 돌아간다', async ({ page }) => {
  await page.goto('/supplements');
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel('이메일').fill('patient@example.com');
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();

  await expect(page).toHaveURL(/\/supplements$/);
});

test('이미 만료된 토큰으로 보호 화면을 열면 세션을 지우고 로그인 화면으로 보낸다', async ({
  page,
}) => {
  await seedSessionWithExpiry(page, Math.floor(Date.now() / 1000) - 60);

  await page.goto('/my');

  await expect(page).toHaveURL(/\/login$/);
  await expect
    .poll(() =>
      page.evaluate(() => ({
        token: sessionStorage.getItem('poke.access-token'),
        principal: sessionStorage.getItem('poke.account-principal'),
      })),
    )
    .toEqual({ token: null, principal: null });
});

test('홈에서는 토큰이 만료되어도 로그인 화면으로 이동하지 않고 게스트 상태로 전환한다', async ({
  page,
}) => {
  await seedSessionWithExpiry(page, Math.floor(Date.now() / 1000) + 3);

  await page.goto('/home');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('heading', { name: '오늘의 복약' })).toBeVisible();

  await expect
    .poll(() => page.evaluate(() => sessionStorage.getItem('poke.access-token')), {
      timeout: 5_000,
    })
    .toBeNull();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('heading', { name: '오늘의 복약' })).toBeVisible();
  await expect(page.getByRole('button', { name: '로그인하고 시작하기' })).toBeVisible();
});

test('회원가입은 두 필수 동의를 각각 선택해야 완료할 수 있다', async ({ page }) => {
  await openSignup(page);
  await advanceSignupToProfile(page);
  await fillSignupProfile(page, {
    name: '동의회원',
    phoneNumber: '01012345678',
    birthDate: '1990-01-01',
    gender: '여성',
  });

  const submit = page.getByRole('button', { name: '회원가입 완료' });
  await expect(submit).toBeDisabled();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await expect(submit).toBeDisabled();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await expect(submit).toBeEnabled();
});

test('회원가입 비밀번호와 비밀번호 확인은 각각 독립적으로 표시하고 다시 숨긴다', async ({
  page,
}) => {
  await openSignup(page);
  await expect(page.getByRole('button', { name: '비밀번호 보기' })).toHaveCount(0);
  await advanceSignupToPassword(page);

  const password = page.getByLabel('비밀번호', { exact: true });
  const passwordConfirm = page.getByLabel('비밀번호 확인', { exact: true });
  await password.fill('Password123!');
  await passwordConfirm.fill('Password123!');

  await page.getByRole('button', { name: '비밀번호 보기', exact: true }).click();
  await expect(password).toHaveAttribute('type', 'text');
  await expect(passwordConfirm).toHaveAttribute('type', 'password');
  await expect(password).toHaveValue('Password123!');

  await page.getByRole('button', { name: '비밀번호 확인 보기' }).click();
  await expect(passwordConfirm).toHaveAttribute('type', 'text');
  await expect(passwordConfirm).toHaveValue('Password123!');

  await page.getByRole('button', { name: '비밀번호 숨기기', exact: true }).click();
  await page.getByRole('button', { name: '비밀번호 확인 숨기기' }).click();
  await expect(password).toHaveAttribute('type', 'password');
  await expect(passwordConfirm).toHaveAttribute('type', 'password');
});

test('회원가입 이름 입력은 숫자·공백·특수문자를 제거하고 여러 언어의 문자를 남긴다', async ({
  page,
}) => {
  await openSignup(page);
  await advanceSignupToProfile(page);

  const nameInput = page.getByLabel('이름');
  await nameInput.fill('홍길동 Élodie山田Мария 123!😀');

  await expect(nameInput).toHaveValue('홍길동Élodie山田Мария');

  await nameInput.fill('E\u0301lodie');
  await expect(nameInput).toHaveValue('Élodie');
  await expect(
    page.getByText('이름에는 숫자, 공백, 특수문자를 사용할 수 없습니다.'),
  ).toHaveCount(0);
});

test('신규 회원은 약을 등록하기 전에 빈 복약 상태로 시작한다', async ({ page }) => {
  await openSignup(page);
  await fillSignup(page, {
    name: '신규사용자',
    birthDate: '1990-01-01',
    gender: '여성',
  });
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
});

test('신규 회원이 약봉투 OCR 결과를 확정하면 저장 완료 상태가 된다', async ({ page }) => {
  await openSignup(page);
  await fillSignup(page, {
    name: '신규사용자',
    birthDate: '1990-01-01',
    gender: '여성',
  });
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();

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
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();

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

  await expect(today.getByText('아침 08:00', { exact: true })).toBeVisible();
  const morning = today.getByRole('group', { name: '아침약 상세' });
  await expect(morning.getByText('셀레콕시브 외 1개')).toBeVisible();
  await expect(morning.getByText('셀레콕시브 200mg')).toHaveCount(0);
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*펼치기/ }).click();
  await expect(
    morning.getByRole('group', { name: /8월 22일 처방 약 상세/ }).getByText('셀레콕시브 200mg', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    morning.getByRole('group', { name: /8월 22일 처방 약 상세/ }).getByText('파모티딘 20mg', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(morning.getByRole('button', { name: '2개 먹었어요' })).toBeVisible();
  await expect(today.getByRole('group', { name: '저녁약 상세' })).toHaveCount(0);
  await expect(today.getByText('7일 중 4일째')).toHaveCount(0);
  await expect(today.getByText('8월 22일 시작')).toHaveCount(0);

  await expect(page.getByRole('region', { name: 'RxVita 기능 소개' })).toHaveCount(0);
});

test('약 하나가 한 슬롯에만 있으면 타임라인도 한 칸과 실제 개수만 보여준다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-one-medication');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(detail.getByRole('article', { name: /약 1개/ })).toBeVisible();
  await expect(detail.getByRole('button', { name: '1개 먹었어요' })).toBeVisible();
});

test('약별 days가 지난 뒤에는 아직 복용 중인 약의 슬롯만 남는다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-29T12:00:00+09:00'));
  await page.goto('/dev/home-active');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '저녁약 상세',
  });
  const episode = detail.getByRole('article', { name: /약 1개/ });
  await episode.getByRole('button', { name: /펼치기/ }).click();
  await expect(
    episode.getByRole('list', { name: /처방 약 목록/ }).getByText('리바록사반 10mg', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(detail.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(detail.getByText('파모티딘 20mg')).toHaveCount(0);
});

test('현재 시각이 바뀌면 접힌 복약 슬롯의 상태도 mealTimes를 따라 바뀐다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T07:30:00+09:00'));
  await page.goto('/dev/home-active');
  await expect(page.getByRole('region', { name: '오늘의 복약' }).getByText('아침 08:00')).toBeVisible();

  await page.clock.setFixedTime(new Date('2026-08-25T20:00:00+09:00'));
  await page.reload();
  await expect(page.getByRole('region', { name: '오늘의 복약' }).getByText('저녁 19:00')).toBeVisible();
});
test('먹었어요를 누르면 즉시 완료되고 다른 슬롯은 접힌 상태를 유지한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();

  await expect(detail.getByRole('button', { name: '복약 기록 되돌리기' })).toBeVisible();
  await expect(page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', { name: '저녁약 상세' })).toHaveCount(0);
  await expect(page.getByText(/저장 중|기록 중/)).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('복약 기록 토스트의 되돌리기는 완료 칸을 다시 현재 칸으로 복구한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  await page.getByRole('button', { name: '되돌리기' }).click();

  await expect(detail.getByRole('button', { name: '2개 먹었어요' })).toBeVisible();
});

test('복약 카드의 전체 회차 기록은 되돌릴 수 있다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });

  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(detail.getByRole('button', { name: '복약 기록 되돌리기' })).toBeVisible();
  await detail.getByRole('button', { name: '복약 기록 되돌리기' }).click();
  await expect(detail.getByRole('button', { name: '2개 먹었어요' })).toBeVisible();
});

test('복약 기록 저장 실패는 낙관적 표시를 원복하고 같은 화면에 오류 팝업을 띄운다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-dose-save-error');
  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await detail.getByRole('button', { name: '2개 먹었어요' }).click();
  const dialog = page.getByRole('dialog', { name: '기록하지 못했어요' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('다시 시도해주세요.');
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
