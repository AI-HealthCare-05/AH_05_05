/**
 * API 클라이언트. 화면(pages/features)은 이 파일을 직접 쓰지 않습니다.
 * entities/&#42;/api.ts 만 여기를 쓰고, 화면은 그 함수를 부릅니다.
 * 그래서 목업 → 실서버 전환이 화면 코드를 건드리지 않습니다.
 *
 * 인증: 노션 API 명세 0장 — 로그인 후 모든 요청에
 * `Authorization: Bearer <accessToken>`. 리프레시 토큰 쿠키도 함께 전송합니다.
 */
import { API_BASE_URL } from '@/shared/config/env';
import { isSessionIdle, endActivitySession, ownsActivitySession, beginActivitySession } from './sessionActivity';
import { withAuthCookieLock } from './authCookieLock';

const ACCESS_TOKEN_STORAGE_KEY = 'poke.access-token';
const ACCOUNT_PRINCIPAL_STORAGE_KEY = 'poke.account-principal';
export const AUTH_SESSION_EXPIRED_EVENT = 'poke:auth-session-expired';

let accessToken: string | null = null;
let accountPrincipal: string | null = null;
let authGeneration = 0;

export function setAccessToken(token: string | null): void {
  authGeneration += 1;
  persistAccessToken(token);
}

// Refresh replaces credentials within the same session, not its identity/generation.
function persistAccessToken(token: string | null): void {
  accessToken = token;
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
  const decoded = accessTokenClaims(token);
  return typeof decoded?.exp === 'number' && Number.isFinite(decoded.exp) ? decoded.exp * 1000 : null;
}

export function accessTokenSessionId(token: string): string | null {
  const id = accessTokenClaims(token)?.session_id;
  return typeof id === 'string' && id ? id : null;
}

function accessTokenClaims(token: string): { exp?: unknown; session_id?: unknown } | null {
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const base64 = payload.replaceAll('-', '+').replaceAll('_', '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    return JSON.parse(atob(padded)) as { exp?: unknown; session_id?: unknown };
  } catch {
    return null;
  }
}

export function expireSession(requestGeneration?: number): void {
  if (requestGeneration !== undefined && requestGeneration !== authGeneration) return;
  if (!restoreAccessToken() && !restoreAccountPrincipal()) return;
  const principal = restoreAccountPrincipal();
  if (principal) endActivitySession(principal);
  setAccessToken(null);
  setAccountPrincipal(null);
  window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
}

let refreshInFlight: { generation: number; promise: Promise<void> } | null = null;
let logoutInFlight: Promise<void> | null = null;

function assertActiveSession(generation: number): void {
  if (generation !== authGeneration) throw new ApiError(401, 'SESSION_CHANGED', '로그인 상태가 변경되었어요.');
  const principal = restoreAccountPrincipal();
  if (!restoreAccessToken() || !principal || isSessionIdle(principal)) {
    expireSession(generation);
    throw new ApiError(401, 'SESSION_EXPIRED', '30분 동안 활동이 없어 로그아웃되었어요.');
  }
}

/** One refresh per tab/session. Network failures retain the session; invalid credentials do not. */
export function refreshAccessToken(): Promise<void> {
  const generation = getAuthGeneration();
  try { assertActiveSession(generation); } catch (error) { return Promise.reject(error); }
  if (refreshInFlight?.generation === generation) return refreshInFlight.promise;
  const promise = (async () => {
    const res = await fetch(`${API_BASE_URL}/v1/auth/token/refresh`, {
      credentials: 'include', headers: authHeader(), cache: 'no-store',
      signal: AbortSignal.timeout(10_000),
    });
    assertActiveSession(generation);
    if (!res.ok) {
      if ([400, 401, 403, 404].includes(res.status)) expireSession(generation);
      throw await toApiError(res);
    }
    const body = await res.json() as { access_token?: unknown };
    assertActiveSession(generation);
    if (typeof body.access_token !== 'string' || !body.access_token) {
      throw new ApiError(502, 'INVALID_REFRESH_RESPONSE', '로그인을 갱신하지 못했어요. 잠시 후 다시 시도해주세요.');
    }
    persistAccessToken(body.access_token);
  })().finally(() => {
    if (refreshInFlight?.promise === promise) refreshInFlight = null;
  });
  refreshInFlight = { generation, promise };
  return promise;
}

/** Clear local state immediately, even when cookie cleanup is offline or slow. */
export function endSession(): Promise<void> {
  if (logoutInFlight) return logoutInFlight;
  const headers = authHeader();
  const principal = restoreAccountPrincipal();
  expireSession();
  const promise = (async () => {
    try {
      await withAuthCookieLock(async () => {
        // A suspended old tab must not clear the cookie reused by a newer login.
        if (principal && !ownsActivitySession(principal)) return;
        await fetch(`${API_BASE_URL}/v1/auth/logout`, {
          method: 'POST', credentials: 'include', headers, signal: AbortSignal.timeout(5_000),
        });
      });
    } catch {
      // A failed cleanup must never restore the local session or block logout.
    }
  })().finally(() => { if (logoutInFlight === promise) logoutInFlight = null; });
  logoutInFlight = promise;
  return promise;
}

async function fetchWithSession(path: string, init: RequestInit): Promise<Response> {
  // Do not let a late logout Set-Cookie delete the next login's cookie in this tab.
  if (path === '/v1/auth/login' && logoutInFlight) await logoutInFlight;
  const generation = getAuthGeneration();
  const protectedRequest = !path.startsWith('/v1/auth/') && Boolean(restoreAccessToken());
  if (protectedRequest) {
    assertActiveSession(generation);
    const expiresAt = accessTokenExpiresAt(restoreAccessToken()!);
    if (expiresAt !== null && expiresAt <= Date.now() + 30_000) await refreshAccessToken();
    assertActiveSession(generation);
  }
  const send = () => fetch(`${API_BASE_URL}${path}`, {
    ...init, credentials: 'include', headers: { ...init.headers, ...authHeader() },
    ...(path === '/v1/auth/login' ? { signal: AbortSignal.timeout(10_000) } : {}),
  });
  const sentToken = restoreAccessToken();
  let res = path === '/v1/auth/login' ? await withAuthCookieLock(async () => {
    const response = await send();
    if (response.ok && typeof init.body === 'string') {
      const payload = JSON.parse(init.body) as { email?: string };
      const body = await response.clone().json() as { access_token?: string };
      const principal = payload.email?.trim().toLowerCase();
      if (principal && typeof body.access_token === 'string' && body.access_token) {
        // Commit the new local epoch before releasing the cookie lock to waiting old tabs.
        setAccessToken(body.access_token);
        setAccountPrincipal(principal);
        beginActivitySession(principal, accessTokenSessionId(body.access_token));
      }
    }
    return response;
  }) : await send();
  if (protectedRequest) assertActiveSession(generation);
  if (res.status === 401 && protectedRequest) {
    // Another request may already have refreshed this exact rejected token.
    if (sentToken === restoreAccessToken()) await refreshAccessToken();
    assertActiveSession(generation);
    res = await send();
    assertActiveSession(generation);
    if (res.status === 401) expireSession(generation);
  }
  return res;
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
  const isFormData = body instanceof FormData;
  const res = await fetchWithSession(path, {
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
    throw await toApiError(res);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const res = await fetchWithSession(path, {
    method: 'GET',
    credentials: 'include',
    headers: authHeader(),
  });
  if (!res.ok) {
    throw await toApiError(res);
  }
  return res.blob();
}

async function requestStream(
  path: string,
  body: unknown,
): Promise<Response> {
  const res = await fetchWithSession(path, {
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
