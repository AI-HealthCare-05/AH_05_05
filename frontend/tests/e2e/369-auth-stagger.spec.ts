import { expect, test, type Page } from 'playwright/test';

// Browser rendering, controlled inputs, validation and navigation remain real.
// Only the external API boundary is intercepted; Vite /src/**/api/** is untouched.
async function isolateApi(page: Page) {
  const requests: { path: string; body: unknown }[] = [];
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname;
    requests.push({ path, body: route.request().postDataJSON() });
    let status = 500;
    let body: unknown = {};
    if (path === '/api/v1/auth/email-verifications') {
      status = 202; body = { verification_id: 41, expires_in: 180, resend_available_in: 60 };
    } else if (path === '/api/v1/auth/email-verifications/41/verify') {
      status = 200; body = { verification_token: 'verification-token', expires_in: 600 };
    } else if (path === '/api/v1/auth/login') {
      status = 400; body = { code: 'INVALID_CREDENTIALS', message: '테스트 로그인 오류' };
    } else if (path === '/api/v1/auth/signup') {
      status = 503; body = { code: 'SIGNUP_UNAVAILABLE', message: '테스트 가입 오류' };
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return requests;
}

async function openSignup(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
}

async function toPassword(page: Page) {
  await page.getByLabel('이메일', { exact: true }).fill('stagger@example.com');
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await page.getByLabel('인증코드').fill('123456');
  await page.getByRole('button', { name: '확인', exact: true }).click();
}

// Capturing animationstart through Element.animate avoids wall-clock races on
// shared CI hosts. Assertions inspect real rendered group motion and hierarchy.
async function captureEntrances(page: Page) {
  await page.addInitScript(() => {
    const original = Element.prototype.animate;
    (window as any).__entrances = [];
    Element.prototype.animate = function (...args) {
      const animation = original.apply(this, args);
      if (!this.classList.contains('auth-enter')) return animation;
      // StrictMode cancels and recreates the same mount entrance before paint.
      (window as any).__entrances = (window as any).__entrances.filter((entry: any) => entry.element !== this);
      (window as any).__entrances.push({
        element: this, animation,
        label: this.querySelector('label, legend')?.textContent || this.textContent,
      });
      return animation;
    };
  });
}

async function clearEntrances(page: Page) {
  await page.evaluate(() => { (window as any).__entrances = []; });
}

async function expectSequence(page: Page, labels: string[]) {
  await expect.poll(() => page.evaluate(() => (window as any).__entrances.length)).toBe(labels.length);
  const entries = await page.evaluate(() => (window as any).__entrances.map((entry: any) => ({
    label: entry.label,
    delay: entry.animation.effect.getTiming().delay,
    frames: entry.animation.effect.getKeyframes().map((frame: any) => ({ opacity: frame.opacity, transform: frame.transform })),
  })));
  expect(entries.map((entry: any) => entry.label)).toEqual(labels);
  expect(entries.map((entry: any) => entry.delay)).toEqual(labels.map((_, i) => i * 80));
  for (const entry of entries) {
    expect(entry.frames).toEqual([{ opacity: '0', transform: 'translateY(8px)' }, { opacity: '1', transform: 'translateY(0px)' }]);
  }
  const opacities = await page.evaluate(() => {
    const entries = (window as any).__entrances;
    entries.forEach((entry: any) => { entry.animation.pause(); entry.animation.currentTime = 120; });
    const values = entries.map((entry: any) => Number(getComputedStyle(entry.element).opacity));
    entries.forEach((entry: any) => entry.animation.finish());
    return values;
  });
  expect(opacities[0]).toBeGreaterThan(opacities[1]);
  expect(opacities[1]).toBeGreaterThan(opacities[2]);
  expect(opacities[2]).toBe(0);
}

for (const width of [320, 390, 1280]) {
  test(`login shares signup background and heading Y at ${width}px`, async ({ page }, testInfo) => {
    await isolateApi(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/login');
    const loginHeading = await page.getByRole('heading', { name: '다시 만나서 반가워요' }).boundingBox();
    const loginBg = await page.locator('main').evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor);
    await expect(page.getByRole('progressbar')).toHaveCount(0);
    const tab = page.getByRole('group', { name: '인증 방식' }).getByRole('button', { name: '로그인', exact: true });
    const colors = await tab.evaluate((el) => {
      const textSurface = el.querySelector('span') || el;
      return { text: getComputedStyle(textSurface).color, background: getComputedStyle(textSurface).backgroundColor };
    });
    expect.soft(colors.text).not.toBe(colors.background);
    await page.screenshot({ path: testInfo.outputPath(`login-${width}.png`), fullPage: true });
    await page.getByRole('button', { name: '회원가입', exact: true }).click();
    const signupHeading = await page.getByRole('heading', { name: '이메일을 알려주세요' }).boundingBox();
    const signupBg = await page.locator('main').evaluate((el) => getComputedStyle(el.parentElement!).backgroundColor);
    expect.soft(loginBg).toBe(signupBg);
    expect.soft(loginHeading!.y).toBe(signupHeading!.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await page.screenshot({ path: testInfo.outputPath(`signup-${width}.png`), fullPage: true });
  });
}

test('title, description, then whole input groups enter once per mode or step', async ({ page }, testInfo) => {
  await isolateApi(page);
  await captureEntrances(page);
  await page.goto('/login');
  await expectSequence(page, ['다시 만나서 반가워요', '로그인하면 저장한 복용약과 영양제를 이어서 볼 수 있어요.', '이메일', '비밀번호']);
  await clearEntrances(page);
  await page.getByLabel('이메일', { exact: true }).fill('stagger@example.com');
  await page.getByLabel('비밀번호', { exact: true }).fill('WrongPassword1!');
  await page.locator('form').getByRole('button', { name: '로그인', exact: true }).click();
  await expect(page.getByText('테스트 로그인 오류')).toBeVisible();
  await expect(page.getByLabel('비밀번호', { exact: true })).toHaveValue('WrongPassword1!');
  expect(await page.evaluate(() => (window as any).__entrances.length)).toBe(0);
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  await expectSequence(page, ['이메일을 알려주세요', '인증 메일을 보내드릴 주소예요.', '이메일']);
  await page.getByLabel('이메일', { exact: true }).fill('stagger@example.com');
  await clearEntrances(page);
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await expectSequence(page, ['메일함을 확인해주세요', 'stagger@example.com 으로 6자리 코드를 보냈어요.', '인증코드']);
  await page.getByLabel('인증코드').fill('123456');
  await clearEntrances(page);
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await expectSequence(page, ['비밀번호를 정해주세요', '로그인할 때 쓸 비밀번호예요. 한글은 쓸 수 없어요.', '비밀번호', '비밀번호 확인']);
  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('Password123!');
  await clearEntrances(page);
  await page.getByRole('button', { name: '다음', exact: true }).click();
  await expectSequence(page, ['마지막이에요', '이름', '전화번호', '생년월일', '성별', '필수 동의']);
  await page.screenshot({ path: testInfo.outputPath('signup-step4.png'), fullPage: true, animations: 'disabled' });
});

test('reduced motion is immediate and focusing an entering field reveals its entire group', async ({ page }) => {
  await isolateApi(page);
  await captureEntrances(page);
  await page.goto('/login');
  await page.evaluate(() => (window as any).__entrances.forEach((entry: any) => {
    entry.animation.pause(); entry.animation.currentTime = 0;
  }));
  const group = page.getByLabel('비밀번호', { exact: true }).locator('../..');
  await expect(group).toHaveCSS('opacity', '0');
  await page.getByLabel('비밀번호', { exact: true }).focus();
  await expect(page.getByLabel('비밀번호', { exact: true })).toBeFocused();
  await expect(group).toHaveCSS('opacity', '1');
  await expect(group).toHaveCSS('transform', 'none');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await clearEntrances(page);
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  expect(await page.evaluate(() => (window as any).__entrances.length)).toBe(0);
  await expect(page.getByRole('heading', { name: '이메일을 알려주세요' })).toHaveCSS('opacity', '1');
});

test('signup validation, back navigation and request payload survive entrance transitions', async ({ page }) => {
  const requests = await isolateApi(page);
  await openSignup(page);
  await toPassword(page);
  await page.getByLabel('비밀번호', { exact: true }).fill('1234');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('1234');
  await page.getByRole('button', { name: '다음', exact: true }).click();
  await expect(page.getByText('비밀번호는 8자 이상이어야 합니다.')).toBeVisible();
  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('Password123!');
  await page.getByRole('button', { name: '다음', exact: true }).click();
  await page.getByLabel('이름', { exact: true }).fill('테스트');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page.getByLabel('비밀번호', { exact: true })).toHaveValue('Password123!');
  await page.getByRole('button', { name: '다음', exact: true }).click();
  await expect(page.getByLabel('이름', { exact: true })).toHaveValue('테스트');
  await page.getByLabel('전화번호').fill('01012345678');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  for (const name of [/서비스 이용약관에 동의해요/, /개인정보 수집 및 이용에 동의해요/, /만 14세 이상이에요/, /진료기록 수집 및 이용에 동의해요/, /AI 서비스 이용에 동의해요/]) {
    await page.getByRole('checkbox', { name }).check();
  }
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page.getByRole('alert')).toHaveText('테스트 가입 오류');
  expect(requests.find((entry) => entry.path === '/api/v1/auth/signup')?.body).toEqual({
    email: 'stagger@example.com', password: 'Password123!', name: '테스트',
    phone_number: '01012345678', birth_date: '1990-01-01', gender: 'FEMALE',
    is_terms_agreed: true, email_verification_token: 'verification-token',
  });
});
