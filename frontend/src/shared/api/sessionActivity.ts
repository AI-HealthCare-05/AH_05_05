/** Same-origin, same-account activity only. No access/refresh tokens go in localStorage. */
export const SESSION_IDLE_MS = 30 * 60 * 1000;
interface Activity { at: number; ended: boolean; epoch?: string; sessionId?: string }
const memory = new Map<string, Activity>();
const epochs = new Map<string, string>();
const keyFor = (principal: string) => `poke.session-activity:${encodeURIComponent(principal)}`;
// getRandomValues also works on HTTP LAN development origins (randomUUID does not).
const newEpoch = () => Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join('-');

function tabEpoch(principal: string): string | null {
  try { return sessionStorage.getItem(`${keyFor(principal)}:epoch`) ?? epochs.get(principal) ?? null; }
  catch { return epochs.get(principal) ?? null; }
}

function bindEpoch(principal: string, epoch: string): void {
  epochs.set(principal, epoch);
  try { sessionStorage.setItem(`${keyFor(principal)}:epoch`, epoch); } catch { /* Memory fallback. */ }
}

function read(principal: string): Activity | null {
  try {
    const raw = localStorage.getItem(keyFor(principal));
    if (raw) {
      const value = JSON.parse(raw) as Activity;
      if (typeof value.at === 'number' && Number.isFinite(value.at) && value.at > 0 &&
          value.at <= Date.now() && typeof value.ended === 'boolean') {
        memory.set(principal, value);
        return value;
      }
    }
  } catch { /* Storage may be unavailable; preserve the current tab's timer. */ }
  return memory.get(principal) ?? null;
}

function write(principal: string, value: Activity): void {
  memory.set(principal, value);
  try { localStorage.setItem(keyFor(principal), JSON.stringify(value)); } catch { /* Memory fallback. */ }
}

export function beginActivitySession(principal: string, sessionId?: string | null): void {
  const current = read(principal);
  const canJoin = current && !current.ended && Date.now() - current.at < SESSION_IDLE_MS &&
    (!sessionId || current.sessionId === sessionId);
  const epoch = (canJoin ? current.epoch : undefined) || newEpoch();
  bindEpoch(principal, epoch);
  write(principal, { at: Date.now(), ended: false, epoch,
    sessionId: sessionId || (canJoin ? current.sessionId : undefined) });
}

export function endActivitySession(principal: string): void {
  const value = read(principal);
  if (value?.epoch && value.epoch !== tabEpoch(principal)) return;
  if (!value?.ended) write(principal, { ...value, at: Date.now(), ended: true });
}

export function ownsActivitySession(principal: string): boolean {
  const value = read(principal);
  return !value?.epoch || value.epoch === tabEpoch(principal);
}

export function isSessionIdle(principal: string): boolean {
  const value = read(principal);
  const epoch = tabEpoch(principal);
  return Boolean(value && (value.ended || (epoch && value.epoch && epoch !== value.epoch) ||
    Date.now() - value.at >= SESSION_IDLE_MS));
}

/** Page loads/focus/API calls never extend an existing idle deadline. */
export function watchSessionActivity(principal: string, onIdle: () => void): () => void {
  // One-time migration for already logged-in tabs without an activity timestamp.
  if (!read(principal)) beginActivitySession(principal);
  const initial = read(principal)!;
  if (!initial.epoch) {
    initial.epoch = newEpoch();
    write(principal, initial);
  }
  if (!tabEpoch(principal)) bindEpoch(principal, initial.epoch);
  let timer: number | undefined;
  let stopped = false;
  const check = () => {
    window.clearTimeout(timer);
    if (stopped) return;
    if (isSessionIdle(principal)) {
      stopped = true;
      onIdle();
      return;
    }
    const last = read(principal)!;
    timer = window.setTimeout(check, Math.max(1, last.at + SESSION_IDLE_MS - Date.now()));
  };
  const activity = (event: Event) => {
    if (!event.isTrusted || document.visibilityState !== 'visible' || stopped) return;
    // A click after suspension must not revive an already-expired session.
    if (isSessionIdle(principal)) { check(); return; }
    write(principal, { ...read(principal)!, at: Date.now(), ended: false, epoch: tabEpoch(principal)! });
    check();
  };
  const storage = (event: StorageEvent) => {
    if (event.key === keyFor(principal)) check();
  };
  // Wheel/touch/key events cover user scrolling without counting programmatic scrolling.
  const events = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'touchmove'];
  for (const name of events) window.addEventListener(name, activity, { passive: true, capture: true });
  window.addEventListener('storage', storage);
  window.addEventListener('focus', check);
  window.addEventListener('pageshow', check);
  document.addEventListener('visibilitychange', check);
  check();
  return () => {
    stopped = true;
    window.clearTimeout(timer);
    for (const name of events) window.removeEventListener(name, activity, true);
    window.removeEventListener('storage', storage);
    window.removeEventListener('focus', check);
    window.removeEventListener('pageshow', check);
    document.removeEventListener('visibilitychange', check);
  };
}
