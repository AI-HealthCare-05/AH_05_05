import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
test.use({ viewport: { width: 393, height: 852 }, hasTouch: true });

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-16T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-532-token');
    sessionStorage.setItem('poke.account-principal', 'issue-532@example.invalid');
  });
});

async function expectNoHorizontalPageOverflow(page: Page) {
  expect(await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }))).toEqual({ viewport: 393, document: 393, body: 393 });
}

test('직접 입력 복약에 복용 시간이 없으면 홈에서 일정 설정으로 안내한다', async ({ page }) => {
  await page.goto('/dev/home-unscheduled');

  await expect(page.getByText('복용 시간을 설정해주세요', { exact: true })).toBeVisible();
  await expect(page.getByText('오늘 복약할 약이 없어요.', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '복용 시간 설정하기', exact: true }).click();
  await expect(page).toHaveURL(/\/medication-schedule\?recordId=12$/);
});

test('챗봇 최근 대화는 제목 오른쪽에 새 상담과 선택을 함께 둔다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.evaluate(() => {
    localStorage.setItem('poke.mock-chat-sessions:issue-532%40example.invalid', JSON.stringify({
      nextSessionId: 534,
      nextMessageId: 534,
      sessions: [{
        sessionId: 532,
        createdAt: '2026-09-16T09:00:00.000Z',
        lastMessageAt: '2026-09-16T09:01:00.000Z',
        messages: [
          { role: 'user', text: '최근 상담 질문', sources: [] },
          { role: 'assistant', text: '최근 상담 답변', sources: [] },
        ],
      }],
    }));
  });
  await page.reload();

  const toolbar = page.getByRole('group', { name: '최근 대화 작업' });
  await expect(toolbar.getByRole('heading', { name: '최근 대화', exact: true })).toBeVisible();
  await expect(toolbar.getByRole('button', { name: '새 상담', exact: true })).toBeVisible();
  await toolbar.getByRole('button', { name: '선택', exact: true }).click();
  await expect(toolbar.getByRole('button', { name: '취소', exact: true })).toBeVisible();
});

test('모바일 복약 메모의 복용 일시는 화면 폭을 넘기지 않는다', async ({ page }) => {
  await page.goto('/medications/notes/new', { waitUntil: 'domcontentloaded' });
  const prescription = page.getByLabel('처방');
  await expect(prescription).toBeEnabled();
  await prescription.selectOption({ index: 1 });
  const dateTime = page.getByLabel('복용 일시');
  await expect(dateTime).toBeVisible();
  expect(await dateTime.evaluate(element => {
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.right <= window.innerWidth && element.scrollWidth <= element.clientWidth;
  })).toBe(true);
  await expectNoHorizontalPageOverflow(page);
});

test('성분 합계는 상한 없는 막대를 흐리지 않고 제목 바로 아래에 개인 기준을 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements-no-upper-limit');

  const section = page.getByRole('heading', { name: '성분 합계', exact: true }).locator('..');
  await expect(section.getByText(/합계 기준: 2025 한국인 영양소 섭취기준/)).toBeVisible();
  await expect(section.getByText('만 26세', { exact: true })).toHaveCSS('font-weight', '700');
  await expect(section.getByText('남성', { exact: true })).toHaveCSS('font-weight', '700');

  const trackWithoutUpperLimit = page.locator('[data-nutrient-range][aria-hidden="true"] [data-range-track]').first();
  await expect(trackWithoutUpperLimit).toBeVisible();
  expect(await trackWithoutUpperLimit.evaluate(element => ({
    mask: getComputedStyle(element).maskImage,
    webkitMask: getComputedStyle(element).webkitMaskImage,
  }))).toEqual({ mask: 'none', webkitMask: 'none' });
});

test('마이페이지 관리 API가 늦어도 각 메뉴에 로딩 문구를 반복하지 않는다', async ({ page }) => {
  await page.goto('/dev/my-management-loading');

  await expect(page.getByRole('status', { name: '내 관리 불러오는 중' })).toHaveCount(1);
  await expect(page.getByText('확인 중', { exact: true })).toHaveCount(0);
  const management = page.getByRole('region', { name: '내 관리' });
  await expect(management.getByRole('button', { name: /복용 중 처방/ })).toBeEnabled();
  await expect(management.getByRole('button', { name: /영양제/ })).toBeEnabled();
  await expect(management.getByRole('button', { name: /진료일정/ })).toBeEnabled();
});

test('노션에서 지정한 주요 공통 버튼은 동일한 명암 규격을 사용한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  const report = page.getByRole('button', { name: 'AI 보고서 받기', exact: true });
  const add = page.getByRole('button', { name: /영양제 추가/ });

  for (const button of [report, add]) {
    await expect(button).toHaveClass(/rx-button/);
    expect(await button.evaluate(element => getComputedStyle(element).boxShadow)).not.toBe('none');
  }
  await expectNoHorizontalPageOverflow(page);
});
