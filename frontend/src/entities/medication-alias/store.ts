import { restoreAccountPrincipal } from '@/shared/api/client';
import type { MedicationOverview } from '@/entities/medication';
import type { MedicationAliasStoreOptions } from './types';

const STORAGE_KEY_PREFIX = 'rxvita.medication-aliases';
type AliasMap = Record<string, string | null>;

const memoryAliasesByScope = new Map<string, AliasMap>();

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function resolveScope(scope?: string | null): string {
  const principal = scope ?? restoreAccountPrincipal();
  return principal?.trim().toLowerCase() || 'anonymous';
}

function storageKey(scope?: string | null): string {
  return `${STORAGE_KEY_PREFIX}:${encodeURIComponent(resolveScope(scope))}`;
}

function readAliases(options: MedicationAliasStoreOptions = {}): AliasMap {
  const scope = resolveScope(options.scope);
  if (!canUseStorage()) return { ...(memoryAliasesByScope.get(scope) ?? {}) };
  try {
    const raw = window.localStorage.getItem(storageKey(scope));
    if (!raw) return { ...(memoryAliasesByScope.get(scope) ?? {}) };
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ...(memoryAliasesByScope.get(scope) ?? {}) };
    }
    const aliases: AliasMap = {};
    for (const [recordId, alias] of Object.entries(parsed)) {
      if (typeof alias === 'string' || alias === null) aliases[recordId] = alias;
    }
    memoryAliasesByScope.set(scope, aliases);
    return { ...aliases };
  } catch {
    return { ...(memoryAliasesByScope.get(scope) ?? {}) };
  }
}

function writeAliases(aliases: AliasMap, options: MedicationAliasStoreOptions = {}): void {
  const scope = resolveScope(options.scope);
  const next = { ...aliases };
  memoryAliasesByScope.set(scope, next);
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(storageKey(scope), JSON.stringify(next));
  } catch {
    // storage가 막힌 경우 현재 탭 메모리 어댑터로 계속 동작합니다.
  }
}

export function getMedicationAlias(
  recordId: number,
  options: MedicationAliasStoreOptions = {},
): string | undefined {
  const aliases = readAliases(options);
  return Object.prototype.hasOwnProperty.call(aliases, String(recordId))
    ? aliases[String(recordId)] ?? undefined
    : undefined;
}

/** 빈 별칭은 서버 기본값도 덮어쓸 수 있도록 명시적인 null override로 보관합니다. */
export function setMedicationAlias(
  recordId: number,
  alias: string,
  options: MedicationAliasStoreOptions = {},
): void {
  const aliases = readAliases(options);
  aliases[String(recordId)] = alias.trim() || null;
  writeAliases(aliases, options);
}

export function applyMedicationAliases(
  overviews: MedicationOverview[],
  options: MedicationAliasStoreOptions = {},
): MedicationOverview[] {
  const aliases = readAliases(options);
  return overviews.map((overview) => {
    const key = String(overview.recordId);
    if (!Object.prototype.hasOwnProperty.call(aliases, key)) return overview;
    return { ...overview, alias: aliases[key] ?? undefined };
  });
}
