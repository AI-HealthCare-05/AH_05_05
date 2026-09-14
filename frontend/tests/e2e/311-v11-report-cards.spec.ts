import { expect, test, type Page } from 'playwright/test';
import { existsSync, readFileSync } from 'node:fs';
import { extname, resolve } from 'node:path';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);

const staticBuildDir = process.env.V11_STATIC_BUILD_DIR ? resolve(process.env.V11_STATIC_BUILD_DIR) : null;
const contentTypes: Record<string, string> = { '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

async function serveStaticBuild(page: Page) {
  await page.route('**/*', async route => {
    if (!staticBuildDir) return route.fallback();
    const url = new URL(route.request().url());
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') return route.fallback();
    if (url.pathname.startsWith('/api/v1/')) return route.fallback();
    const relativePath = url.pathname === '/' ? 'index.html' : url.pathname.replace(/^\//, '');
    const candidate = resolve(staticBuildDir, relativePath);
    const safeCandidate = candidate === staticBuildDir || candidate.startsWith(`${staticBuildDir}\\`) || candidate.startsWith(`${staticBuildDir}/`);
    if (safeCandidate && existsSync(candidate)) return route.fulfill({ body: readFileSync(candidate), contentType: contentTypes[extname(candidate)] ?? 'application/octet-stream' });
    if (route.request().resourceType() === 'document') return route.fulfill({ body: readFileSync(resolve(staticBuildDir, 'index.html')), contentType: 'text/html' });
    return route.fallback();
  });
}

const report = {
  reportStatus: 'COMPLETED', generatedAt: '2026-09-11T00:00:00Z', presentationVersion: 'ai-report-v11',
  profileLabel: '27세 남성',
  dataAvailability: { activeMedicationCount: 2, activeSupplementCount: 3, approvedInteractionRuleAvailable: true, ragEvidenceAvailable: true },
  executiveSummary: { reviewedProductCount: 5, potentialRedundancyCount: 1, interactionCheckCount: 1, summary: '등록한 제품을 확인했어요.', summaryCards: [] },
  currentStack: [
    { itemType: 'MEDICATION', itemId: 71, productName: '가상 처방약 감마 25mg', ingredientName: '감마 성분', registeredIntakeInfo: '하루 1정', scheduledSlots: ['MORNING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'MEDICATION', itemId: 72, productName: '가상 처방약 델타', ingredientName: null, registeredIntakeInfo: '필요 시', scheduledSlots: [], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'SUPPLEMENT', itemId: 73, productName: '가상 비타민 D 제품 A', ingredientName: null, registeredIntakeInfo: '하루 1캡슐', scheduledSlots: ['EVENING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'SUPPLEMENT', itemId: 74, productName: '가상 비타민 D 제품 B', ingredientName: null, registeredIntakeInfo: '하루 1정', scheduledSlots: ['EVENING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'SUPPLEMENT', itemId: 75, productName: '가상 함량 미확인 제품', ingredientName: null, registeredIntakeInfo: '하루 1포', scheduledSlots: [], evidenceLevel: 'REGISTERED_INTAKE' },
  ],
  reviewCards: [], productGuides: [], unverifiedItems: [{ itemType: 'MISSING_AMOUNT', title: '함량 미확인 제품', message: '확인되지 않은 함량은 합산하지 않았어요.', relatedItems: ['가상 비타민 D 제품 B'], nextStep: '제품 라벨을 확인하세요.' }],
  nutrientTotals: [
    { nutrientName: '비타민 D', dailyTotal: '20 μg', includedProductNames: ['가상 비타민 D 제품 A', '가상 비타민 D 제품 B'], calculationStatus: 'PARTIAL', amount: '20', unit: 'μg', referenceValue: '10', referenceKind: 'AI', referencePercent: '200', unknownProductNames: ['가상 함량 미확인 제품'] },
    { nutrientName: '철', dailyTotal: '함량 미확인', includedProductNames: ['가상 함량 미확인 제품'], calculationStatus: 'UNAVAILABLE', amount: null, unit: null, referenceValue: null, referenceKind: null, referencePercent: null },
  ],
  chartData: { medicationCount: 2, supplementCount: 3, interactionCardCount: 1, redundancyCardCount: 1, cautionCardCount: 0, missingInfoCardCount: 1 },
  reportMarkdown: '# 이메일용 의미 투영만 존재합니다.',
  cards: {
    medications: [{
      itemId: 71, productName: '가상 처방약 감마 25mg',
      efficacy: { text: '확인된 효능 설명', sourceIds: ['med-source'] },
      caution: { text: '확인된 주의 설명', sourceIds: ['med-source'] },
      contraindication: { text: '확인된 금기 설명', sourceIds: ['med-source'] },
      details: [{ label: '등록한 복용 정보', text: '하루 1정', sourceIds: [] }, { label: '추가 안내', text: '확인된 상세 설명', sourceIds: ['med-source'] }],
      sourceIds: ['med-source'],
    }, {
      itemId: 72, productName: '가상 처방약 델타',
      efficacy: { text: '델타 효능', sourceIds: [] }, caution: { text: '델타 주의', sourceIds: [] }, contraindication: { text: '델타 금기', sourceIds: [] }, details: [], sourceIds: [],
    }],
    interactions: [{ id: 'public-guide', title: '가상 처방약 감마 안내', summary: '공개 제품 안내에서 확인한 일반 주의예요.', action: '개인 조합에 해당하는지는 전문가에게 확인하세요.', relatedItemIds: [71], sourceIds: ['public-source'], evidenceLevel: 'PUBLIC_GUIDE', actionLevel: 'CHECK' }],
    overlaps: [{ nutrientName: '비타민 D', title: '비타민 D가 2개 제품에 들어 있어요', summary: '두 제품의 확인된 함량을 함께 살펴보세요.', action: '추가 제품 전에는 현재 제품의 표시량을 확인하세요.', productNames: ['가상 비타민 D 제품 A', '가상 비타민 D 제품 B'], sourceIds: ['nutrient-source'] }],
    lifestyle: [{ id: 'habit', category: '복용 습관', title: '기록을 확인하세요', summary: '등록한 복용 정보를 기준으로 한 일반 안내예요.', action: '처방과 제품 안내를 우선하세요.', relatedItemIds: [71], sourceIds: ['public-source'] }],
    sources: [
      { id: 'med-source', title: '의약품 안내', organization: '공공기관', url: 'https://example.com/medicine', evidenceLevel: 'APPROVED_RULE' },
      { id: 'public-source', title: '공개 복용 안내', organization: null, url: 'https://example.com/guide', evidenceLevel: 'PUBLIC_GUIDE' },
      { id: 'nutrient-source', title: '영양소 안내', organization: '공공기관', url: 'javascript:alert(1)', evidenceLevel: 'PUBLIC_GUIDE' },
    ],
  },
};

for (const width of [390, 1280]) {
  test(`unavailable medicines share one list at ${width}px`, async ({ page }, testInfo) => {
    const grouped = structuredClone(report);
    grouped.cards.medications.push({ ...grouped.cards.medications[0], itemId: 99, productName: '스토엠정', hasInformation: false } as typeof grouped.cards.medications[number]);
    grouped.cards.medications.push({ ...grouped.cards.medications[0], itemId: 100, productName: '자료없는약정', hasInformation: false } as typeof grouped.cards.medications[number]);
    await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: grouped }));
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const section = page.locator('#v11-medications');
    const unavailable = section.getByRole('list', { name: '확인 불가 약품' });
    await expect(unavailable.getByRole('listitem')).toHaveCount(2);
    await expect(unavailable).toContainText('스토엠정');
    await expect(unavailable).toContainText('자료없는약정');
    await expect(section.locator('details')).toHaveCount(2);
    await section.locator('summary').first().click();
    await expect(section.getByText('확인된 효능 설명', { exact: true })).toBeVisible();
    await section.screenshot({ path: testInfo.outputPath(`grouped-medicines-${width}.png`) });
  });
}

test.beforeEach(async ({ page }) => {
  await serveStaticBuild(page);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'v11-card-test-token');
    sessionStorage.setItem('poke.account-principal', 'v11-card@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.route('**/api/v1/**', route => route.fulfill({ status: 200, json: {} }));
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: report }));
});

for (const version of ['ai-report-v11', 'ai-report-v2']) {
  test(`${version} keeps report-specific basis notes only above nutrient values`, async ({ page }, testInfo) => {
    const sectionId = version === 'ai-report-v11' ? '#v11-nutrients' : 'section[aria-labelledby="ai-report-nutrients"]';
    const notes = [
      '등록한 1회 복용량과 하루 복용 횟수를 제품 라벨 함량에 반영한 합계예요. 실제 복용 여부는 확인하지 않았고 식사는 제외했어요.',
      '제품 라벨의 1일 섭취 안내량 기준이며 실제 섭취량 합계가 아닙니다. 식사와 성분값·섭취 안내량이 누락된 제품은 제외했습니다.',
    ];
    for (const [index, basisNote] of notes.entries()) {
      await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, presentationVersion: version, basisNote } }));
      await page.setViewportSize({ width: index === 0 ? 390 : 1280, height: 900 });
      await page.goto('/reports/new?source=medications');
      await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
      const nutrients = page.locator(sectionId);
      await expect(nutrients.getByText(basisNote, { exact: true })).toBeVisible();
      await expect(page.getByText(basisNote, { exact: true })).toHaveCount(1);
      await expect(nutrients).toContainText('직접 입력한 영양제와 의약품의 성분은 합산에 포함되지 않아요.');
      await expect(nutrients.getByText('음식과 의약품을 통한 섭취량은 포함되지 않아요.', { exact: true })).toHaveCount(0);
      const noteBox = await nutrients.getByText(basisNote, { exact: true }).boundingBox();
      const valueBox = await (version === 'ai-report-v11'
        ? nutrients.getByRole('article', { name: '비타민 D 성분 합계' })
        : nutrients.getByRole('img', { name: '비타민 D 200%' })
      ).boundingBox();
      expect(noteBox!.y + noteBox!.height).toBeLessThan(valueBox!.y);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await nutrients.screenshot({ path: testInfo.outputPath(`nutrient-basis-${index}.png`) });
    }
    await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, presentationVersion: version, basisNote: null } }));
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    await expect(page.locator(sectionId)).toContainText('검색된 영양제의 성분만 합산된 결과예요.');
    await expect(page.locator(sectionId)).toContainText('음식과 의약품을 통한 섭취량은 포함되지 않아요.');

    await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, presentationVersion: version, basisNote: notes[0], nutrientTotals: [] } }));
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    await expect(page.locator(sectionId)).toHaveCount(0);
    await expect(page.getByText(notes[0], { exact: true })).toHaveCount(0);
  });
}

test('v11 rounded overview has no rectangular background strip above it', async ({ page }, testInfo) => {
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    await expect(page.getByRole('region', { name: '리포트 개요' })).toBeVisible();
    await expect(page.getByRole('region', { name: '리포트 개요' })).toContainText('27세 남성');
    await page.screenshot({ path: testInfo.outputPath(`v11-overview-${width}.png`) });
    await expect(page.locator('.v11-report')).toHaveCSS('background-image', 'none');
    await expect(page.locator('.v11-report')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('medication typo candidates remain a compact confirmation notice', async ({ page }, testInfo) => {
  const message = '‘타이래늘’의 제품명 후보: 타이레놀정500밀리그람, 타이레놀8시간이알서방정. 제품이 확정되지 않아 해당 제품 안내는 반영하지 않았습니다.';
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report,
    unverifiedItems: [{ itemType: 'AMBIGUOUS_PRODUCT', title: '의약품 제품명 확인 필요', message, relatedItems: ['타이레놀정500밀리그람', '타이레놀8시간이알서방정'], nextStep: '약봉투의 정확한 제품명과 성분명을 확인해 주세요.' }],
  } }));
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const section = page.locator('.v11-source-card').filter({ hasText: '확인하지 못한 정보' });
    await expect(section.locator('details')).not.toHaveAttribute('open', '');
    await section.locator('summary').click();
    await expect(section).toContainText(message);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await section.screenshot({ path: testInfo.outputPath(`typo-candidates-${width}.png`) });
  }
});

test('all registered nutrient totals remain visible with honest missing-reference labels', async ({ page }, testInfo) => {
  const names = ['식이섬유', '칼슘', '철', '인', '칼륨', '나트륨', '비타민 A', '레티놀', '베타카로틴', '티아민', '리보플라빈', '나이아신', '비타민 C', '비타민 D'];
  const totals = names.map((nutrientName, index) => ({
    ...report.nutrientTotals[0], nutrientName, amount: String(index + 1), dailyTotal: `${index + 1} mg`,
    unit: nutrientName === '비타민 A' ? 'μg RAE' : [7, 8, 13].includes(index) ? 'μg' : index === 0 ? 'g' : 'mg',
    referenceValue: [7, 8, 11].includes(index) ? null : '10', referenceKind: [7, 8, 11].includes(index) ? null : 'RNI', referencePercent: [7, 8, 11].includes(index) ? null : String((index + 1) * 10),
    unknownProductNames: index === 7 ? ['성분 미확인 제품'] : [],
  }));
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, nutrientTotals: totals } }));
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const section = page.locator('#v11-nutrients');
    const totals = section.locator('.nutrient-totals');
    await expect(totals.getByRole('article')).toHaveCount(names.length);
    await expect(section).toContainText('비타민 A');
    const retinol = totals.getByRole('article', { name: '레티놀 성분 합계' });
    await expect(retinol).toContainText('비교 기준 없음');
    await expect(retinol).not.toContainText('합산에서 제외된 제품');
    await expect(retinol).not.toContainText('성분 미확인 제품');
    await expect(retinol.locator('[data-nutrient-range]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const columns = await totals.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length);
    expect(columns).toBe(1);
    await section.screenshot({ path: testInfo.outputPath(`all-nutrients-${width}.png`) });
  }
});

test('v11 shows positive nutrient totals without zero or unknown rows', async ({ page }, testInfo) => {
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, nutrientTotals: [
      ...report.nutrientTotals,
      { ...report.nutrientTotals[0], nutrientName: '나트륨', amount: '0.00', dailyTotal: '0 mg', referencePercent: '0' },
    ],
  } }));
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=supplements');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const section = page.locator('#v11-nutrients');
    await expect(section.locator('.nutrient-totals').getByRole('article')).toHaveCount(1);
    await expect(section).not.toContainText('나트륨');
    await expect(section).toContainText('비타민 D');
    await expect(section).not.toContainText('미확인');
    const unknown = section.getByRole('article', { name: '철 성분 합계' });
    await expect(unknown).toHaveCount(0);
    await section.screenshot({ path: testInfo.outputPath(`positive-nutrients-${width}.png`) });
  }
});

test('v11 nutrient ranges use the supplement-card threshold contract', async ({ page }, testInfo) => {
  const totals = [
    { ...report.nutrientTotals[0], nutrientName: '칼슘', amount: '600', unit: 'mg', referenceValue: '800', referenceKind: 'RNI', upperLimitValue: '3000' },
    { ...report.nutrientTotals[0], nutrientName: '비타민 D', amount: '33', referenceValue: '10', upperLimitValue: '100' },
    { ...report.nutrientTotals[0], nutrientName: '비타민 C', amount: '80', unit: 'mg', referenceValue: '100', referenceKind: 'RNI', upperLimitValue: '2000' },
    { ...report.nutrientTotals[0], nutrientName: '철', amount: '70', unit: 'mg', referenceValue: '8', referenceKind: 'RNI', upperLimitValue: '40' },
    { ...report.nutrientTotals[0], nutrientName: '비타민 A', amount: '700', unit: 'μg RAE', referenceValue: '800', referenceKind: 'RNI', upperLimitValue: '3000', upperLimitNote: null },
  ];
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, nutrientTotals: totals } }));
  for (const width of [320, 390, 760, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=supplements');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const section = page.locator('#v11-nutrients');
    await expect(section.locator('.nutrient-totals')).toHaveCount(1);
    const totals = section.locator('.nutrient-totals');
    const calcium = totals.getByRole('article', { name: '칼슘 성분 합계' });
    await expect(calcium).toContainText('600mg');
    await expect(calcium.locator('[data-nutrient-status]')).toHaveText('권장량의 75%예요');
    await expect(calcium.locator('[data-threshold-label="upper-limit"]')).toContainText('상한3,000');
    expect(await calcium.locator('[data-threshold="upper-limit"]').evaluate(el => (el as HTMLElement).style.left)).toBe('88%');
    expect(await calcium.locator('[data-range-marker]').evaluate(el => Number.parseFloat((el as HTMLElement).style.left))).toBeCloseTo(17.6, 2);
    await expect(calcium.locator('[data-range-fill]')).toHaveClass(/bg-warning/);
    const vitaminD = totals.getByRole('article', { name: '비타민 D 성분 합계' });
    await expect(vitaminD.locator('[data-nutrient-status]')).toHaveText('권장 범위예요');
    await expect(vitaminD.locator('[data-range-fill]')).toHaveClass(/bg-primary/);
    expect(await vitaminD.locator('[data-range-marker]').evaluate(el => Number.parseFloat((el as HTMLElement).style.left))).toBeCloseTo(29.04, 2);
    const vitaminA = totals.getByRole('article', { name: '비타민 A 성분 합계' });
    await expect(vitaminA.locator('[data-threshold-label="upper-limit"]')).toContainText('상한3,000');
    await expect(vitaminA.locator('[data-nutrient-status]')).toHaveText('권장량의 88%예요');
    await expect(vitaminA).not.toContainText('성분 형태별 상한 기준이 달라');
    expect(await vitaminA.locator('[data-range-marker]').evaluate(el => Number.parseFloat((el as HTMLElement).style.left))).toBeCloseTo(20.53, 2);
    if (width === 320) {
      for (const nutrient of [calcium, vitaminA]) {
        const cardBox = await nutrient.boundingBox();
        const summaryBox = await nutrient.locator('[data-testid="nutrient-total-summary"]').boundingBox();
        const statusBox = await nutrient.locator('[data-nutrient-status]').boundingBox();
        expect(cardBox && summaryBox && statusBox).toBeTruthy();
        expect(statusBox!.x).toBeGreaterThanOrEqual(cardBox!.x);
        expect(statusBox!.x + statusBox!.width).toBeLessThanOrEqual(cardBox!.x + cardBox!.width);
        const overlaps = statusBox!.x < summaryBox!.x + summaryBox!.width
          && summaryBox!.x < statusBox!.x + statusBox!.width
          && statusBox!.y < summaryBox!.y + summaryBox!.height
          && summaryBox!.y < statusBox!.y + statusBox!.height;
        expect(overlaps).toBe(false);
      }
    }
    const iron = totals.getByRole('article', { name: '철 성분 합계' });
    await expect(iron.locator('[data-nutrient-status]')).toHaveText('상한 초과');
    await expect(iron.locator('[data-range-fill]')).toHaveClass(/bg-danger/);
    expect(await iron.locator('[data-range-marker]').evaluate(el => (el as HTMLElement).style.left)).toBe('100%');
    expect(await totals.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await section.screenshot({ path: testInfo.outputPath(`range-thresholds-${width}.png`) });
  }
});

test('v11 displays two decimal places without rounding the graph evaluation', async ({ page }, testInfo) => {
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report,
    nutrientTotals: [{ ...report.nutrientTotals[0], amount: '1.6666666666', referenceValue: '1.661', upperLimitValue: '1.665' }],
  } }));
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  const nutrient = page.locator('#v11-nutrients').getByRole('article');
  await expect(nutrient.locator('strong')).toHaveText('1.67');
  await expect(nutrient.locator('[data-threshold-label="base"]')).toContainText('1.66');
  await expect(nutrient.locator('[data-threshold-label="upper-limit"]')).toContainText('1.67');
  await expect(nutrient.locator('[data-nutrient-status]')).toHaveText('상한 초과');
  await nutrient.screenshot({ path: testInfo.outputPath('two-decimal-report.png') });
});

test('v11 refuses malformed report standards instead of inventing a range', async ({ page }, testInfo) => {
  const totals = [
    { ...report.nutrientTotals[0], nutrientName: '칼슘', amount: '900', unit: 'mg', referenceValue: '800', referenceKind: 'RNI', upperLimitValue: '600', upperLimitNote: '입력된 상한 기준은 권장량보다 낮아 비교하지 않았어요.' },
    { ...report.nutrientTotals[0], nutrientName: '셀레늄', amount: '20', unit: null, referenceValue: '60', referenceKind: 'RNI', upperLimitValue: '400' },
    { ...report.nutrientTotals[0], nutrientName: '구리', amount: '3', unit: 'mg', referenceValue: '1', referenceKind: 'UNKNOWN', upperLimitValue: null },
  ];
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, nutrientTotals: totals } }));
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=supplements');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const calcium = page.getByRole('article', { name: '칼슘 성분 합계' });
    await expect(calcium).toContainText('900mg');
    await expect(calcium).toContainText('입력된 상한 기준은 권장량보다 낮아 비교하지 않았어요.');
    await expect(calcium.locator('[data-threshold="upper-limit"]')).toHaveCount(0);
    await expect(calcium.locator('[data-nutrient-range]')).toHaveAttribute('aria-hidden', 'true');
    const selenium = page.getByRole('article', { name: '셀레늄 성분 합계' });
    await expect(selenium).toContainText('20');
    await expect(selenium).toContainText('비교 기준 없음 · 확인된 합계만 표시했어요.');
    await expect(selenium.locator('[data-nutrient-range], [data-nutrient-status]')).toHaveCount(0);
    const copper = page.getByRole('article', { name: '구리 성분 합계' });
    await expect(copper).toContainText('3mg');
    await expect(copper).toContainText('비교 기준 없음 · 확인된 합계만 표시했어요.');
    await expect(copper.locator('[data-nutrient-range], [data-nutrient-status]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator('#v11-nutrients').screenshot({ path: testInfo.outputPath(`malformed-nutrient-standards-${width}.png`) });
  }
});

test('v11 overview expands registered products responsively and closes with keyboard', async ({ page }, testInfo) => {
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const overview = page.getByRole('region', { name: '리포트 개요' });
    const toggle = overview.locator('summary');
    const medicines = overview.getByRole('list', { name: '등록한 복용약' });
    const supplements = overview.getByRole('list', { name: '등록한 영양제' });
    await expect(toggle).toHaveText('등록한 복용약 2종 · 영양제 3종');
    await expect(medicines).toBeHidden();
    await toggle.click();
    await expect(medicines.getByRole('listitem')).toHaveText(['가상 처방약 감마 25mg', '가상 처방약 델타']);
    await expect(supplements.getByRole('listitem')).toHaveText([
      '가상 비타민 D 제품 A성분·함량 확인 필요',
      '가상 비타민 D 제품 B성분·함량 확인 필요',
      '가상 함량 미확인 제품성분·함량 확인 필요',
    ]);
    await expect(overview.getByText('사용자가 등록한 복용 정보', { exact: true })).toHaveCount(0);
    await expect(overview.getByText('하루 1캡슐', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '등록한 영양제 3종', exact: true })).toHaveCount(0);
    const left = await medicines.boundingBox();
    const right = await supplements.boundingBox();
    expect(left && right).toBeTruthy();
    if (width <= 480) {
      expect(right!.y).toBeGreaterThan(left!.y + left!.height);
    } else {
      expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
      expect(Math.abs(left!.y - right!.y)).toBeLessThan(2);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`v11-products-open-${width}.png`) });
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(medicines).toBeHidden();
    await expect(supplements).toBeHidden();
  }
});

test('v11 shows per-product ingredient amounts only inside the existing product disclosure', async ({ page }, testInfo) => {
  const summaries: Record<number, string> = {
    71: '복용약에 표시하면 안 되는 영양제 성분',
    73: '비타민 D 10μg · 칼슘 200mg',
    74: '티아민 1.2mg · 리보플라빈 1.4mg · 나이아신 16mg · 비타민 C 100mg · 철 12mg',
  };
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, currentStack: report.currentStack.map(item => ({ ...item, ingredientSummary: summaries[item.itemId] ?? null })),
  } }));
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=supplements');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const overview = page.getByRole('region', { name: '리포트 개요' });
    const products = overview.getByRole('list', { name: '등록한 영양제' }).getByRole('listitem');
    await expect(overview.getByText(summaries[73], { exact: true })).toBeHidden();
    await overview.locator('summary').click();
    await expect(products.nth(0).getByText(summaries[73], { exact: true })).toBeVisible();
    await expect(overview.getByText('영양제 성분 · 등록한 하루량 기준', { exact: true })).toHaveCount(1);
    await expect(products.nth(1).getByText(summaries[74], { exact: true })).toBeVisible();
    await expect(products.nth(2).getByText('성분·함량 확인 필요', { exact: true })).toBeVisible();
    await expect(page.getByText(summaries[71], { exact: true })).toHaveCount(0);
    await expect(overview.locator('summary')).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await overview.screenshot({ path: testInfo.outputPath(`ingredient-summary-${width}.png`) });
    await overview.locator('summary').click();
    await expect(overview.getByText(summaries[74], { exact: true })).toBeHidden();
  }
});

test('v11 overview keeps an empty product column explicit', async ({ page }) => {
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report,
    currentStack: report.currentStack.filter(item => item.itemType === 'SUPPLEMENT'),
    dataAvailability: { ...report.dataAvailability, activeMedicationCount: 0 },
    cards: { ...report.cards, medications: [] },
  } }));
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  const overview = page.getByRole('region', { name: '리포트 개요' });
  await overview.locator('summary').click();
  await expect(overview.getByRole('heading', { name: '복용약 0종', exact: true })).toBeVisible();
  await expect(overview.getByText('등록된 제품 없음', { exact: true })).toBeVisible();
  await expect(overview.getByRole('list', { name: '등록한 영양제' }).getByRole('listitem')).toHaveCount(3);
});

test('v11 omits registered intake lines while retaining supplement products', async ({ page }, testInfo) => {
  const doses = ['2정', '1.5캡슐', '0.005g'];
  const supplements = report.currentStack.filter(item => item.itemType === 'SUPPLEMENT');
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, currentStack: supplements.map((item, index) => ({ ...item, registeredIntakeInfo: doses[index] })),
  } }));
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=supplements');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const overview = page.getByRole('region', { name: '리포트 개요' });
    const list = overview.getByRole('list', { name: '등록한 영양제' });
    await expect(list).toBeHidden();
    await overview.locator('summary').click();
    await expect(list.locator('.v11-product-intake')).toHaveCount(0);
    for (const dose of doses) await expect(list.getByText(dose, { exact: true })).toHaveCount(0);
    await expect(list).toContainText('가상 비타민 D 제품 A');
    await list.screenshot({ path: testInfo.outputPath(`registered-intake-omitted-${width}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('v11 shows medicine names with right-side details and folds efficacy independently', async ({ page }, testInfo) => {
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const medicines = page.locator('.v11-medicine');
    const first = medicines.first();
    const second = medicines.nth(1);
    await expect(first.getByText('확인된 효능 설명', { exact: true })).toBeHidden();
    await expect(first.locator('summary')).toContainText('가상 처방약 감마 25mg');
    await expect(first.locator('summary').getByText('상세 보기', { exact: true })).toBeVisible();
    await expect(first.getByText('확인된 주의 설명', { exact: true })).toBeHidden();
    await expect(first.getByText('확인된 금기 설명', { exact: true })).toBeHidden();
    await expect(second.getByText('델타 효능', { exact: true })).toBeHidden();
    await expect(second.getByText('델타 주의', { exact: true })).toBeHidden();
    await page.locator('#v11-medications').screenshot({ path: testInfo.outputPath(`medicines-closed-${width}.png`) });
    await first.locator('summary').click();
    await expect(first.locator('summary').getByText('접기', { exact: true })).toBeVisible();
    await expect(first.getByText('확인된 효능 설명', { exact: true })).toBeVisible();
    await expect(first.locator('dt').first()).toHaveText('효능');
    await expect(first.getByText('확인된 주의 설명', { exact: true })).toBeVisible();
    await expect(first.getByText('확인된 금기 설명', { exact: true })).toBeVisible();
    await expect(first.getByText('사용자가 등록한 복용 정보', { exact: true })).toHaveCount(0);
    await expect(first.getByText('하루 1정', { exact: true })).toHaveCount(0);
    await expect(first.getByText('확인된 상세 설명', { exact: true })).toBeVisible();
    await expect(second.getByText('델타 주의', { exact: true })).toBeHidden();
    await expect(second.getByText('델타 효능', { exact: true })).toBeHidden();
    await second.locator('summary').click();
    await expect(second.getByText('델타 주의', { exact: true })).toBeVisible();
    await page.locator('#v11-medications').screenshot({ path: testInfo.outputPath(`medicines-open-${width}.png`) });
    await first.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(first.getByText('확인된 주의 설명', { exact: true })).toBeHidden();
    await expect(first.getByText('확인된 효능 설명', { exact: true })).toBeHidden();
    await expect(first.locator('summary').getByText('상세 보기', { exact: true })).toBeVisible();
    const titleBox = await first.locator('summary h3').boundingBox();
    const toggleBox = await first.locator('summary .v11-medicine-toggle').boundingBox();
    expect(titleBox).not.toBeNull();
    expect(toggleBox).not.toBeNull();
    expect(titleBox!.x + titleBox!.width).toBeLessThanOrEqual(toggleBox!.x);
    await expect(second.getByText('델타 주의', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('v11 nutrient cards disclose only included products by keyboard without leaking unknown names', async ({ page }, testInfo) => {
  const names = ['가상 제품 A', '가상 제품 B', '가상 제품 C'];
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, nutrientTotals: [{ ...report.nutrientTotals[0], unknownProductNames: names }],
  } }));
  for (const width of [320, 390, 759, 760, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=supplements');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const nutrient = page.getByRole('article', { name: '비타민 D 성분 합계' });
    await expect(nutrient).toBeVisible();
    const disclosure = nutrient.locator('details');
    const summary = disclosure.locator('summary');
    await expect(disclosure).not.toHaveAttribute('open', '');
    await expect(summary).toHaveText('성분 포함 제품 2개');
    await expect(nutrient).not.toContainText('합산에서 제외');
    for (const name of names) await expect(nutrient).not.toContainText(name);
    await expect(nutrient.locator('[data-nutrient-range]')).toBeVisible();
    await expect(page.locator('#v11-nutrients .v11-nutrient-notes')).toBeVisible();
    const columns = await page.locator('.nutrient-totals').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length);
    expect(columns).toBe(1);
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(disclosure).toHaveAttribute('open', '');
    await expect(disclosure).toContainText('가상 비타민 D 제품 A');
    await expect(disclosure).toContainText('가상 비타민 D 제품 B');
    const summaryBox = await summary.boundingBox();
    const disclosureBox = await disclosure.boundingBox();
    expect(summaryBox && disclosureBox).toBeTruthy();
    expect(summaryBox!.width).toBeLessThanOrEqual(disclosureBox!.width);
    await page.locator('#v11-nutrients').screenshot({ path: testInfo.outputPath(`clean-nutrients-${width}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('v11 shows the registered two-tablet iron total and reference from the server', async ({ page }, testInfo) => {
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report,
    nutrientTotals: [{ ...report.nutrientTotals[0], nutrientName: '철', dailyTotal: '24 mg', amount: '24', unit: 'mg',
      referenceValue: '12', referenceKind: 'RNI', referencePercent: '200', calculationStatus: 'REGISTERED_SCHEDULE', unknownProductNames: [] }],
  } }));
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  const iron = page.getByRole('article', { name: '철 성분 합계' });
  await expect(iron.getByRole('heading', { name: '철', exact: true })).toBeVisible();
  await expect(iron).toContainText('24mg');
  await expect(iron.locator('[data-nutrient-status]')).toHaveText('권장량의 200%예요');
  await expect(iron.locator('[data-nutrient-range]')).toHaveAttribute('aria-hidden', 'true');
  await expect(iron.locator('[data-threshold-label="base"]')).toContainText('권장12');
  await iron.screenshot({ path: testInfo.outputPath('registered-iron-24mg.png') });
});

test('v11 only offers expansion for visually clipped text and rechecks after resize', async ({ page }, testInfo) => {
  const summary = '케토코나졸이나 에리트로마이신, 알루미늄, 수산화마그네슘을 함유한 제산제, 아팔루타마이드와 같은 P-gp유도제와 함께 사용시 의사 또는 약사와 상의하십시오. 자몽 주스, 오렌지 및 사과 주스와 같은 과일 주스와 함께 복용시 이 약의 효과를 감소시킬 수 있으므로 물과 함께 복용하는 것을 권장합니다.';
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, cards: { ...report.cards, interactions: [{ ...report.cards.interactions[0], summary }] },
  } }));
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  const card = page.locator('#v11-interactions .v11-pair');
  await expect(card).toContainText(summary);
  await expect(card.getByText('자세히 펼쳐보기', { exact: false })).toHaveCount(0);
  await card.screenshot({ path: testInfo.outputPath('unclipped-desktop.png') });
  await page.setViewportSize({ width: 390, height: 900 });
  const toggle = card.getByRole('button', { name: /자세히 펼쳐보기/ });
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(card.getByRole('button', { name: /접기/ })).toHaveAttribute('aria-expanded', 'true');
  await expect(card.locator('.v11-collapsible-full')).toHaveText(summary);
  await card.screenshot({ path: testInfo.outputPath('expanded-mobile.png') });
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(card.getByRole('button', { name: /접기|자세히 펼쳐보기/ })).toHaveCount(0);
  await expect(card).toContainText(summary);
  await page.setViewportSize({ width: 390, height: 900 });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
});

test('v11 rechecks clipping after font loading even when the clamped box stays the same size', async ({ page }) => {
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, cards: { ...report.cards, interactions: [{ ...report.cards.interactions[0], summary: '가'.repeat(120) }] },
  } }));
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/reports/new?source=medications');
  await page.addStyleTag({ content: '#v11-interactions .v11-collapsible p { width: 600px; font-size: 13px; line-height: 20px; }' });
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  const card = page.locator('#v11-interactions .v11-pair');
  await expect(card.getByRole('button', { name: /자세히 펼쳐보기/ })).toHaveCount(0);
  const before = await card.locator('.v11-collapsible-preview').boundingBox();
  await card.locator('.v11-collapsible-preview').evaluate(element => {
    // Model glyph-width changes while the three-line clamped box remains unchanged.
    element.style.letterSpacing = '6px';
    document.fonts.dispatchEvent(new Event('loadingdone'));
  });
  await expect(card.getByRole('button', { name: /자세히 펼쳐보기/ })).toBeVisible();
  expect((await card.locator('.v11-collapsible-preview').boundingBox())!.height).toBe(before!.height);
});

test('v11 groups common actions, collapses long details, and lists sources only at bottom', async ({ page }, testInfo) => {
  const grouped = structuredClone({ ...report, cards: { ...report.cards, originalTexts: [
    { key: 'medication/0/efficacy', label: '가상 처방약 감마 25mg · 효능', text: '제품 안내의 정리 전 원문이에요.', sourceIds: ['guide:1'] },
  ] } });
  const action = '복용 전 전문가에게 확인하세요.';
  const longText = '제품별 세부 설명은 원문을 유지하며 펼쳐서 확인할 수 있어요. '.repeat(8);
  grouped.cards.interactions = [
    { ...report.cards.interactions[0], id: 'a', title: '가상 조합 A', action, summary: longText },
    { ...report.cards.interactions[0], id: 'b', title: '가상 조합 B', action },
    { ...report.cards.interactions[0], id: 'c', title: '가상 조합 C', action, summary: longText, actionLevel: 'WARNING', evidenceLevel: 'APPROVED_RULE' },
  ];
  grouped.cards.overlaps[0].summary = longText;
  grouped.cards.medications[0].efficacy.text = longText;
  grouped.cards.medications[0].caution.text = '즉시 복용을 중단하고 상담하세요. ' + longText;
  grouped.cards.medications[0].contraindication.text = longText;
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: grouped }));
  await page.setViewportSize({ width: 390, height: 812 });
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.locator('.v11-action-group')).toHaveCount(1);
  await expect(page.locator('.v11-action')).toHaveCount(4);
  await expect(page.locator('.v11-action')).toContainText([action, action, grouped.cards.overlaps[0].action, grouped.cards.lifestyle[0].action]);
  await expect(page.locator('#v11-interactions .v11-pair')).toHaveCount(3);
  await expect(page.locator('.v11-card-sources')).toHaveCount(0);
  await expect(page.locator('.v11-report a[href="https://example.com/guide"]')).toHaveCount(1);
  await expect(page.locator('.v11-urgent .v11-collapsible')).toHaveCount(0);
  await expect(page.locator('.v11-urgent')).toContainText(longText.trim());
  const medicine = page.locator('.v11-medicine').first();
  await expect(medicine.locator('dl > div').nth(0).locator('details')).toHaveCount(0);
  await expect(medicine.locator('dl > div').nth(0)).toContainText(longText.trim());
  await expect(medicine.locator('dl > div').nth(1).locator('details')).toHaveCount(0);
  await expect(medicine.locator('dl > div').nth(2).locator('details')).toHaveCount(0);
  const details = page.locator('#v11-overlaps .v11-collapsible').first();
  await expect(details.locator('.v11-collapsible-full')).toBeHidden();
  const expandLabel = details.locator('.v11-expand-label');
  const expandArrow = expandLabel.locator('[aria-hidden="true"]');
  await expect(expandArrow).toBeVisible({ timeout: 3000 });
  const labelBox = await expandLabel.boundingBox();
  const arrowBox = await expandArrow.boundingBox();
  expect(labelBox && arrowBox).toBeTruthy();
  expect(Math.abs((arrowBox!.y + arrowBox!.height / 2) - (labelBox!.y + labelBox!.height / 2))).toBeLessThan(2);
  await details.getByRole('button', { name: /자세히 펼쳐보기/ }).click();
  await expect(details.locator('.v11-collapse-label [aria-hidden="true"]')).toBeVisible();
  await expect(details.locator('.v11-collapsible-full')).toBeVisible();
  await expect(details.locator('.v11-collapsible-full')).toHaveText(longText);
  await details.getByRole('button', { name: /접기/ }).focus();
  await page.keyboard.press('Enter');
  await expect(details.locator('.v11-collapsible-full')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('#v11-originals')).toHaveCount(0);
  await expect(page.getByText('정리 전 원문 보기', { exact: true })).toHaveCount(0);
  await expect(page.getByText('제품 안내의 정리 전 원문이에요.', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('v11-grouped-collapsed.png'), fullPage: true });
});

for (const startsWithGroup of [false, true]) {
  test(`v11 distinguishes group boundaries from inner dividers (group first: ${startsWithGroup})`, async ({ page }, testInfo) => {
    const grouped = structuredClone(report);
    const base = report.cards.lifestyle[0];
    grouped.cards.lifestyle = [
      ...(!startsWithGroup ? [{ ...base, id: 'timing', category: '복용 시점', title: '등록한 복용 시점 안내', action: '제품 안내에 맞는 시간을 참고해 주세요.' }] : []),
      ...['감마', '델타', '엡실론', '제타'].map((name, index) => ({
        ...base, id: `food-${index}`, category: '약과 음식·술 주의', title: `가상 처방약 ${name}과 음식·음료`,
        summary: '해당 제품 안내에 기재된 음식·음료 관련 주의사항입니다.', action: '제품 안내의 조건과 실제 처방·복약 지시를 확인하세요.',
      })),
      ...['칼슘', '비타민 C'].map((name, index) => ({
        ...base, id: `nutrient-${index}`, category: '영양소 식품 안내', title: `${name}이 들어있는 식품`,
        summary: '등록 성분에 관한 참고 식품 안내입니다.', action: '식품은 참고 예시이며, 영양소 부족을 뜻하지 않아요.',
      })),
      { ...base, id: 'last', category: '복용 습관', title: '등록 정보 확인', action: '등록된 복용 기록을 확인해 주세요.' },
    ];
    await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: grouped }));
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const section = page.locator('#v11-lifestyle');
    const groups = section.locator(':scope > .v11-action-group');
    await expect(groups).toHaveCount(2);
    await expect(groups.first().locator('.v11-pair')).toHaveCount(4);
    await expect(groups.last().locator('.v11-pair')).toHaveCount(2);
    for (const width of [320, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      const lines = await section.evaluate(element => {
        const groups = element.querySelectorAll(':scope > .v11-action-group');
        const inner = getComputedStyle(groups[0].querySelectorAll('.v11-pair')[1]);
        const boundary = getComputedStyle(groups[1]);
        const following = getComputedStyle(groups[1].nextElementSibling!);
        return {
          inner: parseFloat(inner.borderTopWidth), boundary: parseFloat(boundary.borderTopWidth),
          following: parseFloat(following.borderTopWidth), first: parseFloat(getComputedStyle(groups[0]).borderTopWidth),
          innerPadding: parseFloat(inner.paddingTop), boundaryPadding: parseFloat(boundary.paddingTop),
          firstMember: getComputedStyle(groups[0].querySelector('.v11-pair')!).borderTopWidth,
        };
      });
      expect(lines.inner).toBeGreaterThan(0);
      expect(lines.boundary).toBeGreaterThan(lines.inner);
      expect(lines.following).toBe(lines.boundary);
      expect(lines.first).toBe(startsWithGroup ? 0 : lines.boundary);
      expect(lines.firstMember).toBe('0px');
      expect(lines.boundaryPadding).toBeGreaterThan(lines.innerPadding);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await section.screenshot({ path: testInfo.outputPath(`group-dividers-${width}.png`) });
    }
  });
}

test('v11 renders server-owned cards once, keeps public guidance non-personal, and stays responsive', async ({ page }, testInfo) => {
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();

    await expect(page.getByText('등록한 복용약 2종 · 영양제 3종', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '함께 확인할 주의사항' })).toBeVisible();
    await expect(page.getByText('공개 안내 · 개인 조합 확인 필요', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '영양제끼리 확인할 점' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '비타민 D가 2개 제품에 들어 있어요' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '생활습관 가이드' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '영양제 성분 합계' })).toBeVisible();
    await expect(page.locator('#v11-nutrients .v11-nutrient-notes li')).toHaveText([
      '검색된 영양제의 성분만 합산된 결과예요.',
      '직접 입력한 영양제는 성분 합산에 포함되지 않아요.',
      '음식과 의약품을 통한 섭취량은 포함되지 않아요.',
    ]);
    await page.locator('#v11-nutrients').screenshot({ path: testInfo.outputPath(`nutrient-notes-${width}.png`) });
    await expect(page.getByRole('heading', { name: '약 정보' })).toBeVisible();
    await expect(page.getByText('확인된 효능 설명', { exact: true })).toBeHidden();
    await expect(page.getByText('확인된 주의 설명', { exact: true })).toBeHidden();
    await expect(page.getByText('확인된 금기 설명', { exact: true })).toBeHidden();
    await expect(page.getByText('델타 효능', { exact: true })).toBeHidden();
    await expect(page.locator('#v11-nutrients')).not.toContainText('합산에서 제외된 제품');
    const iron = page.getByRole('article', { name: '철 성분 합계' });
    await expect(iron).toHaveCount(0);
    await expect(iron.locator('[data-nutrient-range], [data-nutrient-status]')).toHaveCount(0);
    await expect(iron.getByText('가상 함량 미확인 제품', { exact: true })).toBeHidden();
    await expect(page.getByRole('heading', { name: '등록한 영양제 3종' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '상세 보고서' })).toHaveCount(0);
    await expect(page.getByRole('table', { name: '현재 복용 목록' })).toHaveCount(0);
    await expect(page.getByRole('article', { name: '비타민 D 성분 합계' })).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`v11-card-report-${width}.png`), fullPage: true });
  }

  const sourceDetails = page.getByText('비교 기준과 출처', { exact: true }).locator('..');
  await sourceDetails.getByText('비교 기준과 출처', { exact: true }).click();
  await expect(sourceDetails.getByRole('link', { name: '의약품 안내' })).toHaveAttribute('href', 'https://example.com/medicine');
  await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0);
  const medicationDetails = page.locator('.v11-medicine details').first();
  await medicationDetails.locator('summary').click();
  await expect(medicationDetails).toHaveAttribute('open', '');
  await expect(medicationDetails.getByText('사용자가 등록한 복용 정보', { exact: true })).toHaveCount(0);
  await expect(medicationDetails.getByText('하루 1정', { exact: true })).toHaveCount(0);
});

test('v11 makes missing interaction evidence and partial data visibly non-reassuring', async ({ page }) => {
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    ...report, reportStatus: 'PARTIAL', cards: { ...report.cards, interactions: [] },
  } }));
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('정보 부족은 안전하다는 뜻이 아니에요');
  await expect(page.getByRole('heading', { name: '함께 확인할 주의사항' })).toBeVisible();
  await expect(page.getByText('안전하다는 뜻은 아니며', { exact: false })).toBeVisible();
});

test('v11 reveals inferred product context before efficacy when medicine details open', async ({ page }, testInfo) => {
  const inferred = structuredClone(report);
  inferred.cards.medications[0].identityNotice = '‘가상 처방약 감마 25mg 오타’를 ‘가상 처방약 감마 25mg’으로 추정한 제품 안내입니다. 등록한 이름은 바꾸지 않았어요.';
  inferred.currentStack[0].productName = '가상 처방약 감마 25mg 오타';
  inferred.cards.medications[0].productName = '가상 처방약 감마 25mg 오타';
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: inferred }));

  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    const medicine = page.locator('.v11-medicine').first();
    const notice = medicine.getByText('등록한 이름은 바꾸지 않았어요.', { exact: false });
    await expect(medicine.locator('summary')).toContainText('가상 처방약 감마 25mg 오타');
    await expect(notice).toBeHidden();
    await expect(medicine.locator('details')).not.toHaveAttribute('open', '');
    await medicine.locator('summary').click();
    await expect(notice).toBeVisible();
    await expect(medicine.locator('summary + .v11-hint')).toContainText('추정한 제품 안내입니다.');
    await expect(medicine.getByText('확인된 효능 설명', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await medicine.screenshot({ path: testInfo.outputPath(`inferred-guide-notice-${width}.png`) });
  }
});

test('v11 decodes clinical entities once and keeps encoded markup inert', async ({ page }) => {
  const encoded = structuredClone(report);
  encoded.cards.medications[1].efficacy.text = 'γ 비교 &gamma; &#945;';
  encoded.cards.medications[1].caution.text = '한 번만 &amp;gamma;';
  encoded.cards.medications[1].contraindication.text = '&lt;img src=x onerror=alert(1)&gt; &lt;script&gt;alert(1)&lt;/script&gt;';
  await page.unroute('**/api/v1/intake-reports');
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: encoded }));
  const dialogs: string[] = [];
  page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.getByText('γ 비교 γ α', { exact: true })).toBeHidden();
  await page.locator('.v11-medicine').nth(1).locator('summary').click();
  await expect(page.getByText('γ 비교 γ α', { exact: true })).toBeVisible();
  await expect(page.getByText('한 번만 &gamma;', { exact: true })).toBeVisible();
  await expect(page.locator('.v11-report')).toContainText('<img src=x onerror=alert(1)> <script>alert(1)</script>');
  await expect(page.locator('.v11-report img, .v11-report script')).toHaveCount(0);
  expect(dialogs).toEqual([]);
});

test('v11 card report emails using only the server-issued token without regenerating the report', async ({ page }) => {
  await page.unroute('**/api/v1/intake-reports');
  let generations = 0;
  await page.route('**/api/v1/intake-reports', route => {
    generations++;
    return route.fulfill({ json: { ...report, emailToken: 'v11-card-snapshot' } });
  });
  let emailRequests = 0;
  await page.route('**/api/v1/intake-reports/email', route => {
    emailRequests++;
    expect(route.request().postDataJSON()).toEqual({ emailToken: 'v11-card-snapshot' });
    return route.fulfill({ status: 202, json: { jobId: 51, status: 'QUEUED' } });
  });
  await page.route('**/api/v1/intake-reports/email/51', route => route.fulfill({ json: { jobId: 51, status: 'COMPLETED' } }));

  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '함께 확인할 주의사항' })).toBeVisible();
  expect(generations).toBe(1);
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await expect(page.getByRole('button', { name: '이메일 발송 완료' })).toBeDisabled();
  await expect(page.getByText('메일 서버로 발송했어요. 받은편지함과 스팸함을 확인해주세요.')).toBeVisible();
  expect(emailRequests).toBe(1);
  expect(generations).toBe(1);
});
