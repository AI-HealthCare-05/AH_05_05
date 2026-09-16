import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

const MEDICATION_OVERVIEW = {
  recordId: 45601,
  alias: '혈압 관리 처방',
  documentImageUrl: '/api/v1/ocr/jobs/45601/image',
  start: { date: '2026-09-01', slot: 'morning' },
  endDate: '2026-09-30',
  daysRemaining: 18,
  isFinished: false,
  mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
  medications: [{
    medicationId: 45611,
    name: '혈압약',
    dose: '5mg',
    days: 30,
    daysRemaining: 18,
    slots: ['morning'],
    asNeeded: false,
  }],
};

const SUPPLEMENTS = [{
  id: 45621,
  custom_name: '아침 비타민',
  dose_amount: '1.000',
  dose_unit: '정',
  start_date: '2026-09-01',
  end_date: null,
  status: 'ACTIVE',
  score: null,
  review_body: null,
  note: null,
  created_at: '2026-09-01T08:00:00+09:00',
  updated_at: null,
  slots: [{ slot: 'MORNING', time: '08:00:00' }],
  supplement: null,
}, {
  id: 45622,
  custom_name: '저녁 오메가',
  dose_amount: '2.000',
  dose_unit: '캡슐',
  start_date: '2026-09-01',
  end_date: null,
  status: 'ACTIVE',
  score: null,
  review_body: null,
  note: null,
  created_at: '2026-09-01T19:00:00+09:00',
  updated_at: null,
  slots: [{ slot: 'EVENING', time: '19:00:00' }],
  supplement: null,
}];

interface ControlMaterial {
  backgroundColor: string;
  backgroundImage: string;
  borderRadius: string;
  boxShadow: string;
}

async function controlMaterial(control: Locator): Promise<ControlMaterial> {
  return control.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundColor: style.backgroundColor,
      backgroundImage: style.backgroundImage,
      borderRadius: style.borderRadius,
      boxShadow: style.boxShadow,
    };
  });
}

async function expectWhiteRoundedControl(control: Locator) {
  await expect(control).toHaveAttribute('data-variant', 'secondary');
  await control.page().mouse.move(0, 0);
  await expect.poll(async () => (await controlMaterial(control)).backgroundColor).toBe('rgb(255, 255, 255)');
  const material = await controlMaterial(control);
  expect(material.backgroundColor).toBe('rgb(255, 255, 255)');
  expect(material.borderRadius).not.toBe('0px');
  expect(material.backgroundImage).not.toBe('none');
  expect(material.boxShadow).not.toBe('none');
}

async function expectCircularCheckbox(checkbox: Locator) {
  const dimensions = await checkbox.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return {
      width: box.width,
      height: box.height,
      radius: Number.parseFloat(getComputedStyle(element).borderRadius),
    };
  });
  expect(dimensions.width).toBe(24);
  expect(dimensions.height).toBe(24);
  expect(dimensions.radius).toBeGreaterThanOrEqual(12);
}

async function capture(page: Page, name: string) {
  const directory = process.env.UI456_SELECTION_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: path.join(directory, name),
    fullPage: true,
    animations: 'disabled',
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function prepareMedication(page: Page) {
  await page.route('**/api/v1/medications', route => fulfillJson(route, [MEDICATION_OVERVIEW]));
}

async function prepareSupplements(
  page: Page,
  deleteResponder: (route: Route) => Promise<void> = route => route.fulfill({ status: 204, body: '' }),
) {
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
    items: [], totalCount: 0,
  }));
  await page.route('**/api/v1/users/me', route => fulfillJson(route, {
    name: '선택 테스트',
    maskedName: '선*테',
    phoneNumber: null,
    birthDate: '1990-01-01',
    gender: 'FEMALE',
  }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', route => fulfillJson(route, {
    items: SUPPLEMENTS,
    total: SUPPLEMENTS.length,
    offset: 0,
    limit: 100,
    nutrient_standard: null,
  }));
  await page.route('**/api/v1/med/user-suppl-nutr/*', async route => {
    if (route.request().method() === 'DELETE') {
      await deleteResponder(route);
      return;
    }
    await fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'unexpected request' }, 503);
  });
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-02T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-456-selection-token');
    sessionStorage.setItem('poke.account-principal', 'issue-456-selection@example.invalid');
  });
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
});

for (const width of [320, 390]) {
  test(`복약 선택 도구는 선택 수에 따라 추가·취소·삭제를 전환한다 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await prepareMedication(page);
    await page.goto('/medications');

    const title = page.getByRole('heading', { name: '복약', exact: true });
    const add = page.getByRole('button', { name: '처방 추가', exact: true });
    const selectionEntry = page.getByRole('button', { name: '선택', exact: true });
    await expect(title).toBeVisible();
    await expect(add).toBeVisible();
    await expect(add).toHaveAttribute('data-variant', 'primary');
    await expectWhiteRoundedControl(selectionEntry);

    await selectionEntry.click();
    const cancel = page.getByRole('button', { name: '취소', exact: true });
    await expect(title).toBeVisible();
    await expect(add).toHaveCount(0);
    await expectWhiteRoundedControl(cancel);
    await expect(page.getByRole('button', { name: /삭제 \d+개/ })).toHaveCount(0);

    const checkbox = page.getByRole('checkbox', { name: /처방 선택/ }).first();
    await expectCircularCheckbox(checkbox);
    await checkbox.check();
    const remove = page.getByRole('button', { name: '삭제 1개', exact: true });
    await expect(remove).toBeVisible();
    await expect(remove).toHaveAttribute('data-variant', 'danger');
    await expect(page.getByRole('button', { name: '취소', exact: true })).toBeVisible();
    await expect(page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).resolves.toBe(true);
    await capture(page, `medications-selection-${width}.png`);

    await cancel.click();
    await expect(page.getByRole('checkbox')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
  });
}

for (const width of [320, 390]) {
  test(`영양제 제목과 선택 도구는 작은 화면 한 줄을 지키고 체크 행에서 장식 손잡이를 숨긴다 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await prepareSupplements(page);
    await page.goto('/supplements');

    const listHeading = page.getByRole('heading', { name: /영양제 \d+개/, exact: true });
    const add = page.getByRole('button', { name: '영양제 추가', exact: true });
    const selectionEntry = page.getByRole('button', { name: '선택', exact: true });
    await expect(page.getByRole('heading', { name: '영양제', exact: true })).toBeVisible();
    await expect(listHeading).toBeVisible();
    await expect(listHeading).not.toContainText('먹고 있는');
    await expect(add).toBeVisible();
    await expect(add).toHaveAttribute('data-variant', 'primary');
    await expectWhiteRoundedControl(selectionEntry);
    const normalCenters = await Promise.all([listHeading, add, selectionEntry].map(async locator => {
      const box = await locator.boundingBox();
      expect(box).not.toBeNull();
      return box!.y + box!.height / 2;
    }));
    expect(Math.max(...normalCenters) - Math.min(...normalCenters)).toBeLessThanOrEqual(4);

    await selectionEntry.click();
    const cancel = page.getByRole('button', { name: '취소', exact: true });
    await expect(add).toHaveCount(0);
    await expect(page.getByText(/삭제한 영양제는 챌린지 대상에서 제외돼요/)).toHaveCount(0);
    await expectWhiteRoundedControl(cancel);
    await expect(page.getByRole('button', { name: /삭제 \d+개/ })).toHaveCount(0);

    const checkbox = page.getByRole('checkbox').first();
    await expectCircularCheckbox(checkbox);
    const selectionRow = checkbox.locator('xpath=ancestor::label');
    await expect(selectionRow.getByText('≡', { exact: true })).toHaveCount(0);
    await checkbox.check();
    await expect(page.getByRole('button', { name: '삭제 1개', exact: true })).toHaveAttribute('data-variant', 'danger');
    await expect(page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).resolves.toBe(true);
    await capture(page, `supplements-selection-${width}.png`);
  });
}

test('영양제 변경 성공은 열린 챌린지 화면의 진행률을 다시 조회하게 한다', async ({ page }) => {
  await prepareSupplements(page);
  await page.goto('/supplements');
  await page.evaluate(() => {
    (window as typeof window & { challengeRefreshes?: number }).challengeRefreshes = 0;
    window.addEventListener('rxvita:custom-challenge-progress-invalidated', () => {
      const target = window as typeof window & { challengeRefreshes?: number };
      target.challengeRefreshes = (target.challengeRefreshes ?? 0) + 1;
    });
  });

  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();

  await expect.poll(() => page.evaluate(
    () => (window as typeof window & { challengeRefreshes?: number }).challengeRefreshes ?? 0,
  )).toBe(1);
});

test('영양제 삭제 중에는 취소할 수 없고 부분 실패 대상은 선택 목록에 남는다', async ({ page }) => {
  let releaseFirstDelete!: () => void;
  let notifyFirstDelete!: () => void;
  const firstDeleteReleased = new Promise<void>(resolve => {
    releaseFirstDelete = resolve;
  });
  const firstDeleteStarted = new Promise<void>(resolve => {
    notifyFirstDelete = resolve;
  });
  let deleteAttempts = 0;
  await prepareSupplements(page, async route => {
    deleteAttempts += 1;
    if (deleteAttempts === 1) {
      notifyFirstDelete();
      await firstDeleteReleased;
      await route.fulfill({ status: 204, body: '' });
      return;
    }
    await fulfillJson(route, { code: 'STOP_FAILED', message: '잠시 후 다시 시도해주세요.' }, 500);
  });

  await page.goto('/supplements');
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox', { name: '아침 비타민 선택', exact: true }).check();
  await page.getByRole('checkbox', { name: '저녁 오메가 선택', exact: true }).check();
  await page.getByRole('button', { name: '삭제 2개', exact: true }).click();
  await firstDeleteStarted;

  const cancel = page.getByRole('button', { name: '취소', exact: true });
  await expect(cancel).toBeDisabled();
  await cancel.evaluate((button: HTMLButtonElement) => button.click());
  await expect(page.getByRole('checkbox')).toHaveCount(2);

  releaseFirstDelete();
  const confirmError = page.getByRole('button', { name: '확인', exact: true });
  await expect(confirmError).toBeVisible();
  await confirmError.click();
  await expect(page.getByRole('checkbox', { name: '아침 비타민 선택', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: '저녁 오메가 선택', exact: true })).toBeChecked();
  await expect(cancel).toBeEnabled();
});

function linkedChallenge(sourceIds: number[], status = 'ACTIVE') {
  return {
    id: 45631, templateId: 2, challengeType: 'SUPPLEMENT', challengeName: '영양제 챌린지',
    rewardBadge: null, status, joinedAt: '2026-09-01T08:00:00+09:00',
    endAt: '2026-09-07T23:59:59+09:00', actualEndDate: null,
    targetCount: 7, completedCount: 0, progressRate: 0, action: 'NONE', occurrences: [],
    targets: sourceIds.map((sourceId, index) => ({ id: index + 1, sourceId, name: `영양제 ${sourceId}`, isExcluded: false })),
  };
}

for (const removeAll of [false, true]) {
  test(`참여 중 챌린지 영양제 삭제는 확인 전 요청하지 않고 취소하면 보존한다 (전체=${removeAll})`, async ({ page }) => {
    const deleted: number[] = [];
    await prepareSupplements(page, async route => {
      deleted.push(Number(new URL(route.request().url()).pathname.split('/').at(-1)));
      await route.fulfill({ status: 204, body: '' });
    });
    await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
      items: [linkedChallenge([45621, 45622])], totalCount: 1,
    }));
    await page.goto('/supplements');
    await page.getByRole('button', { name: '선택', exact: true }).click();
    await page.getByRole('checkbox').first().check();
    if (removeAll) await page.getByRole('checkbox').nth(1).check();
    const count = removeAll ? 2 : 1;
    await page.getByRole('button', { name: `삭제 ${count}개`, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '영양제를 삭제할까요?' });
    await expect(dialog).toBeVisible();
    if (removeAll) {
      await expect(dialog).toContainText('삭제하면 참여 중인 챌린지가 종료돼요.');
      await expect(dialog.getByText('이 영양제로 참여 중인 챌린지가 있어요.')).toHaveCount(0);
      await expect(dialog.getByText('삭제하면 해당 챌린지의 대상에서 제외돼요.')).toHaveCount(0);
    } else {
      await expect(dialog).toContainText('이 영양제로 참여 중인 챌린지가 있어요.');
      await expect(dialog).toContainText('삭제하면 해당 챌린지의 대상에서 제외돼요.');
      await expect(dialog.getByText('삭제하면 참여 중인 챌린지가 종료돼요.')).toHaveCount(0);
    }
    await capture(page, `supplement-delete-warning-${removeAll ? 'last' : 'partial'}.png`);
    expect(deleted).toEqual([]);
    await dialog.getByRole('button', { name: '취소', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('checkbox').first()).toBeChecked();
    expect(deleted).toEqual([]);
    await page.getByRole('button', { name: `삭제 ${count}개`, exact: true }).click();
    await dialog.getByRole('button', { name: `삭제 ${count}개`, exact: true }).click();
    if (removeAll) {
      await expect(page.getByRole('heading', { name: '영양제를 등록하고 관리하기' })).toBeVisible();
    } else {
      await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
    }
    expect(deleted).toEqual(removeAll ? [45621, 45622] : [45621]);
  });
}

test('종료되거나 제외된 챌린지 대상은 삭제 경고를 띄우지 않는다', async ({ page }) => {
  await prepareSupplements(page);
  const excluded = linkedChallenge([45621]);
  excluded.targets[0].isExcluded = true;
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
    items: [linkedChallenge([45621], 'COMPLETED'), excluded], totalCount: 2,
  }));
  await page.goto('/supplements');
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('아침 비타민', { exact: true })).toHaveCount(0);
});

test('챌린지 연결 조회가 실패하면 삭제하지 않고 재시도할 수 있다', async ({ page }) => {
  let deleteCount = 0;
  await prepareSupplements(page, async route => {
    deleteCount += 1;
    await route.fulfill({ status: 204, body: '' });
  });
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
    message: '챌린지를 확인하지 못했어요.',
  }, 503));
  await page.goto('/supplements');
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  expect(deleteCount).toBe(0);
  await dialog.getByRole('button', { name: '확인', exact: true }).click();
  await expect(page.getByRole('checkbox').first()).toBeChecked();
  await expect(page.getByRole('button', { name: '삭제 1개', exact: true })).toBeEnabled();
});

test('편집 화면에는 중단 버튼이 없고 목록 삭제의 챌린지 경고 취소 시 영양제를 유지한다', async ({ page }) => {
  let deleteCount = 0;
  await prepareSupplements(page, async route => {
    deleteCount += 1;
    await route.fulfill({ status: 204, body: '' });
  });
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
    items: [linkedChallenge([45621])], totalCount: 1,
  }));
  await page.goto('/supplements');
  await page.getByRole('button', { name: /^아침 비타민/ }).click();
  await expect(page.getByRole('button', { name: '복용 중단하기', exact: true })).toHaveCount(0);
  await page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }).click();
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  const warning = page.getByRole('dialog', { name: '영양제를 삭제할까요?' });
  await expect(warning).toBeVisible();
  await expect(warning).toContainText('삭제하면 참여 중인 챌린지가 종료돼요.');
  await expect(page.locator('[role="dialog"][data-variant="dialog"]')).toHaveCount(1);
  await warning.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByRole('button', { name: '삭제 1개', exact: true })).toBeEnabled();
  expect(deleteCount).toBe(0);
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  await warning.getByRole('button', { name: '삭제 1개', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^아침 비타민/ })).toHaveCount(0);
  expect(deleteCount).toBe(1);
});

test('여러 챌린지의 종료와 일부 제외가 함께 발생하면 둘 다 안내한다', async ({ page }) => {
  await prepareSupplements(page);
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, {
    items: [linkedChallenge([45621]), { ...linkedChallenge([45621, 45622]), id: 45632 }], totalCount: 2,
  }));
  await page.goto('/supplements');
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  const warning = page.getByRole('dialog', { name: '영양제를 삭제할까요?' });
  await expect(warning).toContainText('일부 챌린지는 종료되고, 나머지 챌린지에서는 선택한 영양제가 제외돼요.');
  await warning.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByRole('checkbox').first()).toBeChecked();
});
