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

async function openRecordedPrescriptions(page: Page) {
  await page.getByRole('tab', { name: '작성한 메모' }).click();
  await expect(page.getByRole('button', { name: /감기 처방.*펼치기/ })).toBeVisible();
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
      careEpisodeAlias: index === 0 ? '감기 처방' : '지난 처방',
      careEpisodeStartDate: index === 0 ? '2026-09-24' : '2026-08-01',
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

test('My에서 처방 아코디언을 열면 다음 진료용 여러 줄 메모를 온전히 보여준다', async ({ page }, testInfo) => {
  await page.goto('/my');
  await page.getByRole('button', { name: '복약 메모 모아보기' }).click();
  await expect(page).toHaveURL('/medications/notes');
  await openRecordedPrescriptions(page);
  await page.getByRole('button', { name: /감기 처방.*펼치기/ }).click();
  const note = page.getByText(body, { exact: true });
  await expect(note).toBeVisible();
  await expect(note).toHaveCSS('white-space', 'pre-wrap');
  await expect(note).not.toHaveClass(/truncate/);
  await page.screenshot({ path: testInfo.outputPath('note-collection.png') });
});

test('처방별 아코디언은 해당 메모 수와 커서 페이지네이션을 독립적으로 유지한다', async ({ page }) => {
  await page.goto('/medications/notes');
  await openRecordedPrescriptions(page);
  await page.getByRole('button', { name: /감기 처방.*펼치기/ }).click();
  await expect(page.getByRole('heading', { name: '건강상태 기록 1개' })).toBeVisible();
  await expect(page.getByText('과거 메모 1', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: /지난 처방.*펼치기/ }).click();
  await expect(page.getByRole('heading', { name: '건강상태 기록 22개' })).toBeVisible();
  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await expect(page.getByText('과거 메모 22', { exact: true })).toBeVisible();
  await expect(page.getByText(body, { exact: true })).toHaveCount(0);
});

test('늦게 도착한 다른 처방 응답은 현재 펼친 처방에 섞이지 않는다', async ({ page }) => {
  await page.goto('/medications/notes');
  await openRecordedPrescriptions(page);
  await delayFirstMockResponse(page);

  await page.getByRole('button', { name: /지난 처방.*펼치기/ }).click();
  await page.getByRole('button', { name: /감기 처방.*펼치기/ }).click();
  await expect(page.getByText(body, { exact: true })).toBeVisible();
  await page.waitForTimeout(950);
  await expect(page.getByText('과거 메모 1', { exact: true })).toHaveCount(0);
});

test('존재하지 않는 처방 딥링크는 전체 메모를 오분류하지 않고 안내한다', async ({ page }) => {
  await page.goto('/medications/notes?episodeId=999');
  await expect(page.getByRole('alert')).toContainText('선택한 처방을 찾지 못했어요.');
  await expect(page.getByText(body, { exact: true })).toHaveCount(0);
});
