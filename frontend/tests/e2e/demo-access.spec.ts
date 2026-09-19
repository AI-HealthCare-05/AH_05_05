import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

test('demo report asks for recipient and confirms one send', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'demo-test-token');
    sessionStorage.setItem('poke.account-principal', 'demo_tester@rxvita.p-e.kr');
    sessionStorage.setItem('rxvita.demo-principal', 'demo_tester@rxvita.p-e.kr');
  });
  await page.route('**/api/v1/**', route => route.fulfill({ json: {} }));
  await page.route('**/api/v1/intake-reports', route => route.fulfill({ json: {
    reportStatus: 'COMPLETED', generatedAt: '2026-09-19T00:00:00Z', emailToken: 'snapshot',
    presentationVersion: 'ai-report-v2', dataAvailability: { activeMedicationCount: 0, activeSupplementCount: 1 },
    executiveSummary: { reviewedProductCount: 1, summaryCards: [] }, currentStack: [], reviewCards: [],
    nutrientTotals: [], productGuides: [], unverifiedItems: [], chartData: {}, reportMarkdown: '# 보고서',
  } }));
  let requests = 0;
  await page.route('**/api/v1/intake-reports/email', async route => {
    requests++;
    expect(route.request().postDataJSON()).toEqual({ emailToken: 'snapshot', recipientEmail: 'visitor@example.com' });
    await new Promise(resolve => setTimeout(resolve, 150));
    await route.fulfill({ status: 202, json: { jobId: 41, status: 'QUEUED' } });
  });
  await page.goto('/reports/new?source=supplements');
  await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('[데모버전] 이메일 받을 주소를 입력하세요:');
  await page.getByRole('button', { name: '취소', exact: true }).click();
  expect(requests).toBe(0);
  await page.getByRole('button', { name: '이메일로 받기', exact: true }).click();
  await page.getByLabel('[데모버전] 이메일 받을 주소를 입력하세요:').fill('visitor@example.com');
  await page.getByRole('button', { name: '확인', exact: true }).dblclick();
  await expect(page.getByText('발송 요청이 접수됐어요. 아직 발송이 완료되지는 않았어요.')).toBeVisible();
  expect(requests).toBe(1);
});

test('demo login runs once and badge survives reload', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/**', route => route.fulfill({ json: {} }));
  await page.route('**/api/v1/auth/demo-login', route => {
    requests++;
    return route.fulfill({ json: { access_token: 'demo-test-token', email: 'demo_tester@rxvita.p-e.kr' } });
  });
  await page.goto('/demo');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText('[데모 버전]', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('[데모 버전]', { exact: true })).toBeVisible();
  expect(requests).toBe(1);
});

test('demo profile buttons show notice without opening destructive forms', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'demo-test-token');
    sessionStorage.setItem('poke.account-principal', 'demo_tester@rxvita.p-e.kr');
  });
  await page.route('**/api/v1/**', route => route.fulfill({ json: {} }));
  await page.route('**/api/v1/users/me', route => route.fulfill({ json: {
    name: '데모', maskedName: '데모', email: 'demo_tester@rxvita.p-e.kr',
    phoneNumber: '01012345678', birthDate: '1990-01-01', gender: 'MALE',
  } }));
  await page.goto('/my/profile');
  await page.getByRole('button', { name: '비밀번호 변경', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('데모버전에서는 기능을 지원하지 않습니다.');
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '회원 탈퇴', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('데모버전에서는 기능을 지원하지 않습니다.');
});
