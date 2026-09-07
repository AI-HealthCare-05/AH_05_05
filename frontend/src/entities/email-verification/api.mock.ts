import { ApiError } from '@/shared/api/client';
import type { EmailVerificationRequestResult, EmailVerificationResult } from './types';

const MOCK_CODE = '123456';
let nextVerificationId = 1;
const verificationEmails = new Map<number, string>();

export function mockRequestEmailVerification(email: string): EmailVerificationRequestResult {
  const verificationId = nextVerificationId++;
  verificationEmails.set(verificationId, email.trim().toLowerCase());
  return { verificationId, expiresIn: 180, resendAvailableIn: 60 };
}

export function mockVerifyEmailCode(
  verificationId: number,
  code: string,
): EmailVerificationResult {
  const email = verificationEmails.get(verificationId);
  if (!email || code !== MOCK_CODE) {
    throw new ApiError(
      400,
      'INVALID_EMAIL_VERIFICATION_CODE',
      '인증번호를 확인해주세요.',
      'code',
    );
  }
  return {
    verificationToken: `mock-email-verification:${verificationId}:${email}`,
    expiresIn: 600,
  };
}
