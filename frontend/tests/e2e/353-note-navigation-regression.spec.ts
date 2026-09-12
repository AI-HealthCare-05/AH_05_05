import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const note = {
  id: 901, careEpisodeId: 41, careEpisodeAlias: '아침 처방',
  careEpisodeStartDate: '2026-08-01', careEpisodeStatus: 'ACTIVE',
  availableMedications: [], medicationId: null, medication: null,
  dosedAt: '2026-08-02T08:00:00', body: '속이 편했어요',
  createdAt: '2026-08-02T08:10:00', updatedAt: null,
};

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'note-navigation-test');
    sessionStorage.setItem('poke.account-principal', 'note-navigation@example.com');
  });
  // Exercise the production router/components, isolating every external API.
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path === '/api/v1/med/notes/episodes') {
      body = [{
        careEpisodeId: 41, alias: '아침 처방', startDate: '2026-08-01', status: 'ACTIVE',
        noteCount: 1, medicationCount: 0, representativeMedicationName: null, medications: [],
      }];
    } else if (path === '/api/v1/med/notes') {
      body = { items: [note], total: 1, nextCursor: null };
    } else if (path === '/api/v1/med/notes/901') {
      body = note;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
});

async function enterNotesFromMedicationTab(page: Page) {
  await page.goto('/dev/home-empty');
  await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '복약', exact: true }).click();
  await expect(page).toHaveURL('/medications');
  await page.getByRole('button', { name: '복약 메모', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes');
}

async function openEpisode(page: Page) {
  await page.getByRole('tab', { name: '메모 있는 처방' }).click();
  await page.getByRole('button', { name: /아침 처방 .*펼치기/ }).click();
  await expect(page.getByText('속이 편했어요')).toBeVisible();
}

for (const exit of ['header', 'tab', 'browser'] as const) {
  test(`복약 탭에서 메모 목록을 ${exit}로 나간 뒤 다시 뒤로가도 메모로 순환하지 않는다`, async ({ page }) => {
    await enterNotesFromMedicationTab(page);
    if (exit === 'header') await page.getByRole('button', { name: '뒤로 가기' }).click();
    else if (exit === 'tab') await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '복약', exact: true }).click();
    else await page.goBack();
    await expect(page).toHaveURL('/medications');
    await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL('/dev/home-empty');
  });
}

for (const action of ['new-back', 'edit-back', 'edit-save'] as const) {
  test(`처방을 펼친 후 ${action}는 해당 아코디언을 복원하고 연속 뒤로가기로 복약과 홈에 도착한다`, async ({ page }) => {
    await enterNotesFromMedicationTab(page);
    await openEpisode(page);
    if (action === 'new-back') await page.getByRole('button', { name: '이 처방에 새 메모' }).click();
    else await page.getByRole('button', { name: '처방 전체 속이 편했어요' }).click();
    if (action === 'edit-save') {
      await page.getByLabel('건강상태 기록').fill('수정한 메모');
      await page.getByRole('button', { name: '수정 저장' }).click();
    } else await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL('/medications/notes?episodeId=41');
    await expect(page.getByRole('button', { name: /아침 처방 .*접기/ })).toHaveAttribute('aria-expanded', 'true');
    await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL('/medications');
    await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL('/dev/home-empty');
  });
}

test('직접 연 메모 작성의 뒤로가기는 메모 작성 이력을 다시 남기지 않는다', async ({ page }) => {
  await page.goto('/dev/home-empty');
  await page.goto('/medications/notes/new');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications/notes');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications');
  await page.goBack();
  await expect(page).toHaveURL('/dev/home-empty');
});

test('직접 연 필터 목록에서 수정 후 뒤로가기는 필터를 보존한다', async ({ page }) => {
  await page.goto('/medications/notes?episodeId=41');
  await page.getByRole('button', { name: '처방 전체 속이 편했어요' }).click();
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=41');
});

test('직접 연 목록을 나간 복약 화면의 뒤로가기는 홈으로 복귀한다', async ({ page }) => {
  await page.goto('/medications/notes');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/home');
});

for (const entry of ['medication', 'direct'] as const) {
  test(`${entry} 목록에서 연 수정 화면의 복약 탭으로 나가도 뒤로가기가 순환하지 않는다`, async ({ page }) => {
    if (entry === 'medication') await enterNotesFromMedicationTab(page);
    else await page.goto('/medications/notes');
    await openEpisode(page);
    await page.getByRole('button', { name: '처방 전체 속이 편했어요' }).click();
    await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '복약', exact: true }).click();
    await expect(page).toHaveURL('/medications');
    await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL(entry === 'medication' ? '/dev/home-empty' : '/home');
  });
}

for (const exit of ['header', 'tab', 'browser'] as const) {
  test(`저장 응답 전에 ${exit}로 나간 메모는 늦은 성공 응답으로 다시 이동하지 않는다`, async ({ page }) => {
    let releaseSave!: () => void;
    const saveCanFinish = new Promise<void>((resolve) => { releaseSave = resolve; });
    await page.route('**/api/v1/med/notes/901', async (route) => {
      if (route.request().method() !== 'PATCH') return route.fallback();
      await saveCanFinish;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(note) });
    });
    await enterNotesFromMedicationTab(page);
    await openEpisode(page);
    await page.getByRole('button', { name: '처방 전체 속이 편했어요' }).click();
    await page.getByLabel('건강상태 기록').fill('저장 응답을 기다리는 메모');
    const saveRequested = page.waitForRequest((request) =>
      request.url().endsWith('/api/v1/med/notes/901') && request.method() === 'PATCH');
    await page.getByRole('button', { name: '수정 저장' }).click();
    await saveRequested;
    if (exit === 'header') await page.getByRole('button', { name: '뒤로 가기' }).click();
    else if (exit === 'tab') await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '복약', exact: true }).click();
    else await page.goBack();
    const destination = exit === 'tab' ? '/medications' : '/medications/notes?episodeId=41';
    await expect(page).toHaveURL(destination);
    const saveResponded = page.waitForResponse((response) =>
      response.url().endsWith('/api/v1/med/notes/901') && response.request().method() === 'PATCH');
    releaseSave();
    await (await saveResponded).finished();
    // Let the completed request's async continuation and any resulting route load settle.
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(destination);
    if (exit !== 'tab') await expect(page.getByRole('button', { name: /아침 처방 .*접기/ })).toHaveAttribute('aria-expanded', 'true');
  });
}
