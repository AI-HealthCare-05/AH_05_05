import { writeFile } from 'node:fs/promises';
import { expect, test, type Page, type TestInfo } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(30_000);

async function sendMockQuestion(page: Page) {
  // /dev/chat routes through the real ChatPage with deterministic injected loaders.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('지금 먹는 약을 같이 먹어도 되나요?');
  await page.getByRole('button', { name: '보내기' }).click();
}

async function captureState(
  page: Page,
  testInfo: TestInfo,
  name: string,
  state: string,
) {
  const screenshotPath = testInfo.outputPath(`${name}.png`);
  const manifestPath = testInfo.outputPath(`${name}.manifest.json`);

  await page.screenshot({ path: screenshotPath });
  await writeFile(
    manifestPath,
    `${JSON.stringify({
      state,
      viewport: page.viewportSize(),
      data: 'VITE_USE_MOCK deterministic /dev/chat fixture',
      url: page.url(),
    }, null, 2)}\n`,
    'utf8',
  );
}

test('실제 답변 대기 동안에만 기존 문구 옆 6px 5점 로더를 표시한다', async ({ page }, testInfo) => {
  await sendMockQuestion(page);

  const progressMessage = page.getByText('질문 확인 중', { exact: true });
  const loader = page.locator('[data-chat-pending-loader]');
  await expect(progressMessage).toBeVisible();
  await expect(loader).toBeVisible();
  await expect(loader).toHaveAttribute('aria-hidden', 'true');
  await expect(loader.locator('[data-chat-pending-dot]')).toHaveCount(5);

  const geometry = await loader.evaluate((element) => {
    const dots = [...element.querySelectorAll<HTMLElement>('[data-chat-pending-dot]')];
    const firstStyle = getComputedStyle(dots[0]);
    const loaderStyle = getComputedStyle(element);
    return {
      width: firstStyle.width,
      height: firstStyle.height,
      gap: loaderStyle.columnGap,
    };
  });
  expect(geometry).toEqual({ width: '6px', height: '6px', gap: '4px' });
  await captureState(
    page,
    testInfo,
    'chat-pending-390x844',
    'pending: progressMessage + animated five-dot loader',
  );

  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  await expect(loader).toHaveCount(0);
});

test('움직임 줄이기에서는 대기 5점을 유지하되 반복 애니메이션은 정지한다', async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await sendMockQuestion(page);

  const dots = page.locator('[data-chat-pending-dot]');
  await expect(dots).toHaveCount(5);
  await expect(dots.first()).toHaveCSS('animation-name', 'none');
  await captureState(
    page,
    testInfo,
    'chat-pending-reduced-motion-390x844',
    'pending: static five-dot loader with prefers-reduced-motion',
  );

  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  const sourcesChevron = page.locator('.chat-sources-chevron');
  await expect(sourcesChevron).toBeVisible();
  await expect(sourcesChevron).toHaveCSS('transition-property', 'none');
});

test('근거 accordion은 기본 접힘과 내용을 유지하고 짧은 높이 전환으로 펼친다', async ({ page }, testInfo) => {
  await sendMockQuestion(page);
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  const toggle = page.getByRole('button', { name: '근거 보기 2개' });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  const contentId = await toggle.getAttribute('aria-controls');
  expect(contentId).toBeTruthy();

  const panel = page.locator(`#${contentId}`);
  await expect(panel).toHaveAttribute('aria-hidden', 'true');
  await expect(page.getByRole('link', { name: '새 창에서 열기' })).toHaveCount(0);
  await captureState(
    page,
    testInfo,
    'chat-sources-collapsed-390x844',
    'answer complete: sources collapsed by default',
  );

  await toggle.click();
  const collapse = page.getByRole('button', { name: '근거 접기 2개' });
  await expect(collapse).toHaveAttribute('aria-expanded', 'true');
  await expect(panel).toHaveAttribute('aria-hidden', 'false');
  await expect(page.getByRole('heading', { name: '근거' })).toBeVisible();
  await expect(page.getByText('내 문서', { exact: true })).toBeVisible();
  await expect(page.getByText('공식 자료', { exact: true })).toBeVisible();
  await expect(page.getByText('식품의약품안전처', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '새 창에서 열기' })).toHaveAttribute(
    'href',
    'https://nedrug.mfds.go.kr',
  );

  const transitionMilliseconds = await panel.evaluate((element) => {
    const values = getComputedStyle(element).transitionDuration.split(',');
    return Math.max(
      ...values.map((value) =>
        value.trim().endsWith('ms')
          ? Number.parseFloat(value)
          : Number.parseFloat(value) * 1_000,
      ),
    );
  });
  expect(transitionMilliseconds).toBeGreaterThan(0);
  expect(transitionMilliseconds).toBeLessThanOrEqual(220);
  await expect(panel).toHaveCSS('opacity', '1');
  const nestedShadow = await page.locator('.chat-sources-accordion').evaluate(
    element => getComputedStyle(element).boxShadow,
  );
  expect((nestedShadow.match(/inset/g) ?? []).length).toBeGreaterThanOrEqual(2);
  expect(nestedShadow).toMatch(/0px 2px 4px/);
  await captureState(
    page,
    testInfo,
    'chat-sources-expanded-390x844',
    'answer complete: sources expanded with original labels and links',
  );

  await collapse.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(panel).toHaveAttribute('aria-hidden', 'true');
  await expect(panel).toHaveCSS('opacity', '0');
  await captureState(
    page,
    testInfo,
    'chat-sources-recollapsed-390x844',
    'answer complete: sources collapsed again',
  );
});
