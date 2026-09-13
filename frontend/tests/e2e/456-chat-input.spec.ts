import { expect, test, type Locator, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(30_000);

interface TextareaMetrics {
  clientHeight: number;
  height: number;
  lineHeight: number;
  maxHeight: number;
  overflowY: string;
  scrollHeight: number;
  scrollWidth: number;
  clientWidth: number;
}

async function openEmptyChat(page: Page) {
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
  await page.goto('/dev/chat');
  await page.evaluate(() => localStorage.removeItem('poke.mock-chat-sessions:guest'));
  await page.reload();
  return page.getByRole('textbox', { name: '질문 입력' });
}

async function readMetrics(composer: Locator): Promise<TextareaMetrics> {
  return composer.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement;
    const style = getComputedStyle(textarea);
    const lineHeight = Number.parseFloat(style.lineHeight);
    const verticalChrome =
      Number.parseFloat(style.paddingTop)
      + Number.parseFloat(style.paddingBottom)
      + Number.parseFloat(style.borderTopWidth)
      + Number.parseFloat(style.borderBottomWidth);

    return {
      clientHeight: textarea.clientHeight,
      height: textarea.getBoundingClientRect().height,
      lineHeight,
      maxHeight: lineHeight * 5 + verticalChrome,
      overflowY: style.overflowY,
      scrollHeight: textarea.scrollHeight,
      scrollWidth: textarea.scrollWidth,
      clientWidth: textarea.clientWidth,
    };
  });
}

test('긴어지는 질문은 5줄까지 커지고 이후 내부 스크롤하며 전송 후 줄어든다', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const composer = await openEmptyChat(page);

  await expect(composer).toHaveJSProperty('tagName', 'TEXTAREA');
  const initial = await readMetrics(composer);

  await composer.fill('바로 줄바꿈되어야 하는 아주 긴 질문입니다. '.repeat(30));
  await expect.poll(async () => (await readMetrics(composer)).height).toBeGreaterThan(initial.height);

  const capped = await readMetrics(composer);
  expect(Math.abs(capped.height - capped.maxHeight)).toBeLessThanOrEqual(1);
  expect(capped.scrollHeight).toBeGreaterThan(capped.clientHeight);
  expect(capped.overflowY).toBe('auto');
  expect(capped.scrollWidth).toBeLessThanOrEqual(capped.clientWidth);

  await page.screenshot({ path: testInfo.outputPath('chat-composer-wrapped-390.png'), fullPage: true });
  await page.getByRole('button', { name: '보내기' }).click();

  await expect(composer).toHaveValue('');
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  await expect.poll(async () => (await readMetrics(composer)).height).toBe(initial.height);
});

test('Shift+Enter는 줄바꿈하고 Enter는 기존처럼 trim한 질문을 한 번 전송한다', async ({ page }) => {
  const composer = await openEmptyChat(page);

  await composer.fill('  첫 줄');
  await composer.press('Shift+Enter');
  await composer.pressSequentially('둘째 줄  ');
  await expect(composer).toHaveValue('  첫 줄\n둘째 줄  ');

  await composer.press('Enter');
  await expect(page.getByText('첫 줄\n둘째 줄', { exact: true })).toBeVisible();
  await expect(composer).toHaveValue('');

  await expect.poll(async () => page.evaluate(() => {
    const raw = localStorage.getItem('poke.mock-chat-sessions:guest');
    if (!raw) return [];
    const store = JSON.parse(raw) as {
      sessions: Array<{ messages: Array<{ role: string; text: string }> }>;
    };
    return store.sessions.flatMap(session => session.messages)
      .filter(message => message.role === 'user')
      .map(message => message.text);
  })).toEqual(['첫 줄\n둘째 줄']);
});

test('한글 IME 조합 중 Enter는 전송하지 않는다', async ({ page }) => {
  const composer = await openEmptyChat(page);
  const composingQuestion = '한글 조합 중 질문';
  await composer.fill(composingQuestion);

  await composer.dispatchEvent('compositionstart');
  await composer.dispatchEvent('keydown', {
    key: 'Enter',
    code: 'Enter',
    isComposing: true,
    bubbles: true,
  });

  await expect(composer).toHaveValue(composingQuestion);
  const sentQuestion = page.locator('.chat-user-bubble').filter({ hasText: composingQuestion });
  await expect(sentQuestion).toHaveCount(0);

  await composer.dispatchEvent('compositionend');
  await composer.press('Enter');
  await expect(sentQuestion).toBeVisible();
});
