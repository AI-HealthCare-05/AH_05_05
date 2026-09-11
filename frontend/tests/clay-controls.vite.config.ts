import { defineConfig, mergeConfig } from 'vite';
import baseConfig from '../vite.config';

export default defineConfig((env) => mergeConfig(baseConfig(env), {
  // Kept inside this worktree, with node_modules in the path so Vite treats
  // optimized dependencies as dependencies. The shared install stays untouched.
  cacheDir: '.codex-work/clay-controls/node_modules/.vite',
  server: { proxy: { '/api': { target: 'http://127.0.0.1:9' }, '/media': { target: 'http://127.0.0.1:9' } } },
}));
