/**
 * 관리자 화면 공통 API 계층.
 *
 * FastAPI 가 app.mount("/", StaticFiles(...)) 로 이 파일들을 직접 서빙하므로
 * 화면과 API 가 같은 출처다. CORS 설정도 credentials:"include" 도 필요 없고,
 * admin_refresh_token 쿠키(HttpOnly, 경로 /api/v1/admin/auth)는 자동 전송된다.
 */

const API_BASE = "/api/v1";
const LOGIN_PAGE = "login.html";

const ACCESS_TOKEN_KEY = "adminAccessToken";
const ADMIN_KEY = "adminProfile";

/* ------------------------------------------------------------------ 세션 */

/**
 * 토큰은 sessionStorage 에 둔다.
 *
 * 화면 전환이 페이지 이동(login.html -> user-management.html)이라 메모리에 두면 날아간다.
 * localStorage 는 탭을 닫아도 남아 공용 PC 에서 위험하므로 쓰지 않는다.
 */
export const session = {
  save(accessToken, admin) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    window.sessionStorage.setItem(ADMIN_KEY, JSON.stringify(admin ?? {}));
  },
  saveToken(accessToken) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  },
  token() {
    return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
  },
  /** 로그인 응답의 admin 객체. 권한 분기(role)와 헤더 표시에 쓴다. */
  admin() {
    try {
      return JSON.parse(window.sessionStorage.getItem(ADMIN_KEY) ?? "{}");
    } catch {
      return {};
    }
  },
  isAdminRole() {
    return session.admin().role === "ADMIN";
  },
  clear() {
    window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    window.sessionStorage.removeItem(ADMIN_KEY);
    // 기존 화면이 쓰던 불린 플래그. 남아 있으면 로그인한 것처럼 보인다.
    window.sessionStorage.removeItem("adminAuthenticated");
  },
};

export function redirectToLogin() {
  session.clear();
  window.location.href = LOGIN_PAGE;
}

/* ------------------------------------------------------------------ 에러 */

/**
 * 관리자 API 실패 응답({code, message}, 검증 오류엔 field 추가)을 담는다.
 *
 * 화면은 message 를 그대로 표시하고, 분기가 필요한 곳만 code 로 판단한다.
 * message 문자열을 조건문에 쓰면 문구가 바뀔 때 화면이 조용히 깨진다.
 */
export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message ?? body?.detail ?? "요청을 처리하지 못했습니다.");
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? null;
    this.field = body?.field ?? null;
  }
}

async function readBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ 요청 */

function withAuth(options) {
  const headers = new Headers(options.headers ?? {});
  const token = session.token();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return { ...options, headers };
}

/** 액세스 토큰을 재발급한다. 리프레시 쿠키는 브라우저가 자동으로 보낸다. */
async function refreshAccessToken() {
  const response = await fetch(`${API_BASE}/admin/auth/refresh`, { method: "POST" });
  if (!response.ok) return false;
  const body = await readBody(response);
  if (!body?.accessToken) return false;
  session.saveToken(body.accessToken);
  return true;
}

/**
 * 인증이 필요한 요청을 보낸다.
 *
 * 액세스 토큰이 30분이라 화면을 조금만 켜둬도 만료된다. 401 이 오면 갱신을 한 번
 * 시도하고 원 요청을 재시도한다. **재시도는 1회만** 한다 — 갱신 후에도 401 이면
 * 다시 갱신하러 가면서 무한 루프가 된다.
 */
export async function request(path, options = {}) {
  const url = path.startsWith("/api/") ? path : `${API_BASE}${path}`;

  let response = await fetch(url, withAuth(options));

  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      redirectToLogin();
      throw new ApiError(401, { code: "UNAUTHORIZED", message: "다시 로그인해 주세요." });
    }
    response = await fetch(url, withAuth(options));
    if (response.status === 401) {
      redirectToLogin();
      throw new ApiError(401, { code: "UNAUTHORIZED", message: "다시 로그인해 주세요." });
    }
  }

  const body = await readBody(response);
  if (!response.ok) throw new ApiError(response.status, body);
  return body;
}

export function get(path, params) {
  const query = params ? `?${buildQuery(params)}` : "";
  return request(`${path}${query}`);
}

export function post(path, payload) {
  return request(path, { method: "POST", body: JSON.stringify(payload ?? {}) });
}

export function patch(path, payload) {
  return request(path, { method: "PATCH", body: JSON.stringify(payload ?? {}) });
}

/** 빈 값은 쿼리에서 뺀다. status="" 를 그대로 보내면 422 가 난다. */
export function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.set(key, String(value));
  });
  return search.toString();
}

/* ------------------------------------------------ 화면 표기 ↔ API 값 변환 */

/**
 * 화면은 한글로 보여주고 API 에는 enum 을 보낸다.
 * 회원·관리자 화면이 같은 표를 쓴다.
 */
const STATUS_LABELS = {
  ACTIVE: "활성",
  SUSPENDED: "정지",
  PENDING: "대기",
  WITHDRAWN: "탈퇴",
};

const ROLE_LABELS = {
  ADMIN: "최고 관리자",
  STAFF: "일반 관리자",
};

export function statusLabel(value) {
  return STATUS_LABELS[value] ?? value ?? "";
}

export function statusValue(label) {
  if (!label || label === "전체") return "";
  return Object.keys(STATUS_LABELS).find((key) => STATUS_LABELS[key] === label) ?? "";
}

export function roleLabel(value) {
  return ROLE_LABELS[value] ?? value ?? "";
}

export function roleValue(label) {
  if (!label || label === "전체") return "";
  return Object.keys(ROLE_LABELS).find((key) => ROLE_LABELS[key] === label) ?? "";
}

/** 상태 배지 CSS 클래스. 기존 화면이 active/stopped 두 가지만 쓴다. */
export function statusBadgeClass(value) {
  return value === "ACTIVE" ? "active" : "stopped";
}

/** ISO datetime -> 화면 표기(2024.11.02). 기존 목 데이터 형식을 유지한다. */
export function formatDate(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}.${month}.${day}`;
}

/* ------------------------------------------------------------ 화면 상태 */

/**
 * 표 본문에 로딩·빈 결과·실패를 표시한다.
 *
 * 목 데이터일 때는 항상 데이터가 있어서 이 상태들이 없었다.
 */
export const tableState = {
  loading(tbody, colspan, message = "불러오는 중…") {
    tbody.innerHTML = `<tr><td class="empty-row" colspan="${colspan}">${message}</td></tr>`;
  },
  empty(tbody, colspan, message = "결과가 없습니다.") {
    tbody.innerHTML = `<tr><td class="empty-row" colspan="${colspan}">${message}</td></tr>`;
  },
  error(tbody, colspan, message) {
    tbody.innerHTML =
      `<tr><td class="empty-row" colspan="${colspan}">${escapeHtml(message)} ` +
      `<button type="button" class="ui-link-button" data-retry>다시 시도</button></td></tr>`;
  },
};

/** 사용자 입력이 그대로 innerHTML 에 들어가지 않게 막는다. */
export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** 로그인하지 않은 채 열린 화면을 로그인으로 돌려보낸다. */
export function requireLogin() {
  if (!session.token()) {
    redirectToLogin();
    return false;
  }
  return true;
}
