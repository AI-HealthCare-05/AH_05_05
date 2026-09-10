import { getAuthGeneration, restoreAccessToken, restoreAccountPrincipal } from '@/shared/api/client';

export interface BadgeAward {
  source: 'official' | 'custom';
  awardId: number | string;
  participationId: number | string;
  name: string;
  imageUrl: string;
}

export interface BadgeAwardScope {
  principalKey: string;
  authGeneration: number;
}

type AwardMemory = { observed: Set<string>; presented: Set<string> };
const seenByAccount = new Map<string, AwardMemory>();
let queue: Array<{ scope: BadgeAwardScope; award: BadgeAward }> = [];
const listeners = new Set<() => void>();
let revision = 0;

function identity(award: BadgeAward) {
  return JSON.stringify([award.source, String(award.awardId), String(award.participationId)]);
}

function isCurrent(scope: BadgeAwardScope | null): scope is BadgeAwardScope {
  return Boolean(scope && restoreAccessToken()
    && scope.authGeneration === getAuthGeneration()
    && scope.principalKey === restoreAccountPrincipal()?.trim().toLowerCase());
}

export function captureBadgeAwardScope(principalKey: string | null): BadgeAwardScope | null {
  const scope = principalKey ? { principalKey: principalKey.trim().toLowerCase(), authGeneration: getAuthGeneration() } : null;
  return isCurrent(scope) ? scope : null;
}

function seen(scope: BadgeAwardScope) {
  let ids = seenByAccount.get(scope.principalKey);
  if (!ids) {
    ids = { observed: new Set<string>(), presented: new Set<string>() };
    seenByAccount.set(scope.principalKey, ids);
  }
  try {
    const stored = JSON.parse(localStorage.getItem(`rxvita.badge-awards.v1:${scope.principalKey}`) ?? '{}') as Record<string, unknown>;
    for (const kind of ['observed', 'presented'] as const) {
      if (Array.isArray(stored?.[kind])) for (const id of stored[kind]) if (typeof id === 'string') ids[kind].add(id);
    }
  } catch { /* Private browsing/storage failures retain this tab's memory dedupe. */ }
  return ids;
}

function save(scope: BadgeAwardScope, ids: AwardMemory) {
  try { localStorage.setItem(`rxvita.badge-awards.v1:${scope.principalKey}`, JSON.stringify({ observed: [...ids.observed], presented: [...ids.presented] })); }
  catch { /* Browser-local convenience, not a server or cross-device exactly-once guarantee. */ }
}

/** Initial historical snapshots are silently remembered, never replayed as new awards. */
export function observeBadgeAwards(scope: BadgeAwardScope | null, awards: readonly BadgeAward[]) {
  if (!isCurrent(scope)) return;
  const ids = seen(scope);
  for (const award of awards) ids.observed.add(identity(award));
  save(scope, ids);
}

/** Call only for an actual new server award, using a scope captured before the request. */
export function enqueueBadgeAward(scope: BadgeAwardScope | null, award: BadgeAward, options: { confirmedTransition?: boolean } = {}): boolean {
  if (!isCurrent(scope)) return false;
  const ids = seen(scope);
  const key = identity(award);
  // A current server-confirmed completion can race the first historical badge read.
  // Only that explicit transition may promote an observation; presentations never replay.
  if (ids.presented.has(key) || (ids.observed.has(key) && !options.confirmedTransition)) return false;
  ids.observed.add(key);
  ids.presented.add(key);
  save(scope, ids);
  queue = queue.filter(item => isCurrent(item.scope));
  queue.push({ scope, award });
  revision += 1;
  listeners.forEach(listener => listener());
  return true;
}

export function subscribeBadgeAwards(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export const badgeAwardRevision = () => revision;

export function nextBadgeAward(scope: BadgeAwardScope | null) {
  if (!isCurrent(scope)) return null;
  return queue.find(item => item.scope.principalKey === scope.principalKey
    && item.scope.authGeneration === scope.authGeneration)?.award ?? null;
}

export function dismissBadgeAward(scope: BadgeAwardScope | null, award: BadgeAward) {
  if (!scope) return;
  queue = queue.filter(item => !(item.scope.principalKey === scope.principalKey
    && item.scope.authGeneration === scope.authGeneration && identity(item.award) === identity(award)));
  revision += 1;
  listeners.forEach(listener => listener());
}
