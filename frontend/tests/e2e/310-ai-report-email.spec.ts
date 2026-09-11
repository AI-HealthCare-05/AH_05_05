import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(60_000);
const report = {
  reportStatus: 'COMPLETED', generatedAt: '2026-09-11T00:00:00Z', emailToken: 'server-issued-snapshot',
  presentationVersion: 'ai-report-v2',
  dataAvailability: { activeMedicationCount: 1, activeSupplementCount: 0 },
  executiveSummary: { reviewedProductCount: 1, summaryCards: [] },
  currentStack: [], reviewCards: [], nutrientTotals: [], productGuides: [], unverifiedItems: [], chartData: {},
  reportMarkdown: '# 테스트 복용 보고서\n\n현재 표시된 보고서 본문입니다.\n\n| 제품 | 안내 |\n| --- | --- |\n| 긴한글제품명 테스트 | 전문가와 확인하세요. |',
};
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'email-ui-test-token');
    sessionStorage.setItem('poke.account-principal', 'email-ui@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.route('**/api/v1/**', route => route.fulfill({ json: {} }));
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: report }));
});

test('explicit send uses only server token, prevents duplicates and distinguishes queue from delivery', async ({ page }, info) => {
  let requests = 0;
  let completed = false;
  await page.route('**/api/v1/intake-reports/email', async route => {
    requests++;
    expect(route.request().postDataJSON()).toEqual({ emailToken: report.emailToken });
    await new Promise(resolve => setTimeout(resolve, 250));
    await route.fulfill({ status: 202, json: { jobId: 41, status: 'QUEUED' } });
  });
  await page.route('**/api/v1/intake-reports/email/41', route => route.fulfill({ json: { jobId: 41, status: completed ? 'COMPLETED' : 'PROCESSING' } }));
  await page.setViewportSize({ width: 320, height: 812 });
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  const send = page.getByRole('button', { name: '이메일로 받기', exact: true });
  await expect(send).toBeEnabled();
  expect(requests).toBe(0);
  await send.evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole('button', { name: '이메일 요청 중' })).toBeDisabled();
  await expect(page.getByText('발송 요청이 접수됐어요. 아직 발송이 완료되지는 않았어요.')).toBeVisible();
  expect(requests).toBe(1);
  await page.getByRole('button', { name: '이메일 발송 처리 중' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath('email-queued-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  completed = true;
  await expect(page.getByRole('button', { name: '이메일 발송 완료' })).toBeDisabled();
  await expect(page.getByText('메일 서버로 발송했어요. 받은편지함과 스팸함을 확인해주세요.')).toBeVisible();
  expect(requests).toBe(1);
});

test('request failure can retry safely and worker failure is visible', async ({ page }) => {
  let requests = 0;
  let generations = 0;
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: { ...report, emailToken: `snapshot-${++generations}` } }));
  await page.route('**/api/v1/intake-reports/email', route => {
    requests++;
    return requests === 1
      ? route.fulfill({ status: 503, json: { code: 'EMAIL_UNAVAILABLE', message: '메일 요청을 처리하지 못했어요.' } })
      : route.fulfill({ status: 202, json: { jobId: 42, status: 'QUEUED' } });
  });
  await page.route('**/api/v1/intake-reports/email/42', route => route.fulfill({ json: { jobId: 42, status: 'FAILED' } }));
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('메일 요청을 처리하지 못했어요.');
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('이메일을 발송하지 못했어요.');
  expect(requests).toBe(2);
  await page.getByRole('button', { name: '새 보고서 생성하기', exact: true }).click();
  await expect(page.getByRole('button', { name: '이메일로 받기', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await expect(page.getByText('발송 요청이 접수됐어요. 아직 발송이 완료되지는 않았어요.')).toBeVisible();
  expect(generations).toBe(2);
  expect(requests).toBe(3);
});

test('status lookup failure offers status-only retry without resending', async ({ page }) => {
  let sends = 0;
  let checks = 0;
  await page.route('**/api/v1/intake-reports/email', route => {
    sends++;
    return route.fulfill({ status: 202, json: { jobId: 43, status: 'QUEUED' } });
  });
  await page.route('**/api/v1/intake-reports/email/43', route => {
    checks++;
    return route.fulfill(checks === 1 ? { status: 503, json: {} } : { json: { jobId: 43, status: 'COMPLETED' } });
  });
  await page.goto('/reports/new?source=medications');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await page.getByRole('button', { name: '발송 상태 확인', exact: true }).click();
  await expect(page.getByRole('button', { name: '이메일 발송 완료' })).toBeDisabled();
  expect(sends).toBe(1);
});
