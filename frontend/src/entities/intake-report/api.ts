import { ApiError, http } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import type { IntakeReport, IntakeReportEmailJob } from './types';

export async function generateIntakeReport(): Promise<IntakeReport> {
  if (USE_MOCK) {
    throw new ApiError(0, 'REPORT_REAL_API_REQUIRED', '보고서 생성은 실제 서비스 연결 상태에서 사용할 수 있어요.');
  }
  // The server resolves scope from authentication, never a client userId or prompt.
  return http.post<IntakeReport>('/v1/intake-reports', {});
}

export function emailIntakeReport(emailToken: string): Promise<IntakeReportEmailJob> {
  return http.post<IntakeReportEmailJob>('/v1/intake-reports/email', { emailToken });
}

export function getIntakeReportEmailJob(jobId: number): Promise<IntakeReportEmailJob> {
  return http.get<IntakeReportEmailJob>(`/v1/intake-reports/email/${jobId}`);
}
