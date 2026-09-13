import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const require = createRequire(path.join(root, 'package.json'));
const { createServer } = await import(require.resolve('vite'));
const { default: react } = await import(require.resolve('@vitejs/plugin-react'));
const { default: tailwindcss } = await import(require.resolve('@tailwindcss/vite'));
const port = Number(process.env.PLAYWRIGHT_TEST_PORT ?? '45547');

const server = await createServer({
  configFile: false,
  root,
  cacheDir: path.join(root, 'node_modules/.vite-447-controls-cache'),
  plugins: [
    {
      name: '447-fail-closed',
      configureServer(vite) {
        vite.middlewares.use((request, response, next) => {
          if (/^\/(api|media)(\/|$)/.test(request.url ?? '')) {
            response.statusCode = 503;
            response.setHeader('Content-Type', 'application/json');
            response.end(JSON.stringify({ message: '447 test: unhandled API/media request blocked' }));
            return;
          }
          next();
        });
      },
    },
    react(),
    tailwindcss(),
  ],
  define: {
    'import.meta.env.VITE_USE_MOCK': JSON.stringify(process.env.VITE_USE_MOCK ?? 'true'),
    'import.meta.env.VITE_VAPID_PUBLIC_KEY': JSON.stringify(''),
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: { '@': path.join(root, 'src') },
  },
  server: {
    host: '127.0.0.1',
    port,
    strictPort: true,
    watch: null,
    proxy: {},
    fs: { allow: [path.resolve(root, '..')] },
  },
});

await server.listen();
console.log(`447 controls Vite ready http://127.0.0.1:${port}; mock adapters; fail closed; watch null`);

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, async () => {
    await server.close();
    process.exit(0);
  });
}
