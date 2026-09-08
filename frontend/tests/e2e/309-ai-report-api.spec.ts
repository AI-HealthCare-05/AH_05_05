import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
// WSL's mounted worktree can spend >45s on Vite's first module transform.
// Assertion timeouts remain unchanged; production API keeps its 30s server limit.
test.setTimeout(120_000);

const report = {
  reportStatus: 'COMPLETED', generatedAt: '2026-09-08T08:00:00Z',
  dataAvailability: { activeMedicationCount: 1, activeSupplementCount: 1, approvedInteractionRuleAvailable: true, ragEvidenceAvailable: true },
  executiveSummary: { reviewedProductCount: 2, potentialRedundancyCount: 0, interactionCheckCount: 0, summary: '등록한 두 제품을 확인했어요.', summaryCards: [
    { key: 'reviewedProductCount', label: '검토한 제품', value: 2, unit: '개' },
    { key: 'potentialRedundancyCount', label: '중복 확인 항목', value: 0, unit: '건' },
    { key: 'interactionCheckCount', label: '상호작용 확인 항목', value: 0, unit: '건' },
  ] },
  currentStack: [
    { itemType: 'MEDICATION', itemId: 11, productName: '테스트 처방약', ingredientName: null, registeredIntakeInfo: '1회 1정', scheduledSlots: ['EVENING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'SUPPLEMENT', itemId: 12, productName: '테스트 영양제', ingredientName: '비타민 C', registeredIntakeInfo: '1회 1정', scheduledSlots: ['MORNING'], evidenceLevel: 'REGISTERED_INTAKE' },
  ],
  reviewCards: [{ cardType: 'MISSING_INFO', title: '성분 확인 필요', summary: '일부 함량이 등록되지 않았어요.', relatedItems: ['테스트 영양제'], checkItem: '제품 라벨을 확인하세요.', evidenceLevel: 'UNVERIFIED', sources: [{ title: '잘못된 출처', organization: null, url: 'javascript:alert(1)', evidenceLevel: 'UNVERIFIED' }] }],
  nutrientTotals: [{ nutrientName: '비타민 C', dailyTotal: '100 mg', includedProductNames: ['테스트 영양제'], calculationStatus: 'CALCULATED' }],
  chartData: { medicationCount: 1, supplementCount: 1, interactionCardCount: 0, redundancyCardCount: 0, cautionCardCount: 0, missingInfoCardCount: 1 },
  productGuides: [{ productName: '테스트 처방약', oneLineSummary: '등록한 제품 안내입니다.', generalRole: null, checkItem: '전문가와 확인하세요.', sources: [] }],
  unverifiedItems: [{ itemType: 'MISSING_AMOUNT', title: '함량 미확인', message: '확인되지 않은 함량은 합산하지 않았어요.', relatedItems: ['테스트 영양제'], nextStep: '라벨 확인' }],
  reportMarkdown: '## 생활관리 안내\n\n**등록 정보 기준**으로 확인했어요.\n\n| 항목 | 내용 |\n| --- | --- |\n| 안내 | 라벨 확인 |\n\n<script>window.reportInjected = true</script>\n\n[위험 링크](javascript:alert(1))\n\n![외부 추적](https://example.com/tracker.png)',
};

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'report-api-test-token');
    sessionStorage.setItem('poke.account-principal', 'report-api@example.com');
  });
  // Keep production fetch, auth, rendering and routing; replace only external HTTP.
  await page.route('**/api/v1/**', route => route.fulfill({ status: 200, json: {} }));
});

for (const source of ['medications', 'supplements']) {
  test(`${source}: explicit request renders camelCase report and does not persist it`, async ({ page }, testInfo) => {
    const requests: { body: unknown; auth: string | undefined }[] = [];
    const mutations: string[] = [];
    page.on('request', request => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/api/v1/') && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
        mutations.push(`${request.method()} ${path}`);
      }
    });
    await page.route('**/api/v1/intake-reports', async route => {
      requests.push({ body: route.request().postDataJSON(), auth: route.request().headers().authorization });
      await route.fulfill({ json: report });
    });
    await page.setViewportSize({ width: 320, height: 740 });
    await page.goto(`/reports/new?source=${source}`);
    await expect(page.getByRole('button', { name: '보고서 생성하기', exact: true })).toBeVisible();
    expect(requests).toHaveLength(0);
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    await expect(page.getByRole('heading', { name: '생활관리 안내' })).toBeVisible();
    await expect(page.getByRole('button', { name: '이메일로 받기', exact: true })).toBeDisabled();
    await expect(page.getByText('이메일 발송 기능은 준비 중이에요.', { exact: true })).toBeVisible();
    await expect(page.getByRole('table', { name: '현재 복용 목록' })).toContainText('테스트 처방약');
    await expect(page.getByRole('table', { name: '일일 성분 합계' })).toContainText('100 mg');
    await expect(page.getByRole('figure', { name: '확인 항목 수' })).toContainText('정보 부족');
    await expect(page.getByText('함량 미확인', { exact: true })).toBeVisible();
    expect(requests).toEqual([{ body: {}, auth: 'Bearer report-api-test-token' }]);
    expect(await page.locator('a[href^="javascript:"], img[src*="tracker.png"], main script').count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain('테스트 처방약');
    await page.screenshot({ path: testInfo.outputPath(`report-${source}-320.png`), fullPage: true });
    await page.reload();
    await expect(page.getByRole('button', { name: '보고서 생성하기', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '생활관리 안내' })).toHaveCount(0);
    expect(requests).toHaveLength(1);
    expect(mutations).toEqual(['POST /api/v1/intake-reports']);
  });
}

test('pending generation prevents duplicate requests; timeout allows retry', async ({ page }) => {
  let calls = 0;
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/intake-reports', async route => {
    calls += 1;
    if (calls === 1) {
      await wait;
      await route.fulfill({ status: 504, json: { code: 'INTAKE_REPORT_TIMEOUT', message: '보고서 생성 시간이 초과되었습니다.' } });
    } else await route.fulfill({ json: { ...report, reportStatus: 'PARTIAL' } });
  });
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.getByRole('button', { name: '보고서 생성 중' })).toBeDisabled();
  expect(calls).toBe(1);
  release();
  await expect(page.getByRole('alert')).toContainText('생성 시간이 초과');
  await page.getByRole('button', { name: '다시 시도', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('일부 정보');
  await expect(page.getByRole('heading', { name: '생활관리 안내' })).toBeVisible();
  expect(calls).toBe(2);
});

test('EMPTY guides registration without inventing a health score', async ({ page }) => {
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, reportStatus: 'EMPTY', currentStack: [], reviewCards: [], nutrientTotals: [], productGuides: [], unverifiedItems: [], reportMarkdown: '',
    dataAvailability: { activeMedicationCount: 0, activeSupplementCount: 0, approvedInteractionRuleAvailable: false, ragEvidenceAvailable: false },
    executiveSummary: { reviewedProductCount: 0, potentialRedundancyCount: 0, interactionCheckCount: 0, summary: '등록 정보가 없어요.', summaryCards: [] },
    chartData: { medicationCount: 0, supplementCount: 0, interactionCardCount: 0, redundancyCardCount: 0, cautionCardCount: 0, missingInfoCardCount: 0 },
  } }));
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '분석할 복용 정보가 없어요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '영양제 관리로 이동' })).toBeVisible();
  await expect(page.getByRole('figure')).toHaveCount(0);
});

test('401 redirects to login and does not retain a report', async ({ page }) => {
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', message: '인증이 필요합니다.' } }));
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: '생활관리 안내' })).toHaveCount(0);
});

test('report entry does not promise history storage', async ({ page }) => {
  await page.goto('/reports');
  await expect(page.getByText('보고서는 저장되지 않아요.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'AI 보고서 받기', exact: true }).click();
  await expect(page).toHaveURL(/\/reports\/new\?source=medications$/);
});
