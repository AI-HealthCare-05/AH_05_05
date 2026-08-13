/**
 * API 클라이언트. 화면(pages/features)은 이 파일을 직접 쓰지 않습니다.
 * entities/&#42;/api.ts 만 여기를 쓰고, 화면은 그 함수를 부릅니다.
 * 그래서 목업 → 실서버 전환이 화면 코드를 건드리지 않습니다.
 *
 * 인증: 노션 API 명세 0장 — 로그인 후 모든 요청에
 * `Authorization: Bearer <accessToken>`. 쿠키는 쓰지 않습니다.
 */
import { API_BASE_URL } from '@/shared/config/env';

// 로그인 화면(REQ-USER-002)이 붙기 전까지 쓰는 고정값.
// 로그인이 붙으면 setAccessToken()으로 교체하고 이 상수는 지웁니다.
const DEV_ACCESS_TOKEN = 'dev-fixed-token';

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function authHeader(): Record<string, string> {
  return { Authorization: `Bearer ${accessToken ?? DEV_ACCESS_TOKEN}` };
}

/** 목업이 네트워크 지연을 흉내내어 로딩 상태를 확인할 수 있게 합니다. */
export function mockDelay(ms = 400): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 서버 오류를 화면이 항상 같은 모양으로 받도록 정규화합니다.
 * 노션 API 명세 11장에서 백엔드에 요청한 형태: { code, message, field? }
 *
 * field 가 있으면 그 입력칸 아래에 메시지를 붙일 수 있습니다(회원가입 검증 오류 등).
 */
export class ApiError extends Error {
  readonly code: string;
  readonly field?: string;
  readonly status: number;

  constructor(status: number, code: string, message: string, field?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

/** 서버가 오류 본문을 못 주거나 형식이 다를 때 화면에 띄울 기본 문구. */
const FALLBACK_MESSAGE = '일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.';

async function toApiError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = FALLBACK_MESSAGE;
  let field: string | undefined;
  try {
    const body = (await res.json()) as { code?: string; message?: string; field?: string };
    if (body.code) code = body.code;
    if (body.message) message = body.message;
    if (body.field) field = body.field;
  } catch {
    // 본문이 JSON이 아니면 기본 문구를 씁니다.
  }
  return new ApiError(res.status, code, message, field);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isFormData = body instanceof FormData;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      ...authHeader(),
      // FormData 는 boundary 를 브라우저가 붙여야 해서 Content-Type 을 직접 지정하지 않습니다.
      ...(body !== undefined && !isFormData ? { 'Content-Type': 'application/json' } : {}),
    },
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const http = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
};
