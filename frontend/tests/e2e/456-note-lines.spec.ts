import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const longMedicationName = '아주긴이름의복합성분감기약서방정500밀리그램';
const datedWithoutNotes = {
  careEpisodeId: 4561,
  alias: '메모 작성 처방',
  startDate: '2026-09-08',
  status: 'ACTIVE',
  representativeMedicationName: longMedicationName,
  medicationCount: 2,
  noteCount: 0,
};
const undatedWithoutNotes = {
  careEpisodeId: 4562,
  alias: '날짜 없는 처방',
  startDate: null,
  status: 'COMPLETED',
  representativeMedicationName: '날짜없는처방약',
  medicationCount: 1,
  noteCount: 0,
};
const datedWithNotes = {
  careEpisodeId: 4563,
  alias: '작성한 메모 처방',
  startDate: '2026-09-09',
  status: 'ACTIVE',
  representativeMedicationName: '작성한메모처방약',
  medicationCount: 1,
  noteCount: 1,
};
const note = {
  id: 45601,
  careEpisodeId: 4563,
  careEpisodeAlias: datedWithNotes.alias,
  careEpisodeStartDate: datedWithNotes.startDate,
  careEpisodeStatus: datedWithNotes.status,
  availableMedications: [],
  medicationId: null,
  medication: null,
  dosedAt: '2026-09-10T08:00:00',
  body: '레이아웃 이후에도 열리는 메모',
  createdAt: '2026-09-10T08:10:00',
  updatedAt: null,
};

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function expectVerticalOrder(header: Locator, dateText: string, medicationText: string) {
  const boxes = await header.evaluate((element, labels) => {
    function textBox(label: string) {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const start = node.textContent?.indexOf(label) ?? -1;
        if (start >= 0) {
          const range = document.createRange();
          range.setStart(node, start);
          range.setEnd(node, start + label.length);
          const box = range.getBoundingClientRect();
          return { y: box.y, height: box.height };
        }
        node = walker.nextNode();
      }
      return null;
    }
    return { date: textBox(labels.date), medication: textBox(labels.medication) };
  }, { date: dateText, medication: medicationText });
  expect(boxes.date).not.toBeNull();
  expect(boxes.medication).not.toBeNull();
  expect(boxes.medication!.y).toBeGreaterThanOrEqual(boxes.date!.y + boxes.date!.height);
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'note-lines-456-token');
    sessionStorage.setItem('poke.account-principal', 'note-lines-456@example.com');
  });
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/med/notes/episodes') {
      return fulfillJson(route, [datedWithoutNotes, undatedWithoutNotes, datedWithNotes]);
    }
    if (path === '/api/v1/med/notes') {
      return fulfillJson(route, { items: [note], total: 1, nextCursor: null });
    }
    if (path === `/api/v1/med/notes/${note.id}`) return fulfillJson(route, note);
    return fulfillJson(route, []);
  });
});

for (const width of [320, 390]) {
  test(`처방 날짜와 약 요약을 두 줄로 표시하고 기존 동작을 유지한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/medications/notes');

    const withoutNotesHeader = page.getByRole('button', { name: /메모 작성 처방.*펼치기/ });
    await expect(withoutNotesHeader).toBeVisible();
    await expectVerticalOrder(withoutNotesHeader, '2026년 9월 8일', `${longMedicationName} 외 1개`);
    expect(await withoutNotesHeader.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);

    const undatedHeader = page.getByRole('button', { name: /날짜 없는 처방.*펼치기/ });
    await expect(undatedHeader).toContainText('날짜없는처방약');
    await expect(undatedHeader).not.toContainText('·');
    await withoutNotesHeader.click();
    await expect(page.getByRole('button', { name: /메모 작성 처방.*접기/ })).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('button', { name: '이 처방에 메모 작성' })).toBeVisible();

    await page.getByRole('tab', { name: '작성한 메모' }).click();
    const withNotesHeader = page.getByRole('button', { name: /작성한 메모 처방.*펼치기/ });
    await expectVerticalOrder(withNotesHeader, '2026년 9월 9일', '작성한메모처방약');
    await withNotesHeader.click();
    await expect(page.getByRole('button', { name: /작성한 메모 처방.*접기/ })).toHaveAttribute('aria-expanded', 'true');
    await page.getByRole('button', { name: '레이아웃 이후에도 열리는 메모', exact: true }).click();
    await expect(page).toHaveURL(`/medications/notes/${note.id}`);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    if (width === 390) {
      await page.goBack();
      await page.screenshot({ path: testInfo.outputPath('note-lines-390.png'), fullPage: true });
    }
  });
}
