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
  expect(await details.locator('summary').evaluate(el => getComputedStyle(el).listStyleType)).toBe('none');
  await details.locator('summary').click();
  await expect(details.locator('.v11-collapse-label [aria-hidden="true"]')).toBeVisible();
  await expect(details.locator('.v11-collapsible-full')).toBeVisible();
  await expect(details.locator('.v11-collapsible-full')).toHaveText(longText);
  await details.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(details.locator('.v11-collapsible-full')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const originals = page.locator('#v11-originals details');
  await expect(originals.locator('.v11-details-body')).toBeHidden();
  await originals.locator('summary').click({ timeout: 3000 });
  await expect(originals.locator('.v11-details-body')).toContainText('제품 안내의 정리 전 원문이에요.');
  await originals.locator('summary').click();
  await page.screenshot({ path: testInfo.outputPath('v11-grouped-collapsed.png'), fullPage: true });
});

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
    await expect(page.getByRole('heading', { name: '영양소는 얼마나 겹칠까요?' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '약 정보' })).toBeVisible();
    await expect(page.getByText('확인된 효능 설명', { exact: true })).toBeVisible();
    await expect(page.getByText('확인된 주의 설명', { exact: true })).toBeVisible();
    await expect(page.getByText('확인된 금기 설명', { exact: true })).toBeVisible();
    await expect(page.getByText('델타 효능', { exact: true })).toBeVisible();
    await expect(page.getByText('확인 필요 제품 · 가상 함량 미확인 제품', { exact: true })).toBeVisible();
    const iron = page.getByRole('heading', { name: '철 함량 미확인' }).locator('..').locator('..');
    await expect(iron.getByText('미확인', { exact: true })).toBeVisible();
    await expect(iron.getByRole('img')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '등록한 영양제 3종' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '상세 보고서' })).toHaveCount(0);
    await expect(page.getByRole('table', { name: '현재 복용 목록' })).toHaveCount(0);
    await expect(page.getByRole('img', { name: '비타민 D 200%' })).toHaveCount(1);
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
  await expect(medicationDetails.getByText('사용자가 등록한 복용 정보', { exact: true })).toBeVisible();
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
