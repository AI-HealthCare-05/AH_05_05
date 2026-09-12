import { expect, test, type Page, type Route } from 'playwright/test';

const challenge = {
  id: 101,
  name: '매일 30분 걷기',
  phrase: '걷기로 채우는 나의 2주',
  description: '하루 한 번 걷고 직접 기록해요.',
  challenge_type_code: 'OFFICIAL',
  period_code: 'D14',
  duration_days: 14,
  check_type_code: 'SELF',
  frequency_code: 'DAILY',
  recruit_start_at: '2026-09-01T00:00:00+09:00',
  recruit_end_at: '2026-09-30T23:59:59+09:00',
  reward_badge: {
    id: 31,
    name: '튼튼 걷기 배지',
    description: '꾸준한 걷기를 기록했어요.',
    image_path: '/images/challenges/badge-walk.png',
  },
  can_join: true,
  participation_id: null,
};

const customChallenge = {
  templateId: 41,
  challengeType: 'SUPPLEMENT',
  challengeName: '영양제 루틴 이어가기',
  rewardBadge: null,
  action: 'NONE',
  targets: [{ id: 201, name: '오메가3', existingParticipationId: null }],
};

const noteEpisode = {
  careEpisodeId: 41,
  alias: '아침 처방',
  startDate: '2026-08-01',
  status: 'ACTIVE',
  noteCount: 1,
  medicationCount: 1,
  representativeMedicationName: '아침 처방 약',
  medications: [{ id: 410, name: '아침 처방 약', dose: '1정' }],
};

const note = {
  id: 901,
  careEpisodeId: 41,
  careEpisodeAlias: '아침 처방',
  careEpisodeStartDate: '2026-08-01',
  careEpisodeStatus: 'ACTIVE',
  availableMedications: [],
  medicationId: null,
  medication: null,
  dosedAt: '2026-08-02T08:00:00',
  body: '기존 메모',
  createdAt: '2026-08-02T08:10:00',
  updatedAt: null,
};

const medicationOverview = {
  recordId: 41,
  alias: '아침 처방',
  documentImageUrl: '',
  start: { date: '2026-08-01', slot: 'morning' },
  endDate: '2026-08-10',
  daysRemaining: 5,
  isFinished: false,
  mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
  medications: [{
    medicationId: 410,
    name: '아침 처방 약',
    dose: '1정',
    days: 10,
    daysRemaining: 5,
    slots: ['morning'],
    asNeeded: false,
  }],
};

const product = {
  id: 702,
  food_code: 'SUPPL-MULTI-702',
  name: '종합비타민',
  basis_qty: '1000mg',
  energy_kcal: 0,
  water_g: null,
  protein_g: null,
  fat_g: null,
  ash_g: null,
  carb_g: null,
  sugar_g: null,
  fiber_g: null,
  calcium_mg: null,
  iron_mg: null,
  phosphorus_mg: null,
  potassium_mg: null,
  sodium_mg: null,
  vitamin_a_ug_rae: null,
  retinol_ug: null,
  beta_carotene_ug: null,
  thiamine_mg: null,
  riboflavin_mg: null,
  niacin_mg: null,
  vitamin_c_mg: null,
  vitamin_d_ug: '10.00',
  cholesterol_mg: null,
  sat_fat_g: null,
  trans_fat_g: null,
  serving_desc: '2정',
  serving_size: '1000mg',
  daily_freq: '1회',
  target: '성인',
};

test.setTimeout(60_000);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'navigation-424-token');
    sessionStorage.setItem('poke.account-principal', 'navigation-424@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'NOT_FOUND', message: 'fixture에 없음' }, 404));
  await page.route('**/api/v1/user/challenge-catalog?*', route => fulfillJson(route, {
    items: [challenge], total_count: 1, offset: 0, limit: 100,
  }));
  await page.route('**/api/v1/user/challenge-catalog/101', route => fulfillJson(route, challenge));
  await page.route('**/api/v1/user/challenges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, {
    items: [{
      id: 901,
      user_id: 7,
      badge_id: 31,
      challenge_id: 101,
      user_challenge_id: 501,
      status: 'AWARDED',
      badge_name: '튼튼 걷기 배지',
      badge_image_path: '/images/challenges/badge-walk.png',
      awarded_at: '2026-09-10T10:00:00+09:00',
      revoked_at: null,
      revoke_reason: null,
    }],
    total_count: 1,
  }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => fulfillJson(route, {
    items: [customChallenge], totalCount: 1,
  }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
    items: [], totalCount: 0,
  }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => fulfillJson(route, {
    items: [], totalCount: 0,
  }));
  await page.route('**/api/v1/medications', route => fulfillJson(route, [medicationOverview]));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route => fulfillJson(route, [noteEpisode]));
  await page.route('**/api/v1/med/notes/901', route => fulfillJson(route, {
    ...note,
    ...(route.request().method() === 'PATCH' ? route.request().postDataJSON() : {}),
  }));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, route => {
    if (route.request().method() === 'POST') {
      return fulfillJson(route, { ...note, id: 902, ...route.request().postDataJSON() });
    }
    return fulfillJson(route, { items: [note], total: 1, nextCursor: null });
  });
  await page.route('**/api/v1/users/me', route => fulfillJson(route, {
    name: '테스트 사용자', phoneNumber: '01012345678', birthDate: '1990-01-01', gender: 'female',
  }));
  await page.route('**/api/v1/user/follow-up-visits?*', route => fulfillJson(route, {
    items: [], total: 0, offset: 0, limit: 100,
  }));
});

test('공식·맞춤 챌린지의 앱/브라우저 뒤로가기가 둘러보기와 순환하지 않는다', async ({ page }, testInfo) => {
  await page.goto('/challenges');
  await page.getByRole('link', { name: '둘러보기', exact: true }).click();
  await page.getByRole('button', { name: `${challenge.name} 자세히 보기`, exact: true }).click();
  await expect(page).toHaveURL('/challenges/official/101');

  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/browse');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges');

  await page.goForward();
  await expect(page).toHaveURL('/challenges/browse');
  await page.getByRole('button', { name: '영양제 루틴 이어가기 대상 선택', exact: true }).click();
  await expect(page).toHaveURL('/challenges/tailored/supplement?templateId=41');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/browse');
  await page.screenshot({ path: testInfo.outputPath('challenge-navigation-mobile.png'), fullPage: true });

  await page.getByRole('button', { name: '영양제 루틴 이어가기 대상 선택', exact: true }).click();
  await page.goBack();
  await expect(page).toHaveURL('/challenges/browse');
  await page.goBack();
  await expect(page).toHaveURL('/challenges');
});

test('배지 상세에서 목록으로 돌아간 뒤 목록 뒤로가기는 챌린지로 빠져나간다', async ({ page }) => {
  await page.goto('/challenges');
  await page.getByRole('region', { name: '작은 실천이 쌓이고 있어요' }).getByRole('link', { name: /전체 보기/ }).click();
  await page.getByRole('link', { name: '튼튼 걷기 배지, 1회 획득', exact: true }).click();
  await expect(page).toHaveURL('/challenges/badges/31');
  await expect(page.getByRole('banner').getByRole('heading', { name: '배지 상세', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '내 배지로 돌아가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/badges');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges');
});

test('배지 상세 공통 헤더는 로딩 실패와 미존재 상태에서도 뒤로가기를 제공한다', async ({ page }) => {
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, {
    code: 'TEMPORARY', message: '잠시 후 다시 시도해주세요.',
  }, 503));
  await page.goto('/challenges/badges/31');
  const header = page.getByRole('banner');
  await expect(header.getByRole('heading', { name: '배지 상세', exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(header.getByRole('button', { name: '뒤로 가기', exact: true })).toBeVisible();

  await page.goto('/challenges/badges/not-a-number');
  await expect(page.getByRole('banner').getByRole('heading', { name: '배지 상세', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '배지를 찾을 수 없어요', exact: true })).toBeVisible();
});

test('마이에서 연 복약 메모는 작성 취소와 수정 저장 뒤에도 마이 복귀 이력을 유지한다', async ({ page }) => {
  await page.goto('/my');
  await page.getByRole('button', { name: '복약 메모 모아보기', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes');
  await page.reload();

  await page.getByRole('button', { name: '새 메모 작성', exact: true }).click();
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes');

  await page.getByRole('tab', { name: '작성한 메모', exact: true }).click();
  await page.getByRole('button', { name: /아침 처방.*펼치기/ }).click();
  await page.getByRole('button', { name: '처방 전체 기존 메모', exact: true }).click();
  await page.getByLabel('건강상태 기록').fill('수정한 메모');
  await page.getByRole('button', { name: '수정 저장', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=41');

  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/my');
  await page.goForward();
  await expect(page).toHaveURL('/medications/notes?episodeId=41');
  await page.goBack();
  await expect(page).toHaveURL('/my');
});

test('홈 랭킹에서 추가했거나 이미 등록된 제품의 내 영양제 CTA는 뒤로가기 시 홈으로 복귀한다', async ({ page }, testInfo) => {
  let registered = false;
  await page.route('**/api/v1/display/med/nutr/rank', route => fulfillJson(route, {
    display_id: 3,
    title: '9월 면역력 관리',
    start_at: '2026-08-01T00:00:00+09:00',
    end_at: '2026-09-30T23:59:59+09:00',
    is_enabled: true,
    created_by_admin_id: 1,
    created_at: '2026-08-27T17:35:52+09:00',
    updated_at: null,
    items: [{ supplement_nutrient_id: 702, name: '종합비타민', rank_no: 1 }],
  }));
  await page.route('**/api/v1/med/nutr/702', route => fulfillJson(route, product));
  await page.route('**/api/v1/med/nutr/702/reviews?*', route => fulfillJson(route, {
    items: [], total: 0, offset: 0, limit: 10, rating_average: null, rating_count: 0, review_count: 0,
  }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', route => fulfillJson(route, {
    items: registered ? [{
      id: 9702,
      dose_amount: '1.000',
      dose_unit: '정',
      start_date: '2026-09-12',
      end_date: null,
      status: 'ACTIVE',
      note: null,
      created_at: '2026-09-12T09:00:00+09:00',
      updated_at: null,
      slots: [{ slot: 'MORNING', time: '08:00:00' }],
      supplement: product,
    }] : [],
    total: registered ? 1 : 0,
    offset: 0,
    limit: 100,
    nutrient_standard: null,
  }));
  await page.route('**/api/v1/med/user-suppl-nutr/702', route => {
    registered = true;
    return fulfillJson(route, {
      id: 9702,
      dose_amount: '1.000',
      dose_unit: '정',
      start_date: '2026-09-12',
      end_date: null,
      status: 'ACTIVE',
      score: null,
      review_body: null,
      note: null,
      created_at: '2026-09-12T09:00:00+09:00',
      updated_at: null,
      slots: [{ slot: 'MORNING', time: '08:00:00' }],
      supplement: product,
    });
  });

  await page.goto('/home');
  await page.getByRole('button', { name: '1위 종합비타민 제품 정보', exact: true }).click();
  await page.getByRole('button', { name: '내 영양제에 추가', exact: true }).click();
  await page.getByRole('dialog', { name: '영양제 추가' }).getByRole('button', { name: '추가하기' }).click();
  await expect(page).toHaveURL('/supplements');

  await page.goBack();
  await expect(page).toHaveURL('/home');
  await page.goForward();
  await expect(page).toHaveURL('/supplements');
  await page.reload();
  await expect(page).toHaveURL('/supplements');
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath('supplements-after-add-desktop.png'), fullPage: true });

  await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '홈', exact: true }).click();
  await expect(page).toHaveURL('/home');
  await page.getByRole('button', { name: '1위 종합비타민 제품 정보', exact: true }).click();
  await expect(page.getByRole('button', { name: '내 영양제에서 보기', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '내 영양제에서 보기', exact: true }).click();
  await expect(page).toHaveURL('/supplements');
  await page.goBack();
  await expect(page).toHaveURL('/home');
});

test('직접 URL 진입은 각 기능의 안전한 상위 화면으로 replace 된다', async ({ page }) => {
  await page.goto('/challenges/official/101');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/browse');

  await page.goto('/challenges/tailored/supplement?templateId=41');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/browse');

  await page.goto('/challenges/badges/31');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/challenges/badges');

  await page.goto('/medications/notes');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/medications');

  await page.goto('/supplements/product/702');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/supplements');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/home');
});

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}
