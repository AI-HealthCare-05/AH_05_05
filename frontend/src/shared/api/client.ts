/**
 * API 클라이언트. 화면(pages/features)은 이 파일을 직접 쓰지 않습니다.
 * entities/&#42;/api.ts 만 여기를 쓰고, 화면은 그 함수를 부릅니다.
 * 그래서 목업 → 실서버 전환이 화면 코드를 건드리지 않습니다.
 *
 * 인증: 노션 API 명세 0장 — 로그인 후 모든 요청에
 * `Authorization: Bearer <accessToken>`. 리프레시 토큰 쿠키도 함께 전송합니다.
 */
import { API_BASE_URL } from '@/shared/config/env';

const ACCESS_TOKEN_STORAGE_KEY = 'poke.access-token';
const ACCOUNT_PRINCIPAL_STORAGE_KEY = 'poke.account-principal';
export const AUTH_SESSION_EXPIRED_EVENT = 'poke:auth-session-expired';

let accessToken: string | null = null;
let accountPrincipal: string | null = null;
let authGeneration = 0;

export function setAccessToken(token: string | null): void {
  accessToken = token;
  authGeneration += 1;
  try {
    if (token) sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
    else sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    // 저장소를 사용할 수 없는 환경에서는 현재 탭 메모리의 토큰만 사용합니다.
  }
}

export function setAccountPrincipal(principal: string | null): void {
  accountPrincipal = principal?.trim().toLowerCase() || null;
  authGeneration += 1;
  try {
    if (accountPrincipal) sessionStorage.setItem(ACCOUNT_PRINCIPAL_STORAGE_KEY, accountPrincipal);
    else sessionStorage.removeItem(ACCOUNT_PRINCIPAL_STORAGE_KEY);
  } catch {
    // 저장소를 사용할 수 없는 환경에서는 현재 탭 메모리의 주체만 사용합니다.
  }
}

export function restoreAccountPrincipal(): string | null {
  if (accountPrincipal) return accountPrincipal;
  try {
    accountPrincipal = sessionStorage.getItem(ACCOUNT_PRINCIPAL_STORAGE_KEY);
  } catch {
    accountPrincipal = null;
  }
  return accountPrincipal;
}

export function getAuthGeneration(): number {
  return authGeneration;
}

export function restoreAccessToken(): string | null {
  if (accessToken) return accessToken;
  try {
    accessToken = sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    accessToken = null;
  }
  return accessToken;
}

export function authHeader(): Record<string, string> {
  const token = restoreAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** JWT의 exp(초)를 브라우저 시간(밀리초)으로 변환합니다. JWT가 아니면 서버의 401에 맡깁니다. */
export function accessTokenExpiresAt(token: string): number | null {
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const base64 = payload.replaceAll('-', '+').replaceAll('_', '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const decoded = JSON.parse(atob(padded)) as { exp?: unknown };
    return typeof decoded.exp === 'number' && Number.isFinite(decoded.exp)
      ? decoded.exp * 1000
      : null;
  } catch {
    return null;
  }
}

function expireSession(requestGeneration?: number): void {
  if (requestGeneration !== undefined && requestGeneration !== authGeneration) return;
  if (!restoreAccessToken() && !restoreAccountPrincipal()) return;
  setAccessToken(null);
  setAccountPrincipal(null);
  window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
}

function handleUnauthorized(res: Response, requestGeneration: number): void {
  if (res.status === 401) expireSession(requestGeneration);
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
  readonly detail?: unknown;

  constructor(status: number, code: string, message: string, field?: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.field = field;
    this.detail = detail;
  }
}

/** 서버가 오류 본문을 못 주거나 형식이 다를 때 화면에 띄울 기본 문구. */
const FALLBACK_MESSAGE = '일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.';

async function toApiError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = FALLBACK_MESSAGE;
  let field: string | undefined;
  let detail: unknown;
  try {
    const body = (await res.json()) as {
      code?: string;
      message?: string;
      detail?: unknown;
      field?: string;
    };
    if (body.code) code = body.code;
    if (body.message) message = body.message;
    detail = body.detail;
    if (body.field) field = body.field;
  } catch {
    // 본문이 JSON이 아니면 기본 문구를 씁니다.
  }
  if (import.meta.env.DEV && detail !== undefined) {
    console.warn('API error detail:', detail);
  }
  return new ApiError(res.status, code, message, field, detail);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  additionalHeaders: Record<string, string> = {},
): Promise<T> {
  const requestGeneration = getAuthGeneration();
  const isFormData = body instanceof FormData;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    credentials: 'include',
    headers: {
      ...authHeader(),
      ...additionalHeaders,
      // FormData 는 boundary 를 브라우저가 붙여야 해서 Content-Type 을 직접 지정하지 않습니다.
      ...(body !== undefined && !isFormData ? { 'Content-Type': 'application/json' } : {}),
    },
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    handleUnauthorized(res, requestGeneration);
    throw await toApiError(res);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const requestGeneration = getAuthGeneration();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    credentials: 'include',
    headers: authHeader(),
  });
  if (!res.ok) {
    handleUnauthorized(res, requestGeneration);
    throw await toApiError(res);
  }
  return res.blob();
}

async function requestStream(
  path: string,
  body: unknown,
): Promise<Response> {
  const requestGeneration = getAuthGeneration();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...authHeader(),
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    handleUnauthorized(res, requestGeneration);
    throw await toApiError(res);
  }
  return res;
}

export const http = {
  get: <T>(path: string) => request<T>('GET', path),
  getBlob: (path: string) => requestBlob(path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>('POST', path, body, headers),
  postStream: (path: string, body: unknown) => requestStream(path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string, body?: unknown) => request<T>('DELETE', path, body),
};
