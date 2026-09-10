import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.skip(IS_REAL_API, MOCK_ONLY_REASON);

test.beforeEach(async ({ page }) => {
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
  await page.route('**/api/v1/**', route => route.abort());
  // Official challenges use the real API even in mock mode; isolate this chat test boundary.
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
});

const answer = '## 복용 안내\n\n**확인할 내용**\n\n- 첫 번째 안내\n- 두 번째 안내\n\n[공식 안내](https://example.com/guide) [위험 링크](javascript:alert(1))\n\n<script>alert(1)</script>\n\n| 제품 | 설명 |\n| --- | --- |\n| 제품명 | 아주긴내용'.concat('가'.repeat(80), ' |\n\n```text\n', 'long-code-'.repeat(40), '\n```');

test('저장된 AI 답변은 안전한 Markdown과 스크롤 가능한 표·코드로 표시한다', async ({ page }, testInfo) => {
  await page.addInitScript(({ answer }) => {
    sessionStorage.setItem('poke.access-token', 'e2e-token');
    sessionStorage.setItem('poke.account-principal', 'patient@example.com');
    localStorage.setItem('poke.mock-chat-sessions:patient%40example.com', JSON.stringify({
      nextSessionId: 78, nextMessageId: 1205,
      sessions: [{ sessionId: 77, createdAt: '2026-09-10T00:00:00Z', lastMessageAt: '2026-09-10T00:00:00Z', messages: [
        { role: 'user', text: '**사용자 질문**', sources: [] },
        { role: 'assistant', text: answer, sources: [{ scope: 'official', title: '공공 근거', organization: '식품의약품안전처' }] },
      ] }],
    }));
  }, { answer });
  await page.goto('/chat');
  await page.getByRole('button', { name: /사용자 질문/ }).click();
  const body = page.getByLabel('답변 본문');
  await expect(body.getByRole('heading', { name: '복용 안내' })).toBeVisible();
  await expect(body.locator('strong')).toHaveText('확인할 내용');
  await expect(body.getByRole('listitem')).toHaveCount(2);
  await expect(body.getByRole('link', { name: '공식 안내' })).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(body.getByRole('link', { name: '위험 링크' })).toHaveCount(0);
  await expect(body.locator('script, img')).toHaveCount(0);
  await expect(page.getByText('**사용자 질문**', { exact: true })).toBeVisible();
  await expect(page.getByText('이 답변은 AI가 생성한 답변입니다', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '챗봇', exact: true })).toHaveCount(0);
  for (const width of [320, 375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const selector of ['table', 'pre']) {
      const scroll = await body.locator(selector).evaluate(el => {
        const region = el.tagName === 'TABLE' ? el.parentElement! : el;
        return { overflows: region.scrollWidth > region.clientWidth, overflowX: getComputedStyle(region).overflowX };
      });
      expect(scroll.overflowX).toBe('auto');
      // On wide #369 layouts a table may fit without needing horizontal scrolling.
      if (width < 768 || selector === 'pre') expect(scroll.overflows).toBe(true);
    }
    await page.screenshot({ path: testInfo.outputPath(`chat-markdown-${width}.png`), fullPage: true });
  }
});

test('AI 생성 안내는 첫 답변이 완료된 뒤 대화 영역 끝의 입력창 위에 나타난다', async ({ page }) => {
  await page.goto('/dev/chat');
  const notice = page.getByText('이 답변은 AI가 생성한 답변입니다', { exact: true });
  await expect(page.getByRole('textbox', { name: '질문 입력' })).toBeEnabled();
  await expect(notice).toHaveCount(0);
  await page.getByRole('textbox', { name: '질문 입력' }).fill('일반 안내');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByRole('textbox', { name: '질문 입력' })).toBeDisabled();
  await expect(notice).toHaveCount(0);
  await expect(notice).toBeVisible();
  const inputBox = await page.getByRole('textbox', { name: '질문 입력' }).boundingBox();
  await expect(page.getByRole('main').getByText('이 답변은 AI가 생성한 답변입니다', { exact: true })).toBeVisible();
  const noticeBox = (await notice.boundingBox())!;
  expect(noticeBox.y + noticeBox.height).toBeLessThan(inputBox!.y);
});

test('하단 챌린지 탭과 전역 챗봇 진입은 로그인 경계를 지킨다', async ({ page }, testInfo) => {
  await page.goto('/home');
  const navigation = page.getByRole('navigation', { name: '주요 화면' });
  await expect(navigation.getByRole('button', { name: '챗봇' })).toHaveCount(0);
  await expect(navigation.getByRole('button', { name: '챌린지' })).toBeVisible();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    const launcherBox = (await page.getByRole('button', { name: '챗봇', exact: true }).boundingBox())!;
    const navigationBox = (await navigation.boundingBox())!;
    expect(launcherBox.y + launcherBox.height).toBeLessThan(navigationBox.y);
    await page.screenshot({ path: testInfo.outputPath(`floating-home-${width}.png`), fullPage: true });
  }
  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('button', { name: '챗봇', exact: true })).toBeHidden();
  await page.getByRole('button', { name: '로그인 · 회원가입' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('이메일').fill('patient@example.com');
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await expect(page).toHaveURL(/\/home$/);
  await page.goto('/home');
  await navigation.getByRole('button', { name: '챌린지' }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  await expect(navigation.getByRole('button', { name: '챌린지' })).toHaveAttribute('aria-current', 'page');
  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
});

test('탭 없는 화면도 챗봇을 제공하고 하단 작업·입력·다이얼로그를 가리지 않는다', async ({ page }, testInfo) => {
  for (const route of ['/dev/document-upload', '/dev/medication-schedule', '/terms', '/dev/my-profile']) {
    await page.goto(route);
    const launcher = page.getByRole('button', { name: '챗봇', exact: true });
    await expect(launcher).toBeVisible();
    const main = page.getByRole('main');
    await main.evaluate(el => { el.scrollTop = el.scrollHeight; window.scrollTo(0, document.body.scrollHeight); });
    const launcherBox = (await launcher.boundingBox())!;
    for (const button of await main.getByRole('button').all()) {
      const box = await button.boundingBox();
      if (box && box.y >= 0 && box.y + box.height <= 812) {
        expect(box.x + box.width <= launcherBox.x || box.x >= launcherBox.x + launcherBox.width || box.y + box.height <= launcherBox.y || box.y >= launcherBox.y + launcherBox.height).toBe(true);
      }
    }
    if (route === '/dev/my-profile') {
      await main.getByRole('textbox').first().focus();
      await expect(launcher).toBeHidden();
    }
    if (route === '/dev/document-upload') await page.screenshot({ path: testInfo.outputPath('floating-upload-mobile.png'), fullPage: true });
  }
});
