import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/**
 * '/api' 요청을 백엔드(FastAPI)로 넘깁니다. 브라우저 입장에서는 같은 출처라
 * CORS 설정이 필요 없습니다. 백엔드 주소가 다르면 .env.local 에
 * VITE_API_PROXY_TARGET 을 넣으세요.
 */
const DEFAULT_API_PROXY_TARGET = 'http://127.0.0.1:8000';

export default defineConfig(({ mode }) => {
  // loadEnv 로 읽습니다. Vite 는 .env 파일을 process.env 에 넣어주지 않아서
  // process.env.VITE_API_PROXY_TARGET 은 항상 undefined 였고, .env.local 에
  // 무엇을 적든 위 기본값으로만 붙었습니다.
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const API_PROXY_TARGET = env.VITE_API_PROXY_TARGET || DEFAULT_API_PROXY_TARGET;

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: {
        // 경로를 그대로 넘깁니다. 백엔드 라우트가 /api/v1/... 이라 접두사를 떼면 404 가 됩니다.
        '/api': {
          target: API_PROXY_TARGET,
          changeOrigin: true,
        },
      },
    },
  };
});
