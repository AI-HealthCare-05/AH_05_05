import { defineConfig, mergeConfig } from 'vite';
import baseConfig from '../vite.config';

export default defineConfig((env) => mergeConfig(baseConfig(env), {
  cacheDir: 'test-results/.vite-auth-stagger',
  server: { proxy: { '/api': { target: 'http://127.0.0.1:9' }, '/media': { target: 'http://127.0.0.1:9' } } },
}));
