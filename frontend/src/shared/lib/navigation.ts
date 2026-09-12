import type { NavigateFunction } from 'react-router';

export function navigateBackOrReplace(
  navigate: NavigateFunction,
  fallback: string,
  canUseHistory = true,
): void {
  const index = typeof window === 'undefined' ? undefined : window.history.state?.idx;
  if (canUseHistory && typeof index === 'number' && index > 0) {
    navigate(-1);
    return;
  }
  navigate(fallback, { replace: true });
}

export function trustedBackTarget(
  state: unknown,
  allowedTargets: readonly string[],
): string | null {
  if (state === null || typeof state !== 'object' || !('returnTo' in state)) return null;
  const returnTo = (state as { returnTo?: unknown }).returnTo;
  return typeof returnTo === 'string' && allowedTargets.includes(returnTo) ? returnTo : null;
}
