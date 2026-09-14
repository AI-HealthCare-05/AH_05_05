/** Serialize cookie-changing responses across tabs; refresh never changes the cookie. */
const KEY = 'poke.auth-cookie-lock';
const LEASE_MS = 15_000;
const pause = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));

export async function withAuthCookieLock<T>(operation: () => Promise<T>): Promise<T> {
  if (navigator.locks) return navigator.locks.request(KEY, operation);

  // HTTP LAN development may not expose Web Locks. All locked fetches time out at 10s,
  // shorter than the lease; abandoned tabs therefore cannot leave a permanent lock.
  const owner = Array.from(crypto.getRandomValues(new Uint32Array(4))).join('-');
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    let acquired = false;
    try {
      const raw = localStorage.getItem(KEY);
      let lease: { owner?: string; until?: number } | null = null;
      try { lease = raw ? JSON.parse(raw) : null; } catch { /* Replace malformed lease. */ }
      if (!lease || typeof lease.until !== 'number' || lease.until <= Date.now()) {
        localStorage.setItem(KEY, JSON.stringify({ owner, until: Date.now() + LEASE_MS }));
        // Yield before verifying ownership when two tabs observe an empty lease at once.
        await pause(50);
        acquired = JSON.parse(localStorage.getItem(KEY) ?? '{}').owner === owner;
      }
    } catch {
      // Fail closed: without either coordination mechanism a stale Set-Cookie could
      // delete a new login. The UI can retry once browser storage is available.
      throw new Error('로그인 상태를 안전하게 변경하려면 브라우저 저장소를 허용해 주세요.');
    }
    if (acquired) {
      try { return await operation(); }
      finally {
        try {
          if (JSON.parse(localStorage.getItem(KEY) ?? '{}').owner === owner) localStorage.removeItem(KEY);
        } catch { /* Lease expires even if cleanup storage is unavailable. */ }
      }
    }
    await pause(100);
  }
  throw new Error('다른 탭에서 로그인 상태를 변경 중이에요. 잠시 후 다시 시도해주세요.');
}
