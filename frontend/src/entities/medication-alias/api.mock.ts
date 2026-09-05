import { restoreAccountPrincipal } from '@/shared/api/client';

const SESSION_KEY = 'rxvita.mock.medication-aliases';
const memoryAliasesByScope = new Map<string, Record<string, string | null>>();

function resolveScope(): string {
  return restoreAccountPrincipal()?.trim().toLowerCase() || 'anonymous';
}

function readAliases(): Record<string, string | null> {
  const scope = resolveScope();
  const memory = memoryAliasesByScope.get(scope);
  try {
    const raw = sessionStorage.getItem(`${SESSION_KEY}:${encodeURIComponent(scope)}`);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const aliases: Record<string, string | null> = {};
        for (const [recordId, alias] of Object.entries(parsed)) {
          if (typeof alias === 'string' || alias === null) aliases[recordId] = alias;
        }
        memoryAliasesByScope.set(scope, aliases);
        return { ...aliases };
      }
    }
  } catch {
    // session storage is an optional persistence layer for the mock adapter.
  }
  return { ...(memory ?? {}) };
}

function writeAliases(aliases: Record<string, string | null>): void {
  const scope = resolveScope();
  const next = { ...aliases };
  memoryAliasesByScope.set(scope, next);
  try {
    sessionStorage.setItem(`${SESSION_KEY}:${encodeURIComponent(scope)}`, JSON.stringify(next));
  } catch {
    // Keep the in-memory mock usable when storage is disabled.
  }
}

export function mockUpdateEpisodeAlias(recordId: number, alias: string | null): void {
  const aliases = readAliases();
  aliases[String(recordId)] = alias?.trim() || null;
  writeAliases(aliases);
}

export function mockMedicationAlias(recordId: number, fallback?: string): string | undefined {
  const aliases = readAliases();
  const key = String(recordId);
  if (Object.prototype.hasOwnProperty.call(aliases, key)) return aliases[key] ?? undefined;
  return fallback;
}
