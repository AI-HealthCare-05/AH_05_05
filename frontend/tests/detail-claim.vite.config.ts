import { defineConfig, mergeConfig } from 'vite';
import appConfig from '../vite.config';

export default defineConfig(async env => mergeConfig(
  await (typeof appConfig === 'function' ? appConfig(env) : appConfig),
  { cacheDir: 'node_modules/.vite-custom-detail-claim315' },
));
