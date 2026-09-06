import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(30_000);

async function openAnsweredChat(page: Page) {
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('지금 먹는 약을 같이 먹어도 되나요?');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
}

test('평가 사유는 공통코드 다섯 개를 표시하고 처음에는 선택하지 않는다', async ({ page }) => {
  await openAnsweredChat(page);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  const endSheet = page.getByRole('dialog', { name: '상담 종료' });
  await endSheet.getByRole('button', { name: '좋아요' }).click();

  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  const reasonButtons = positiveSheet.locator('button[aria-pressed]');
  await expect(reasonButtons).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    await expect(reasonButtons.nth(index)).toHaveAttribute('aria-pressed', 'false');
  }
});

test('선택한 평가 사유는 코드로 저장되고 사유를 해제해도 제출할 수 있다', async ({ page }) => {
  await openAnsweredChat(page);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '좋아요' }).click();

  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  const reasonButtons = positiveSheet.locator('button[aria-pressed]');
  await expect(reasonButtons).toHaveCount(5);
  await reasonButtons.nth(1).click();
  await expect(reasonButtons.nth(1)).toHaveAttribute('aria-pressed', 'true');
  await reasonButtons.nth(1).click();
  await expect(reasonButtons.nth(1)).toHaveAttribute('aria-pressed', 'false');
  await positiveSheet.getByRole('button', { name: '제출하고 종료' }).click();

  await expect(page.getByRole('dialog')).toHaveCount(0);
  const sessions = await page.evaluate(() => {
    const raw = localStorage.getItem('poke.mock-chat-sessions:guest');
    return raw
      ? (JSON.parse(raw) as {
          sessions: Array<{ isLike?: boolean | null; reasonCode?: string | null }>;
        }).sessions
      : [];
  });
  expect(sessions.at(-1)).toMatchObject({ isLike: true, reasonCode: null });
});

test('평가 사유는 좁은 화면에서도 세로 전체 너비로 보이고 제출 버튼은 고정된다', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 360 });
  await openAnsweredChat(page);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '좋아요' }).click();

  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  const reasonArea = positiveSheet.getByRole('region', { name: '평가 사유' });
  const reasonButtons = reasonArea.locator('button[aria-pressed]');
  await expect(reasonButtons).toHaveCount(5);

  const boxes = await reasonButtons.evaluateAll((buttons) =>
    buttons.map((button) => {
      const box = button.getBoundingClientRect();
      return { x: box.x, width: box.width, height: box.height };
    }),
  );
  expect(boxes.every((box) => box.width >= 300 && box.height >= 44)).toBe(true);
  expect(new Set(boxes.map((box) => box.x)).size).toBe(1);

  const reasonsOverflow = await reasonArea.evaluate((element) => ({
    scrollable: element.scrollHeight > element.clientHeight,
    bottom: element.getBoundingClientRect().bottom,
  }));
  expect(reasonsOverflow.scrollable).toBe(true);

  const submit = positiveSheet.getByRole('button', { name: '제출하고 종료' });
  await expect(submit).toBeVisible();
  const submitBox = await submit.boundingBox();
  expect(submitBox).not.toBeNull();
  expect((submitBox?.y ?? 0) + (submitBox?.height ?? 0)).toBeLessThanOrEqual(360);
});
