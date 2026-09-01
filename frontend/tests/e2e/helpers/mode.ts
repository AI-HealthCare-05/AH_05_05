/** VITE_USE_MOCK=false 로 띄운 실 API 모드인가 */
export const IS_REAL_API = process.env.VITE_USE_MOCK === 'false';

export const MOCK_ONLY_REASON = '이 파일은 목업 픽스처를 검증합니다.';
export const REAL_API_ONLY_REASON = '이 파일은 실 API 계약을 검증합니다.';
