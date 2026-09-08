import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);
const body = '아침에 약을 먹은 뒤 느낀 점을 기록해요. 다음 진료에서 이 내용을 꼭 물어보고 싶어요.\n두 번째 줄도 생략하지 않고 확인하고 싶어요.';

async function delayFirstMockResponse(page: Page) {
  await page.evaluate(() => {
    const nativeSetTimeout = window.setTimeout.bind(window);
    let medicationNoteDelayCount = 0;
    window.setTimeout = ((handler: TimerHandler, timeout?: number) => {
      if (timeout === 400) {
        medicationNoteDelayCount += 1;
        return nativeSetTimeout(handler, medicationNoteDelayCount === 1 ? 900 : 10);
      }
      return nativeSetTimeout(handler, timeout);
    }) as typeof window.setTimeout;
  });
}

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.addInitScript(({ noteBody }) => {
    const principal = 'note-collection@example.com';
    sessionStorage.setItem('poke.access-token', 'e2e-note-collection');
    sessionStorage.setItem('poke.account-principal', principal);
    const notes = Array.from({ length: 23 }, (_, index) => ({
      id: index + 1,
      careEpisodeId: index === 0 ? 901 : 902,
      careEpisodeTitle: index === 0 ? '감기 처방' : '지난 처방',
      careEpisodeAlias: index === 0 ? '감기 처방' : '지난 처방',
      careEpisodeStartDate: '2026-08-01',
      careEpisodeStatus: index === 0 ? 'ACTIVE' : 'COMPLETED',
      availableMedications: [],
      medicationId: null,
      medication: null,
      dosedAt: `2026-09-${String(24 - index).padStart(2, '0')}T08:00:00+09:00`,
      body: index === 0 ? noteBody : `과거 메모 ${index}`,
      createdAt: '2026-09-08T10:00:00+09:00',
      updatedAt: null,
    }));
    sessionStorage.setItem(`rxvita.mock.medication-notes:${encodeURIComponent(principal)}`, JSON.stringify(notes));
  }, { noteBody: body });
});

test('My entry shows complete multiline notes for the next visit', async ({ page }, testInfo) => {
  await page.goto('/my');
  await page.getByRole('button', { name: '복약 메모 모아보기' }).click();
  await expect(page).toHaveURL('/medications/notes');
  const note = page.getByText(body, { exact: true });
  await expect(note).toBeVisible();
  await expect(note).toHaveCSS('white-space', 'pre-wrap');
  await expect(note).not.toHaveClass(/truncate/);
  await page.screenshot({ path: testInfo.outputPath('note-collection.png') });
});

test('prescription filter uses only its notes and resets pagination', async ({ page }) => {
  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모 23개', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '감기 처방 메모만 보기', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=901');
  await expect(page.getByRole('heading', { name: '복약 메모 1개', exact: true })).toBeVisible();
  await expect(page.getByText('감기 처방 메모만 보고 있어요.', { exact: true })).toBeVisible();
  await expect(page.getByText('과거 메모 1', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '더 보기', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '전체 메모 보기' }).click();
  await expect(page.getByRole('heading', { name: '복약 메모 23개', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await expect(page.getByText('과거 메모 22', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '지난 처방 메모만 보기', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: '복약 메모 22개', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await expect(page.getByText('과거 메모 22', { exact: true })).toBeVisible();
  await expect(page.getByText(body, { exact: true })).toHaveCount(0);
});

test('a late load-more response cannot append notes from the previous filter', async ({ page }) => {
  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모 23개', exact: true })).toBeVisible();
  await delayFirstMockResponse(page);

  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await page.getByRole('button', { name: '감기 처방 메모만 보기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '복약 메모 1개', exact: true })).toBeVisible();

  await page.waitForTimeout(950);
  await expect(page.getByRole('heading', { name: '복약 메모 1개', exact: true })).toBeVisible();
  await expect(page.getByText('과거 메모 1', { exact: true })).toHaveCount(0);
});

test('an old response stays invalid after returning to the same filter scope', async ({ page }) => {
  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모 23개', exact: true })).toBeVisible();
  await delayFirstMockResponse(page);

  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await page.getByRole('button', { name: '감기 처방 메모만 보기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '복약 메모 1개', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '전체 메모 보기' }).click();
  await expect(page.getByRole('heading', { name: '복약 메모 23개', exact: true })).toBeVisible();
  await expect(page.getByText('과거 메모 22', { exact: true })).toHaveCount(0);

  await page.waitForTimeout(950);
  await expect(page.getByText('과거 메모 22', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '더 보기', exact: true })).toBeVisible();
});

test('an empty filtered collection still identifies the selected prescription', async ({ page }) => {
  await page.goto('/medications/notes?episodeId=999');
  await expect(page.getByRole('heading', { name: '복약 메모 0개', exact: true })).toBeVisible();
  await expect(page.getByText('선택한 처방 메모만 보고 있어요.', { exact: true })).toBeVisible();
  await expect(page.getByText('복용 후 느낀 점을 남겨두면 다음 진료 때 도움이 돼요.')).toBeVisible();
});
