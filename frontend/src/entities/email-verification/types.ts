export interface EmailVerificationRequestResult {
  verificationId: number;
  expiresIn: number;
  resendAvailableIn: number;
}

export interface EmailVerificationResult {
  verificationToken: string;
  expiresIn: number;
}
