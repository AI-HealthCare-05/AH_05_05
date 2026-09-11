import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
// WSL's mounted worktree can spend >45s on Vite's first module transform.
// Assertion timeouts remain unchanged; report generation has a bounded server-side repair budget.
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
    await expect(page.getByText('이 보고서는 이메일 발송을 사용할 수 없어요. 새 보고서를 생성해주세요.', { exact: true })).toBeVisible();
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
  await page.goto('/reports/new?source=medications');
  await expect(page.getByText('보고서는 저장되지 않아요.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '보고서 생성하기', exact: true })).toBeEnabled();
});

test('ai-report-v2 renders the generated Markdown as the report body and keeps only registered values as supporting data', async ({ page }, testInfo) => {
  const aiGeneratedReport = {
    ...report,
    presentationVersion: 'ai-report-v2',
    profileLabel: '등록 정보 4종',
    basisNote: '등록한 복용 정보와 확인된 근거를 바탕으로 생성했습니다.',
    fallbackUsed: false,
    fallbackReason: null,
    dataAvailability: { activeMedicationCount: 3, activeSupplementCount: 1, approvedInteractionRuleAvailable: true, ragEvidenceAvailable: true },
    currentStack: [
      { itemType: 'MEDICATION', itemId: 1, productName: '낯선 약 알파 200mg', ingredientName: '성분 알파', registeredIntakeInfo: '하루 1정', scheduledSlots: ['MORNING'], evidenceLevel: 'REGISTERED_INTAKE' },
      { itemType: 'MEDICATION', itemId: 2, productName: '처방약 베타 100mg', ingredientName: '성분 베타', registeredIntakeInfo: '하루 1정', scheduledSlots: ['LUNCH'], evidenceLevel: 'REGISTERED_INTAKE' },
      { itemType: 'MEDICATION', itemId: 3, productName: '처방약 감마', ingredientName: null, registeredIntakeInfo: '필요 시 1정', scheduledSlots: [], evidenceLevel: 'REGISTERED_INTAKE' },
      { itemType: 'SUPPLEMENT', itemId: 4, productName: '영양제 철분', ingredientName: null, registeredIntakeInfo: '하루 1정', scheduledSlots: ['LUNCH'], evidenceLevel: 'REGISTERED_INTAKE' },
    ],
    reviewCards: [],
    nutrientTotals: [
      { nutrientName: '철', dailyTotal: '30 mg', includedProductNames: ['영양제 철분'], calculationStatus: 'CALCULATED', amount: '30', unit: 'mg', referenceValue: '12', referenceKind: 'RNI', referencePercent: '250', unknownProductNames: ['영양제 확인필요'] },
      { nutrientName: '비타민 B', dailyTotal: '10 μg', includedProductNames: ['영양제 철분'], calculationStatus: 'CALCULATED', amount: '10', unit: 'μg', referenceValue: '10', referenceKind: 'AI', referencePercent: '100' },
    ],
    productGuides: [],
    unverifiedItems: [],
    reportMarkdown: '# 실제 AI 생성 보고서\n\n## 복용약과 영양제 조합\n\n등록한 네 가지 제품의 조합을 검토했어요.\n\n## 생활 관리\n\n복용 변경 전에는 의료진과 상의하세요.\n\n## 약별 안내\n\n### 낯선 약 알파 200mg\n\n- 효능: AI가 확인한 설명\n- 주의: 등록 정보와 다르면 확인하세요.\n- 금기: 개인 상태에 따라 의료진에게 확인하세요.\n\n## 근거 출처\n\n[공공 근거](https://example.com/evidence)\n\n<script>window.reportInjected = true</script>\n\n[위험 링크](javascript:alert(1))\n\n![외부 추적](https://example.com/tracker.png)',
  };
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: aiGeneratedReport }));

  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    await expect(page.getByRole('heading', { name: '실제 AI 생성 보고서' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '복용약과 영양제 조합' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '생활 관리' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '약별 안내' })).toBeVisible();
    await expect(page.getByText('AI가 확인한 설명', { exact: false })).toBeVisible();
    for (const productName of ['낯선 약 알파 200mg', '처방약 베타 100mg', '처방약 감마', '영양제 철분']) {
      await expect(page.getByRole('table', { name: '현재 복용 목록' }).getByText(productName, { exact: true })).toBeVisible();
    }
    await expect(page.getByRole('heading', { name: '등록한 복용 정보' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '영양소 합계' })).toBeVisible();
    await expect(page.getByText('250%', { exact: true })).toBeVisible();
    await expect(page.getByText(/권장섭취량 12mg 기준/)).toBeVisible();
    await expect(page.getByText(/충분섭취량 10μg 기준/)).toBeVisible();
    await expect(page.getByRole('img', { name: '철 250%' }).locator('span')).toHaveAttribute('style', /width: 100%/);
    await expect(page.getByRole('img', { name: '철 250%' }).locator('..').getByText('100%', { exact: true })).toHaveClass(/left-\[75%\]/);
    await expect(page.getByRole('heading', { name: '먼저 확인할 약 조합' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '약 정보' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: '공공 근거' })).toHaveAttribute('href', 'https://example.com/evidence');
    expect(await page.locator('a[href^="javascript:"], main script').count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.screenshot({ path: testInfo.outputPath('ai-report-v2-390.png'), fullPage: true });
});

test('ai-report-v2 visibly identifies the verified-information fallback', async ({ page }) => {
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report,
    presentationVersion: 'ai-report-v2',
    fallbackUsed: true,
    fallbackReason: 'AI 응답 시간이 초과되었습니다.',
    reportMarkdown: '## 확인된 등록정보\n\n등록한 정보를 표시합니다.',
  } }));
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('AI 생성 결과가 아니라 확인된 등록정보·근거를 표시합니다');
  await expect(page.getByRole('alert')).toContainText('AI 응답 시간이 초과되었습니다.');
  await expect(page.getByRole('heading', { name: '확인된 등록정보' })).toBeVisible();
});
