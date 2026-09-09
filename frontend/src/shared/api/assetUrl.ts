import { API_BASE_URL } from '@/shared/config/env';

const ABSOLUTE_HTTP_URL = /^https?:\/\//i;

export function apiAssetUrl(path: string): string {
  if (ABSOLUTE_HTTP_URL.test(path)) return path;

  const rootedPath = `/${path.replace(/^\/+/, '')}`;
  if (!ABSOLUTE_HTTP_URL.test(API_BASE_URL)) return rootedPath;

  return new URL(rootedPath, API_BASE_URL).toString();
}
