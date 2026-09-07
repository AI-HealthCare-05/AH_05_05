import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockRequestEmailVerification, mockVerifyEmailCode } from './api.mock';
import type { EmailVerificationRequestResult, EmailVerificationResult } from './types';

interface RequestResponseBody {
  verification_id: number;
  expires_in: number;
  resend_available_in: number;
}

interface VerifyResponseBody {
  verification_token: string;
  expires_in: number;
}

export async function requestEmailVerification(
  email: string,
): Promise<EmailVerificationRequestResult> {
  const normalizedEmail = email.trim().toLowerCase();
  if (USE_MOCK) {
    await mockDelay();
    return mockRequestEmailVerification(normalizedEmail);
  }
  const body = await http.post<RequestResponseBody>('/v1/auth/email-verifications', {
    email: normalizedEmail,
  });
  return {
    verificationId: body.verification_id,
    expiresIn: body.expires_in,
    resendAvailableIn: body.resend_available_in,
  };
}

export async function verifyEmailCode(
  verificationId: number,
  code: string,
): Promise<EmailVerificationResult> {
  if (USE_MOCK) {
    await mockDelay();
    return mockVerifyEmailCode(verificationId, code);
  }
  const body = await http.post<VerifyResponseBody>(
    `/v1/auth/email-verifications/${verificationId}/verify`,
    { code },
  );
  return {
    verificationToken: body.verification_token,
    expiresIn: body.expires_in,
  };
}
