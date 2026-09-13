import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page, type Route } from 'playwright/test';
import { expectSelectedSlotDepth } from './helpers/doseSlotDepth';

const badge = {
  id: 31,
  name: '튼튼 걷기 배지',
  description: '꾸준한 걷기를 기록했어요.',
  image_path: '/images/challenges/badge-walk.png',
};

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
  reward_badge: badge,
  can_join: false,
  participation_id: 501,
};

function participation(checked: boolean) {
  return {
    id: 501,
    user_id: 7,
    challenge_id: 101,
    challenge_name: challenge.name,
    status: 'ACTIVE',
    joined_at: '2026-09-08T10:00:00+09:00',
    started_at: '2026-09-08T00:00:00+09:00',
    end_at: '2026-09-22T00:00:00+09:00',
    target_count: 14,
    completed_count: checked ? 4 : 3,
    progress_rate: checked ? '28.57' : '21.43',
    completed_at: null,
    cancelled_at: null,
    progress_periods: [],
    challenge,
    today: '2026-09-10',
    today_verification: checked
      ? {
          id: 990,
          verification_date: '2026-09-10',
          status: 'APPROVED',
          reviewed_at: '2026-09-10T12:00:00+09:00',
          submitted_at: '2026-09-10T12:00:00+09:00',
        }
      : null,
    can_verify: !checked,
    verified_dates: checked ? ['2026-09-08', '2026-09-09', '2026-09-10'] : ['2026-09-08', '2026-09-09'],
  };
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-447-token');
    sessionStorage.setItem('poke.account-principal', 'issue-447@example.com');
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function expectClay(control: Locator, height: number) {
  await expect(control).not.toHaveCSS('background-image', 'none');
  await expect(control).not.toHaveCSS('box-shadow', 'none');
  await expect(control).toHaveCSS('height', `${height}px`);
  expect((await control.boundingBox())!.height).toBeCloseTo(height, 1);
}

async function physical(control: Locator) {
  return control.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundColor: style.backgroundColor,
      backgroundImage: style.backgroundImage,
      borderColor: style.borderTopColor,
      borderWidth: style.borderTopWidth,
      boxShadow: style.boxShadow,
      transform: style.transform,
    };
  });
}

async function captureReviewScreenshot(page: Page, name: string) {
  const directory = process.env.UI447_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, name), fullPage: true });
}

test.beforeEach(async ({ page }) => {
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, (route) => route.abort());
});

test('홈 공식 인증은 compact 공통 표면과 pending 중복 방지를 함께 유지한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-09-10T12:00:00+09:00'));
  let checked = false;
  let verificationPosts = 0;
  let releaseVerification!: () => void;
  const verificationGate = new Promise<void>((resolve) => { releaseVerification = resolve; });
  const unhandled: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/user/challenges' && request.method() === 'GET') {
      return fulfillJson(route, { items: [participation(checked)], total_count: 1 });
    }
    if (path === '/api/v1/user/challenges/501/verifications' && request.method() === 'POST') {
      verificationPosts += 1;
      await verificationGate;
      checked = true;
      return fulfillJson(route, participation(true).today_verification, 201);
    }
    if (path === '/api/v1/user/custom-challenge-participations') {
      return fulfillJson(route, { items: [], totalCount: 0 });
    }
    if (path === '/api/v1/user/badges') return fulfillJson(route, { items: [], total_count: 0 });
    if (path === '/api/v1/medications') return fulfillJson(route, []);
    if (path === '/api/v1/medications/doses') return fulfillJson(route, []);
    if (path === '/api/v1/med/user-suppl-nutr') {
      return fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null });
    }
    if (path === '/api/v1/display/med/nutr/rank') return fulfillJson(route, { items: [] });
    unhandled.push(`${request.method()} ${path}`);
    return fulfillJson(route, { message: '447 fixture missing' }, 503);
  });

  await page.goto('/dev/medications');
  const canonical = page.getByRole('button', { name: 'AI 보고서 받기', exact: true });
  await expectClay(canonical, 44);
  const canonicalIdle = await physical(canonical);
  await canonical.hover();
  await page.waitForTimeout(160);
  const canonicalHover = await physical(canonical);
  await canonical.evaluate((element) => { element.style.transition = 'none'; });
  await page.mouse.down();
  await expect.poll(() => canonical.evaluate((element) => getComputedStyle(element).transform)).not.toBe('none');
  await page.waitForTimeout(160);
  const canonicalPressed = await physical(canonical);
  await page.mouse.move(0, 0);
  await page.mouse.up();

  await page.goto('/dev/medication-schedule');
  const canonicalDisabled = page.getByRole('button', { name: '저장하고 계속', exact: true });
  await expect(canonicalDisabled).toBeDisabled();
  const canonicalDisabledSurface = await physical(canonicalDisabled);

  await page.goto('/home');
  const checkIn = page.getByRole('button', { name: `${challenge.name} 했어요` });
  await expect(checkIn).toHaveAttribute('data-size', 'compact');
  await expectClay(checkIn, 44);
  expect(await physical(checkIn)).toEqual(canonicalIdle);
  await page.locator('.rx-today-challenge-item').evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
  await captureReviewScreenshot(page, 'task-1-home-controls-390.png');
  await checkIn.hover();
  await page.waitForTimeout(160);
  expect(await physical(checkIn)).toEqual(canonicalHover);
  await checkIn.evaluate((element) => { element.style.transition = 'none'; });
  await page.mouse.down();
  await expect.poll(() => checkIn.evaluate((element) => getComputedStyle(element).transform)).not.toBe('none');
  await page.waitForTimeout(160);
  expect(await physical(checkIn)).toEqual(canonicalPressed);
  await page.mouse.move(0, 0);
  await page.mouse.up();

  await checkIn.click();
  const pending = page.getByRole('button', { name: `${challenge.name} 했어요` });
  await expect(pending).toBeDisabled();
  await expect(pending).toHaveText('저장 중…');
  await expectClay(pending, 44);
  await pending.evaluate((element) => { element.style.transition = 'none'; });
  expect(await physical(pending)).toEqual(canonicalDisabledSurface);
  await pending.evaluate((button: HTMLButtonElement) => button.click());
  expect(verificationPosts).toBe(1);
  releaseVerification();
  await expect(page.getByText('완료', { exact: true })).toBeVisible();
  expect(verificationPosts).toBe(1);
  expect(unhandled).toEqual([]);
});

test('직접 설정과 등록 wizard의 선택 시간대는 같은 입체 표면과 선택 제한을 사용한다', async ({ page }) => {
  await page.goto('/dev/medication-schedule');
  const direct = page.getByRole('region', { name: '약별 복용 시간 확인' });
  const directSelected = direct.locator('button.rx-dose-slot[aria-pressed="true"]');
  await expect(directSelected.first()).toBeVisible();
  await expectSelectedSlotDepth(directSelected);
  await captureReviewScreenshot(page, 'task-1-dose-slots-direct-390.png');
  const directFirstName = await direct.getByRole('button', { pressed: true }).first().getAttribute('aria-label');
  expect(directFirstName).not.toBeNull();
  const directFirst = direct.getByRole('button', { name: directFirstName!, exact: true });
  await directFirst.click();
  await expect(directFirst).toHaveAttribute('aria-pressed', 'false');
  await directFirst.click();
  await expect(directFirst).toHaveAttribute('aria-pressed', 'true');

  await page.goto('/dev/medication-schedule?recordId=12&ocrJobId=102&flow=registration');
  const wizard = page.getByRole('main');
  const wizardSelected = wizard.locator('button.rx-dose-slot[aria-pressed="true"]');
  await expect(wizardSelected.first()).toBeVisible();
  await expectSelectedSlotDepth(wizardSelected);
  await captureReviewScreenshot(page, 'task-1-dose-slots-wizard-390.png');
  const group = wizard.getByRole('group').first();
  const before = await group.getByRole('button', { pressed: true }).count();
  await group.getByRole('button', { pressed: false }).first().click();
  await expect(group.getByRole('alert')).toContainText(`하루 ${before}회만 선택할 수 있어요`);
  await expect(group.getByRole('button', { pressed: true })).toHaveCount(before);
});

for (const width of [320, 390, 1280]) {
  test(`지정 compact 실행과 영양제 추가 패턴은 ${width}px에서 높이·문구를 보존한다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/dev/supplements');
    const report = page.getByRole('button', { name: 'AI 보고서 받기', exact: true });
    const add = page.getByRole('button', { name: '영양제 추가', exact: true });
    await expect(report).toHaveAttribute('data-size', 'compact');
    await expectClay(report, 44);
    await expect(add).toHaveAttribute('data-variant', 'secondary');
    await expect(add).toContainText('영양제 추가');
    await expectClay(add, 52);
    const icon = add.locator('svg');
    await expect(icon).toHaveCSS('width', '16px');
    await expect(icon).toHaveCSS('height', '16px');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 390) await captureReviewScreenshot(page, 'task-1-supplement-actions-390.png');
    await report.click();
    await expect(page).toHaveURL(/\/reports\/new\?source=supplements$/);

    await page.goto('/dev/medications');
    const medicationReport = page.getByRole('button', { name: 'AI 보고서 받기', exact: true });
    const medicationAdd = page.getByRole('button', { name: '처방 추가', exact: true });
    await expectClay(medicationReport, 44);
    await expectClay(medicationAdd, 52);
    if (width === 390) await captureReviewScreenshot(page, 'task-1-medication-actions-390.png');
    await medicationReport.click();
    await expect(page).toHaveURL(/\/reports\/new\?source=medications$/);
  });
}

test('챌린지·채팅 compact 실행은 긴 문구에서도 44px 높이와 내용을 보존한다', async ({ page }) => {
  await authenticate(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname === '/api/v1/user/challenges' && request.method() === 'GET') {
      return fulfillJson(route, { items: [participation(false)], total_count: 1 });
    }
    if (pathname === '/api/v1/user/custom-challenge-participations') {
      return fulfillJson(route, { items: [], totalCount: 0 });
    }
    if (pathname === '/api/v1/user/badges') {
      return fulfillJson(route, { items: [], total_count: 0 });
    }
    return fulfillJson(route, { message: '447 official challenge fixture missing' }, 503);
  });
  await page.goto('/challenges');
  await page.getByRole('button', { name: '진행 중인 챌린지 펼치기', exact: true }).click();
  const officialCard = page.getByRole('article', { name: challenge.name });
  const challengeButton = officialCard.locator('button.rx-button').last();
  await expect(challengeButton).toHaveText('했어요');
  await expect(challengeButton).toHaveAttribute('data-size', 'compact');
  await expectClay(challengeButton, 44);
  const originalLabel = await challengeButton.textContent();
  const longCompactLabel = '오늘 공식 챌린지 인증 기록을 다시 불러오기';
  await challengeButton.evaluate((element, label) => { element.textContent = label; }, longCompactLabel);
  await expect(challengeButton).toHaveText(longCompactLabel);
  expect(await challengeButton.evaluate((element) => ({
    horizontal: element.scrollWidth <= element.clientWidth + 1,
    vertical: element.scrollHeight <= element.clientHeight + 1,
  }))).toEqual({ horizontal: true, vertical: true });
  await challengeButton.evaluate((element, label) => { element.textContent = label; }, originalLabel);
  await expect(challengeButton).toHaveText('했어요');

  await page.evaluate(() => {
    localStorage.setItem('poke.mock-chat-sessions:issue-447%40example.com', JSON.stringify({
      nextSessionId: 78,
      nextMessageId: 1205,
      sessions: [{
        sessionId: 77,
        createdAt: '2026-09-10T09:00:00.000Z',
        lastMessageAt: '2026-09-10T09:01:00.000Z',
        messages: [
          { role: 'user', text: '긴 채팅 목록 문구가 줄바꿈되어도 높이는 안정적이어야 해요', sources: [] },
          { role: 'assistant', text: '안정적인 높이를 확인하는 답변입니다.', sources: [] },
        ],
      }],
    }));
  });
  await page.goto('/dev/chat');
  const newChat = page.getByRole('button', { name: '새 채팅', exact: true });
  await expect(newChat).toHaveAttribute('data-size', 'compact');
  await expectClay(newChat, 44);
  const longSession = page.getByRole('button', { name: /긴 채팅 목록 문구/ });
  const wideHeight = (await longSession.boundingBox())!.height;
  expect(wideHeight).toBeGreaterThanOrEqual(44);
  await page.setViewportSize({ width: 320, height: 844 });
  expect((await longSession.boundingBox())!.height).toBeCloseTo(wideHeight, 1);

  await page.goto('/dev/chat-history');
  const endChat = page.getByRole('button', { name: '채팅 종료', exact: true });
  await expect(endChat).toHaveAttribute('data-size', 'compact');
  await expectClay(endChat, 44);
});
