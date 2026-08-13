/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API 기본 경로. 비우면 '/api'(vite 프록시)를 씁니다. */
  readonly VITE_API_BASE_URL?: string;
  /** 'false' 일 때만 실제 서버를 호출합니다. 그 외에는 목업. */
  readonly VITE_USE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
