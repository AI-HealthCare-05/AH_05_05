import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
// WSL's mounted checkout can need more than 60s for Vite's first cold transform.
test.setTimeout(120_000);

const ACCESS_TOKEN = 'issue-431-ui-token';

test.beforeEach(async ({ page }) => {
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
  await page.addInitScript((token) => {
    sessionStorage.setItem('poke.access-token', token);
    sessionStorage.setItem('poke.account-principal', 'issue-431@example.com');
  }, ACCESS_TOKEN);
  await page.route('**/api/v1/**', route => route.fulfill({ status: 200, json: {} }));
});

test('PC 최근 대화의 긴 제목과 미리보기가 행과 뷰포트 밖으로 넘치지 않는다', async ({ page }, testInfo) => {
  const title = `PC긴제목-${'가'.repeat(320)}`;
  const preview = `PC긴미리보기-${'나'.repeat(640)}`;
  await page.route('**/api/v1/chat/sessions', route => route.fulfill({
    status: 200,
    json: {
      items: [{
        sessionId: 431,
        title,
        lastMessagePreview: preview,
        lastMessageAt: '2026-09-12T09:00:00+09:00',
      }],
    },
  }));

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/chat', { waitUntil: 'domcontentloaded' });
  const row = page.getByRole('button', { name: /PC긴제목/ });
  await expect(row).toBeVisible();
  const measurement = await row.evaluate((element) => {
    const rowRect = element.getBoundingClientRect();
    const textRects = [...element.querySelectorAll('span')].map(node => {
      const rect = node.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        clientWidth: (node as HTMLElement).clientWidth,
        scrollWidth: (node as HTMLElement).scrollWidth,
        overflowX: getComputedStyle(node).overflowX,
        textOverflow: getComputedStyle(node).textOverflow,
      };
    });
    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      rowLeft: rowRect.left,
      rowRight: rowRect.right,
      rowClientWidth: (element as HTMLElement).clientWidth,
      rowScrollWidth: (element as HTMLElement).scrollWidth,
      textRects,
    };
  });
  await testInfo.attach('pc-recent-conversation-measurement.json', {
    body: Buffer.from(JSON.stringify(measurement, null, 2)),
    contentType: 'application/json',
  });
  await page.screenshot({ path: testInfo.outputPath('pc-recent-conversation-1440.png'), fullPage: true });

  expect(measurement.documentScrollWidth).toBeLessThanOrEqual(measurement.viewportWidth);
  expect(measurement.rowScrollWidth).toBeLessThanOrEqual(measurement.rowClientWidth);
  for (const text of measurement.textRects) {
    expect(text.left).toBeGreaterThanOrEqual(measurement.rowLeft);
    expect(text.right).toBeLessThanOrEqual(measurement.rowRight);
    expect(text.overflowX).toBe('hidden');
    expect(text.textOverflow).toBe('ellipsis');
    expect(text.scrollWidth).toBeGreaterThan(text.clientWidth);
  }
});

test('대화방 AI 아바타는 플로팅 챗봇과 같은 병아리 알약 캐릭터를 쓴다', async ({ page }, testInfo) => {
  let releaseReply!: () => void;
  const pendingReply = new Promise<void>(resolve => { releaseReply = resolve; });
  await page.route('**/api/v1/chat/sessions', route => route.fulfill({
    status: 200,
    json: {
      items: [{
        sessionId: 431,
        title: '아바타 확인 상담',
        lastMessagePreview: '병아리 알약 캐릭터로 답변했어요.',
        lastMessageAt: '2026-09-12T09:00:00+09:00',
      }],
    },
  }));
  await page.route('**/api/v1/chat/sessions/431', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        sessionId: 431,
        messages: [
          { messageId: 1, role: 'USER', content: '아바타를 확인할게요.', status: 'COMPLETED', sources: [] },
          { messageId: 2, role: 'ASSISTANT', content: '병아리 알약 캐릭터로 답변했어요.', status: 'COMPLETED', sources: [] },
        ],
      },
      error: null,
    },
  }));
  await page.route('**/api/v1/chat/stream', async route => {
    await pendingReply;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: complete\ndata: {"conversationId":431,"messageId":3,"answer":"추가 답변이에요.","sources":[]}\n\n',
    });
  });

  await page.goto('/chat');
  await page.getByRole('button', { name: /아바타 확인 상담/ }).click();
  await expect(page.getByText('병아리 알약 캐릭터로 답변했어요.', { exact: true })).toBeVisible();
  const avatar = page.getByRole('main').locator('img').first();
  await expect(avatar).toHaveAttribute('src', '/images/default-profile.png');
  const avatarPresentation = await avatar.evaluate(image => ({
    renderedWidth: image.getBoundingClientRect().width,
    frameOverflow: getComputedStyle(image.parentElement!).overflow,
  }));
  expect(avatarPresentation.renderedWidth).toBeGreaterThanOrEqual(42);
  expect(avatarPresentation.frameOverflow).toBe('hidden');

  await page.getByRole('textbox', { name: '질문 입력' }).fill('대기 아바타도 확인해요.');
  await page.getByRole('button', { name: '보내기' }).click();
  const pendingAvatar = page.getByRole('main').locator('img').last();
  await expect(pendingAvatar).toHaveAttribute('src', '/images/default-profile.png');
  expect(await pendingAvatar.evaluate(image => image.getBoundingClientRect().width)).toBeGreaterThanOrEqual(42);

  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    await page.screenshot({ path: testInfo.outputPath(`chat-avatar-${width}.png`), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  releaseReply();
  await expect(page.getByText('추가 답변이에요.', { exact: true })).toBeVisible();
});

for (const source of ['medications', 'supplements']) {
test(`보고서 ${source} 생성 대기는 말풍선과 움직이는 점으로 표시하며 중복 요청을 막는다`, async ({ page }, testInfo) => {
  let requests = 0;
  let release!: () => void;
  const pendingResponse = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/intake-reports', async route => {
    requests += 1;
    await pendingResponse;
    await route.fulfill({ status: 504, json: { code: 'TIMEOUT', message: '테스트 종료' } });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/reports/new?source=${source}`);
  const generateButton = page.getByRole('button', { name: '보고서 생성하기', exact: true });
  await generateButton.evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });

  const pendingButton = page.getByRole('button', { name: '보고서 생성 중', exact: true });
  await expect(pendingButton).toBeDisabled();
  await expect(pendingButton).toHaveAttribute('aria-busy', 'true');
  const status = page.getByRole('status');
  await expect(status).toHaveCount(1);
  await expect(status).toContainText('보고서 생성 중 (최대 2분 소요)');
  const surface = await status.evaluate(element => {
    const style = getComputedStyle(element);
    return { border: parseFloat(style.borderTopWidth), radius: parseFloat(style.borderTopRightRadius), shadow: style.boxShadow, background: style.backgroundColor };
  });
  expect(surface.border).toBeGreaterThanOrEqual(1);
  expect(surface.radius).toBeGreaterThanOrEqual(20);
  expect(surface.shadow).not.toBe('none');
  expect(surface.background).not.toBe('rgba(0, 0, 0, 0)');
  const dots = status.locator('[data-chat-pending-dot]');
  await expect(dots).toHaveCount(5);
  await expect(status.locator('[data-chat-pending-loader]')).toHaveAttribute('aria-hidden', 'true');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const animation = await dots.first().evaluate(async element => {
    const motion = element.getAnimations()[0];
    if (!motion) return null;
    await motion.ready;
    const initial = Number(motion.currentTime);
    const transform = getComputedStyle(element).transform;
    await new Promise(resolve => setTimeout(resolve, 220));
    return { elapsed: Number(motion.currentTime) - initial, changed: transform !== getComputedStyle(element).transform };
  });
  expect(animation?.elapsed).toBeGreaterThan(100);
  expect(animation?.changed).toBe(true);
  await expect(pendingButton.locator('.rx-button-spinner')).toHaveCount(0);
  expect(requests).toBe(1);
  for (const width of [375, 390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const layout = await status.evaluate(element => {
      const box = element.getBoundingClientRect();
      const loader = element.querySelector('[data-chat-pending-loader]')!.getBoundingClientRect();
      return { boxRight: box.right, loaderRight: loader.right, loaderLeft: loader.left, boxLeft: box.left, overflow: element.scrollWidth > element.clientWidth };
    });
    expect(layout.loaderRight).toBeLessThanOrEqual(layout.boxRight);
    expect(layout.loaderLeft).toBeGreaterThanOrEqual(layout.boxLeft);
    expect(layout.overflow).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`report-loading-${width}.png`), fullPage: true });
  }
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const dot of await dots.all()) {
    await expect(dot).toHaveCSS('animation-name', 'none');
    expect(await dot.evaluate(element => element.getAnimations().length)).toBe(0);
  }

  release();
  await expect(page.getByRole('alert')).toContainText('테스트 종료');
  await expect(status).toHaveCount(0);
  await expect(page.getByRole('button', { name: '다시 시도', exact: true })).toBeEnabled();
});
}
