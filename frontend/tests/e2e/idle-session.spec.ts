import { expect, test, type Page, type Route } from 'playwright/test';
import { Buffer } from 'node:buffer';

const START = new Date('2026-09-14T09:00:00+09:00');
const IDLE_MS = 30 * 60 * 1_000;
const TOKEN = 'idle-session-access-token';
const PRINCIPAL = 'idle-session@example.com';
const ORIGIN = `http://127.0.0.1:${process.env.PLAYWRIGHT_TEST_PORT ?? '44175'}`;

type ApiTrace = {
  refreshes: Array<{ authorization: string | undefined; credentials: string | undefined }>;
  protectedCalls: number;
};

async function setClock(page: Page) {
  await page.clock.install({ time: START });
}

async function seedSession(page: Page, principal = PRINCIPAL, token = TOKEN) {
  await page.context().addCookies([
    { name: 'refresh_token', value: token, url: ORIGIN },
  ]);
  await page.addInitScript(
    ({ principalKey, accessToken }) => {
      sessionStorage.setItem('poke.access-token', accessToken);
      sessionStorage.setItem('poke.account-principal', principalKey);
    },
    { principalKey: principal, accessToken: token },
  );
}

async function installApiFixture(page: Page, options: {
  refresh?: (route: Route, trace: ApiTrace) => Promise<void>;
  protected?: (route: Route, trace: ApiTrace) => Promise<void>;
} = {}) {
  const trace: ApiTrace = { refreshes: [], protectedCalls: 0 };
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/auth/token/refresh') {
      trace.refreshes.push({
        authorization: request.headers().authorization,
        credentials: request.headers().cookie,
      });
      if (options.refresh) return options.refresh(route, trace);
      await route.fulfill({ json: { access_token: 'idle-session-refreshed-token' } });
      return;
    }
    if (path.startsWith('/api/v1/idle-probe')) {
      trace.protectedCalls += 1;
      if (options.protected) return options.protected(route, trace);
      await route.fulfill({ json: { ok: true } });
      return;
    }
    // Home is only the real screen host for this client-level contract. Keep all of
    // its unrelated API calls in-process so no provider/backend request can escape.
    await route.fulfill({ json: { items: [], total: 0, total_count: 0 } });
  });
  return trace;
}

async function openAuthenticatedProfile(
  page: Page,
  options?: Parameters<typeof installApiFixture>[1],
  token = TOKEN,
) {
  await setClock(page);
  await seedSession(page, PRINCIPAL, token);
  const trace = await installApiFixture(page, options);
  await page.goto('/my/profile');
  await expect(page).toHaveURL(/\/my\/profile$/);
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('poke.access-token'))).toBe(token);
  return trace;
}

function jwtExpiringAt(timestampMs: number) {
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(timestampMs / 1_000) })).toString('base64url');
  return `eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.${payload}.signature`;
}

async function sessionKeys(page: Page) {
  return page.evaluate(() => ({
    token: sessionStorage.getItem('poke.access-token'),
    principal: sessionStorage.getItem('poke.account-principal'),
  }));
}

async function issueProbe(page: Page, suffix: string) {
  return page.evaluate(async (path) => {
    const client = await import('/src/shared/api/client.ts');
    return client.http.get(path).then(
      () => ({ ok: true }),
      (error: Error) => ({ ok: false, message: error.message }),
    );
  }, `/v1/idle-probe/${suffix}`);
}

test.describe('30분 유휴 세션', () => {
  test('정확히 30분 동안 이 앱에서 활동하지 않으면 보호 세션을 비운다', async ({ page }) => {
    const trace = await openAuthenticatedProfile(page);

    await page.clock.fastForward(IDLE_MS);

    await expect(page).toHaveURL(/\/login$/);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: null, principal: null });
    expect(trace.refreshes).toHaveLength(0);
  });

  test('29분 59초의 실제 키 입력은 유휴 기한을 다시 30분으로 민다', async ({ page }) => {
    await openAuthenticatedProfile(page);

    await page.clock.fastForward(IDLE_MS - 1_000);
    await page.keyboard.press('Shift');
    await page.clock.fastForward(1_000);

    await expect(page).toHaveURL(/\/my\/profile$/);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: TOKEN, principal: PRINCIPAL });
    await page.clock.fastForward(IDLE_MS - 2_000);
    await expect(page).toHaveURL(/\/my\/profile$/);
    await page.clock.fastForward(1_000);
    await expect(page).toHaveURL(/\/login$/);
  });

  test('API 호출과 synthetic focus는 마지막 앱 활동을 갱신하지 않는다', async ({ page }) => {
    await openAuthenticatedProfile(page);

    await page.clock.fastForward(IDLE_MS - 1_000);
    await issueProbe(page, 'background-api');
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.clock.fastForward(1_000);

    await expect(page).toHaveURL(/\/login$/);
  });

  test('hidden 상태에서 발생한 이벤트는 마지막 앱 활동을 갱신하지 않는다', async ({ page }) => {
    await openAuthenticatedProfile(page);

    await page.clock.fastForward(IDLE_MS - 1_000);
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift' }));
    });
    await page.clock.fastForward(1_000);

    await expect(page).toHaveURL(/\/login$/);
  });

  test('다른 사이트 탭의 입력은 이 앱의 마지막 활동을 갱신하지 않는다', async ({ page, context }) => {
    await openAuthenticatedProfile(page);
    const otherSite = await context.newPage();
    try {
      await page.clock.fastForward(IDLE_MS - 1_000);
      await otherSite.goto('data:text/html,<button>other site</button>');
      await otherSite.getByRole('button', { name: 'other site' }).click();
      await page.clock.fastForward(1_000);

      await expect(page).toHaveURL(/\/login$/);
    } finally {
      await otherSite.close();
    }
  });

  test('같은 출처·같은 주체의 다른 탭 활동은 공유하고 다른 주체는 공유하지 않는다', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: ORIGIN });
    const active = await context.newPage();
    const peer = await context.newPage();
    const otherPrincipal = await context.newPage();
    try {
      for (const page of [active, peer, otherPrincipal]) await setClock(page);
      await seedSession(active, PRINCIPAL);
      await seedSession(peer, PRINCIPAL);
      await seedSession(otherPrincipal, 'different-principal@example.com');
      for (const page of [active, peer, otherPrincipal]) {
        await installApiFixture(page);
        await page.goto('/my/profile');
      }

      // Playwright's controlled clock is shared by pages in this browser context.
      await active.clock.fastForward(IDLE_MS - 60_000);
      await active.keyboard.press('Shift');
      await expect.poll(() => peer.evaluate(() => {
        const raw = localStorage.getItem('poke.session-activity:idle-session%40example.com');
        return raw ? JSON.parse(raw).at : null;
      })).toBeGreaterThanOrEqual(START.getTime() + IDLE_MS - 60_000);
      // The real storage event re-arms the peer's timer before its original deadline.
      await peer.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
      await peer.clock.fastForward(60_000);

      await expect(peer).toHaveURL(/\/my\/profile$/);
      await expect(otherPrincipal).toHaveURL(/\/login$/);
      await peer.clock.fastForward(IDLE_MS - 60_000 - 1_000);
      await expect(peer).toHaveURL(/\/my\/profile$/);
      await peer.clock.fastForward(1_000);
      await expect(peer).toHaveURL(/\/login$/);
    } finally {
      await context.close();
    }
  });

  test('동시 401은 bearer를 유지한 refresh 한 번으로 재시도한다', async ({ page }) => {
    const trace = await openAuthenticatedProfile(page, {
      protected: async (route, currentTrace) => {
        const authorization = route.request().headers().authorization;
        if (authorization === `Bearer ${TOKEN}`) {
          await route.fulfill({ status: 401, json: { code: 'INVALID_TOKEN' } });
          return;
        }
        expect(authorization).toBe('Bearer idle-session-refreshed-token');
        await route.fulfill({ json: { ok: true } });
      },
    });

    const result = await page.evaluate(async () => {
      const client = await import('/src/shared/api/client.ts');
      return Promise.all([client.http.get('/v1/idle-probe/a'), client.http.get('/v1/idle-probe/b')]);
    });

    expect(result).toEqual([{ ok: true }, { ok: true }]);
    expect(trace.refreshes).toHaveLength(1);
    expect(trace.refreshes[0]?.authorization).toBe(`Bearer ${TOKEN}`);
    expect(trace.refreshes[0]?.credentials).toContain(`refresh_token=${TOKEN}`);
    expect(await sessionKeys(page)).toEqual({ token: 'idle-session-refreshed-token', principal: PRINCIPAL });
  });

  test('refresh의 일시 500은 인증을 유지하지만 401은 로그아웃한다', async ({ page }) => {
    const trace = await openAuthenticatedProfile(page, {
      protected: async route => route.fulfill({ status: 401, json: { code: 'INVALID_TOKEN' } }),
      refresh: async (route, currentTrace) => {
        const status = currentTrace.refreshes.length === 1 ? 500 : 401;
        await route.fulfill({ status, json: { code: status === 500 ? 'TEMPORARY' : 'INVALID_REFRESH' } });
      },
    });

    await issueProbe(page, 'transient');
    expect(trace.refreshes).toHaveLength(1);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: TOKEN, principal: PRINCIPAL });

    await issueProbe(page, 'invalid');
    await expect(page).toHaveURL(/\/login$/);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: null, principal: null });
  });

  test('로그아웃 중 완료된 refresh 응답은 세션을 되살리지 않는다', async ({ page }) => {
    let releaseRefresh!: () => void;
    const refreshBlocked = new Promise<void>(resolve => { releaseRefresh = resolve; });
    const trace = await openAuthenticatedProfile(page, {
      protected: async route => route.fulfill({ status: 401, json: { code: 'INVALID_TOKEN' } }),
      refresh: async route => {
        await refreshBlocked;
        await route.fulfill({ json: { access_token: 'must-not-resurrect-token' } });
      },
    });

    const request = issueProbe(page, 'logout-race');
    await expect.poll(() => trace.refreshes.length).toBe(1);
    await page.evaluate(() => window.dispatchEvent(new Event('poke:auth-session-expired')));
    releaseRefresh();
    await request;

    await expect(page).toHaveURL(/\/login$/);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: null, principal: null });
  });

  test('2분 뒤 만료되는 JWT는 자동 갱신 후 원래 만료 시점을 지나도 인증을 유지하지만 유휴 30분에 끝난다', async ({
    page,
  }, testInfo) => {
    const token = jwtExpiringAt(START.getTime() + 120_000);
    const trace = await openAuthenticatedProfile(page, undefined, token);

    // SessionContext's 30초 timer, not a protected API 401, reaches the 60초 refresh window.
    await page.clock.fastForward(121_000);
    await expect.poll(() => trace.refreshes.length).toBe(1);
    await expect(page).toHaveURL(/\/my\/profile$/);
    await expect.poll(() => sessionKeys(page)).toEqual({
      token: 'idle-session-refreshed-token',
      principal: PRINCIPAL,
    });
    await page.screenshot({ path: testInfo.outputPath('jwt-auto-refresh-kept-session.png'), fullPage: true });

    // Refresh is background work: it must not move the activity deadline established at page load.
    await page.clock.fastForward(IDLE_MS - 121_000);
    await expect(page).toHaveURL(/\/login$/);
  });

  test('29분 뒤 새로고침해도 기존 유휴 기한을 연장하지 않는다', async ({ page }, testInfo) => {
    await setClock(page);
    await page.context().addCookies([{ name: 'refresh_token', value: TOKEN, url: ORIGIN }]);
    await page.addInitScript(({ principal, token }) => {
      // addInitScript is rerun by reload. Only the first document gets a legacy fixture session.
      if (sessionStorage.getItem('idle-session-reload-fixture-seeded')) return;
      sessionStorage.setItem('idle-session-reload-fixture-seeded', 'true');
      sessionStorage.setItem('poke.access-token', token);
      sessionStorage.setItem('poke.account-principal', principal);
    }, { principal: PRINCIPAL, token: TOKEN });
    await installApiFixture(page);
    await page.goto('/my/profile');
    await expect(page).toHaveURL(/\/my\/profile$/);

    await page.clock.fastForward(IDLE_MS - 60_000);
    await page.reload();
    await expect(page).toHaveURL(/\/my\/profile$/);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: TOKEN, principal: PRINCIPAL });
    await page.clock.fastForward(60_000);

    await expect(page).toHaveURL(/\/login$/);
    await expect.poll(() => sessionKeys(page)).toEqual({ token: null, principal: null });
    await page.screenshot({ path: testInfo.outputPath('reload-keeps-idle-deadline-expired.png'), fullPage: true });
  });

  test('이전 epoch 탭은 logout과 즉시 새 epoch가 coalesce돼도 새 marker를 종료하지 않고 스스로 만료된다', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: ORIGIN });
    const tabA = await context.newPage();
    const tabB = await context.newPage();
    try {
      let staleLogoutRequests = 0;
      await context.route('**/api/v1/auth/logout', route => {
        staleLogoutRequests += 1;
        return route.fulfill({ status: 200, body: '{}' });
      });
      await Promise.all([tabA.goto('/login'), tabB.goto('/login')]);
      await tabA.evaluate(async principal => {
        const activity = await import('/src/shared/api/sessionActivity.ts');
        activity.beginActivitySession(principal, 'same-server-session');
      }, PRINCIPAL);
      await tabB.evaluate(async principal => {
        // Simulate a suspended tab receiving only the final localStorage state.
        window.addEventListener('storage', event => event.stopImmediatePropagation(), true);
        const activity = await import('/src/shared/api/sessionActivity.ts');
        (window as Window & { idleChecks: number }).idleChecks = 0;
        activity.watchSessionActivity(principal, () => {
          (window as Window & { idleChecks: number }).idleChecks += 1;
        });
        // Logging into the same still-active server session joins the shared epoch.
        activity.beginActivitySession(principal, 'same-server-session');
      }, PRINCIPAL);
      expect(await tabA.evaluate(async principal => {
        const activity = await import('/src/shared/api/sessionActivity.ts');
        return activity.isSessionIdle(principal);
      }, PRINCIPAL)).toBe(false);

      const latest = await tabA.evaluate(async principal => {
        const activity = await import('/src/shared/api/sessionActivity.ts');
        activity.endActivitySession(principal);
        // Even if offline logout left the same cookie behind, this is a new local epoch.
        activity.beginActivitySession(principal, 'same-server-session');
        const raw = localStorage.getItem(`poke.session-activity:${encodeURIComponent(principal)}`);
        return raw ? JSON.parse(raw) : null;
      }, PRINCIPAL);

      expect(latest).toMatchObject({ ended: false });
      const staleTab = await tabB.evaluate(async principal => {
        const activity = await import('/src/shared/api/sessionActivity.ts');
        window.dispatchEvent(new Event('focus'));
        const raw = localStorage.getItem(`poke.session-activity:${encodeURIComponent(principal)}`);
        return {
          idle: activity.isSessionIdle(principal),
          idleChecks: (window as Window & { idleChecks: number }).idleChecks,
          marker: raw ? JSON.parse(raw) : null,
        };
      }, PRINCIPAL);

      expect(staleTab.idle).toBe(true);
      expect(staleTab.idleChecks).toBe(1);
      expect(staleTab.marker).toMatchObject({ ended: false });
      await tabB.evaluate(async principal => {
        const client = await import('/src/shared/api/client.ts');
        client.setAccountPrincipal(principal);
        client.setAccessToken('old-session-token');
        await client.endSession();
      }, PRINCIPAL);
      expect(staleLogoutRequests).toBe(0);
    } finally {
      await context.close();
    }
  });

  test('login 응답 대기 중 예약된 구 탭 logout은 새 epoch commit 뒤 쿠키를 건드리지 않는다', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: ORIGIN });
    const oldTab = await context.newPage();
    const newTab = await context.newPage();
    let releaseLogin!: () => void;
    const deferred = new Promise<void>(resolve => { releaseLogin = resolve; });
    let loginStarted = false;
    let logoutRequests = 0;
    try {
      await context.route('**/api/v1/auth/login', async route => {
        loginStarted = true;
        await deferred;
        await route.fulfill({ json: { access_token: 'new-token' } });
      });
      await context.route('**/api/v1/auth/logout', route => {
        logoutRequests += 1;
        return route.fulfill({ status: 200, body: '{}' });
      });
      await Promise.all([oldTab.goto('/login'), newTab.goto('/login')]);
      await oldTab.evaluate(async principal => {
        const activity = await import('/src/shared/api/sessionActivity.ts');
        const client = await import('/src/shared/api/client.ts');
        activity.beginActivitySession(principal);
        client.setAccountPrincipal(principal);
        client.setAccessToken('old-token');
      }, PRINCIPAL);
      const login = newTab.evaluate(async principal => {
        const client = await import('/src/shared/api/client.ts');
        await client.http.post('/v1/auth/login', { email: principal, password: 'Password123!' });
      }, PRINCIPAL);
      await expect.poll(() => loginStarted).toBe(true);
      const logout = oldTab.evaluate(async () => {
        const client = await import('/src/shared/api/client.ts');
        await client.endSession();
      });
      await expect.poll(async () => oldTab.evaluate(principal =>
        JSON.parse(localStorage.getItem(`poke.session-activity:${encodeURIComponent(principal)}`)!).ended, PRINCIPAL)).toBe(true);
      releaseLogin();
      await Promise.all([login, logout]);
      expect(logoutRequests).toBe(0);
    } finally { releaseLogin(); await context.close(); }
  });

  test('다른 탭 login은 보류된 logout 쿠키 정리 뒤에만 전송되며 navigator.locks fallback도 같다', async ({ browser }) => {
    async function assertCookieMutationOrder(disableNavigatorLocks: boolean) {
      const context = await browser.newContext({ baseURL: ORIGIN });
      if (disableNavigatorLocks) {
        await context.addInitScript(() => {
          Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
        });
      }
      const tabA = await context.newPage();
      const tabB = await context.newPage();
      let logoutRequests = 0;
      let loginRequests = 0;
      let releaseLogout!: () => void;
      let logoutReleased = false;
      const logoutDeferred = new Promise<void>(resolve => { releaseLogout = resolve; });
      try {
        await context.route(url => url.pathname === '/api/v1/auth/logout' || url.pathname === '/api/v1/auth/login', async route => {
          const path = new URL(route.request().url()).pathname;
          if (path === '/api/v1/auth/logout') {
            logoutRequests += 1;
            await logoutDeferred;
            await route.fulfill({ status: 204 });
            return;
          }
          loginRequests += 1;
          expect(logoutReleased).toBe(true);
          await route.fulfill({ json: { access_token: 'cross-tab-new-login-token' } });
        });
        await Promise.all([tabA.goto('/login'), tabB.goto('/login')]);

        const logout = tabA.evaluate(async principal => {
          const client = await import('/src/shared/api/client.ts');
          client.setAccessToken('cross-tab-old-token');
          client.setAccountPrincipal(principal);
          await client.endSession();
        }, PRINCIPAL);
        await expect.poll(() => logoutRequests).toBe(1);
        const login = tabB.evaluate(async () => {
          const client = await import('/src/shared/api/client.ts');
          return client.http.post('/v1/auth/login', { email: 'idle-session@example.com', password: 'Password123!' });
        });

        await tabB.waitForTimeout(100);
        expect(loginRequests).toBe(0);
        logoutReleased = true;
        releaseLogout();
        await logout;
        await expect.poll(() => loginRequests).toBe(1);
        await expect(login).resolves.toEqual({ access_token: 'cross-tab-new-login-token' });
      } finally {
        await context.close();
      }
    }

    await assertCookieMutationOrder(false);
    await assertCookieMutationOrder(true);
  });
});
