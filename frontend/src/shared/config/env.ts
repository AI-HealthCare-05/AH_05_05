/**
 * 실행 환경 설정. 여기 말고 다른 곳에서 import.meta.env를 직접 읽지 마세요.
 * 값이 흩어지면 "지금 목업인지 실서버인지"를 한 곳에서 알 수 없게 됩니다.
 *
 * .env.example 을 .env.local 로 복사해서 값을 바꿉니다(.env.local 은 커밋하지 않습니다).
 */

/**
 * API 기본 경로. 기본값 '/api' 는 vite dev 서버의 프록시를 타고 백엔드로 갑니다.
 * 프록시를 쓰면 브라우저 입장에서 같은 출처라 CORS 설정이 필요 없습니다.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api';

/**
 * true면 네트워크를 타지 않고 entities/&#42;/api.mock.ts 의 고정 데이터를 돌려줍니다.
 * 백엔드가 준비된 엔드포인트부터 하나씩 붙이려면 .env.local 에 VITE_USE_MOCK=false 를
 * 넣고, 아직 안 된 엔드포인트는 각 api.ts 의 USE_MOCK 분기를 개별로 남겨두면 됩니다.
 */
export const USE_MOCK: boolean = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false';

/** Web Push 구독 생성에 쓰는 VAPID 공개키. 개인키는 프론트에 두지 않습니다. */
export const VAPID_PUBLIC_KEY: string = import.meta.env.VITE_VAPID_PUBLIC_KEY ?? '';
