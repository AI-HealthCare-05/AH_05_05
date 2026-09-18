import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.skip(IS_REAL_API, MOCK_ONLY_REASON);
test.setTimeout(60_000);

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => route.fulfill({ json: { items: [], total_count: 0 } }));
});

for (const sample of [
  { name: '한 개 물결표로 연결된 수치 범위', text: '표시 검증: 6~8시간 간격, 1~2개, 250~500mg 범위입니다.' },
  { name: '두 개 물결표와 강조 안의 범위', text: '표시 검증: ~~원문~~, **6~8시간 및 250~500mg** 범위입니다.' },
]) {
  test(`${sample.name}는 취소선 없이 원문의 물결표를 보존한다`, async ({ page }, testInfo) => {
    await page.addInitScript(({ answer }) => {
      sessionStorage.setItem('poke.access-token', 'markdown-test');
      sessionStorage.setItem('poke.account-principal', 'markdown@example.invalid');
      localStorage.setItem('poke.mock-chat-sessions:markdown%40example.invalid', JSON.stringify({
        nextSessionId: 78, nextMessageId: 1205,
        sessions: [{ sessionId: 77, createdAt: '2026-09-18T00:00:00Z', lastMessageAt: '2026-09-18T00:00:00Z', messages: [
          { role: 'user', text: '물결표 표시 검증', sources: [] },
          { role: 'assistant', text: answer, sources: [] },
        ] }],
      }));
    }, { answer: sample.text + '\n\n| 구분 | 범위 |\n| --- | --- |\n| A | 1~2 / 3~4 |\n\n`~~코드~~`\n\n[원문 링크](https://example.com/~demo?q=~~value~~)\n\n\\~이스케이프\\~\n\n~~~text\n~~코드 블록~~\n~~~' });
    await page.goto('/chat');
    await page.getByRole('button', { name: /^물결표 표시 검증/ }).click();
    const body = page.getByLabel('답변 본문');
    await expect(body).toBeVisible();
    await body.locator('p').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('chat-tildes.png'), fullPage: true });
    await expect(body.locator('del, s')).toHaveCount(0);
    await expect(body.locator('p').first()).toHaveText(sample.text.replaceAll('**', ''));
    if (sample.name.startsWith('두')) await expect(body.locator('strong')).toHaveText('6~8시간 및 250~500mg');
    await expect(body.getByRole('cell', { name: '1~2 / 3~4', exact: true })).toBeVisible();
    await expect(body.locator('code').first()).toHaveText('~~코드~~');
    await expect(body.locator('pre code')).toHaveText('~~코드 블록~~\n');
    await expect(body.getByRole('link', { name: '원문 링크' })).toHaveAttribute('href', 'https://example.com/~demo?q=~~value~~');
    await expect(body).toContainText('~이스케이프~');
    expect(await body.locator('*').evaluateAll(elements => elements.some(el => getComputedStyle(el).textDecorationLine.includes('line-through')))).toBe(false);
  });
}
