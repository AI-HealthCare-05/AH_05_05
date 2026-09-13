import { expect, test, type Locator } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);

const sessions = Array.from({ length: 20 }, (_, index) => ({
  sessionId: 43100 + index,
  title: `세로 확인 ${index + 1}번째 상담 ${'긴제목'.repeat(80)}`,
  lastMessagePreview: `미리보기 ${index + 1}번째 내용 ${'긴내용'.repeat(80)}`,
  lastMessageAt: '2026-09-12T09:00:00+09:00',
}));

async function measureLines(rows: Locator) {
  return rows.evaluateAll(elements => elements.map(element => {
    const row = element.getBoundingClientRect();
    const lines = [...element.querySelectorAll('span.truncate')].map(node => {
      const rect = node.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(node);
      const glyph = range.getBoundingClientRect();
      const style = getComputedStyle(node);
      return { height: rect.height, lineHeight: parseFloat(style.lineHeight), top: rect.top,
        bottom: rect.bottom, glyphTop: glyph.top, glyphBottom: glyph.bottom,
        width: rect.width, scrollWidth: node.scrollWidth, overflowX: style.overflowX };
    });
    return { rowHeight: row.height, lines };
  }));
}

for (const viewport of [{ width: 1280, height: 600 }, { width: 1440, height: 600 }, { width: 1440, height: 900 }]) {
  test(`최근 대화 20개는 세로 글자를 자르지 않고 끝까지 스크롤된다 ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', 'issue431-height');
      sessionStorage.setItem('poke.account-principal', 'issue431-height@example.com');
    });
    await page.route('**/api/v1/**', route => route.fulfill({ json: {} }));
    await page.route('**/api/v1/chat/sessions', route => route.fulfill({ json: { items: sessions } }));
    await page.goto('/chat');
    const main = page.getByRole('main');
    for (const mode of ['browse', 'selection']) {
      if (mode === 'selection') await page.getByRole('button', { name: '대화 삭제', exact: true }).click();
      const rows = mode === 'browse' ? main.getByRole('button', { name: /^세로 확인/ }) : main.locator('label').filter({ has: page.getByRole('checkbox') });
      await expect(rows).toHaveCount(20);
      const measurement = await measureLines(rows);
      await testInfo.attach(`line-boxes-${mode}.json`, { body: Buffer.from(JSON.stringify(measurement, null, 2)), contentType: 'application/json' });
      await page.screenshot({ path: testInfo.outputPath(`recent-list-${mode}-top.png`) });
      for (const item of measurement) {
        expect(item.lines).toHaveLength(2);
        expect(item.rowHeight).toBeGreaterThanOrEqual(80);
        for (const line of item.lines) {
          expect(line.height).toBeGreaterThanOrEqual(line.lineHeight - 1);
          expect(line.glyphTop).toBeGreaterThanOrEqual(line.top - 1);
          expect(line.glyphBottom).toBeLessThanOrEqual(line.bottom + 1);
          expect(line.scrollWidth).toBeGreaterThan(line.width);
          expect(line.overflowX).toBe('hidden');
        }
      }
      expect(await main.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
      await rows.last().scrollIntoViewIfNeeded();
      const scroll = await main.evaluate(element => ({ top: element.scrollTop, bottom: element.getBoundingClientRect().bottom }));
      expect(scroll.top).toBeGreaterThan(0);
      const last = await rows.last().boundingBox();
      expect(last).not.toBeNull();
      expect(last!.y + last!.height).toBeLessThanOrEqual(scroll.bottom + 1);
      await expect(page.getByRole('navigation', { name: '주요 화면' })).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`recent-list-${mode}-bottom.png`) });
    }
  });
}
