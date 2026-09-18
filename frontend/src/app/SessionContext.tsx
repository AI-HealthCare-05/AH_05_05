import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AUTH_SESSION_EXPIRED_EVENT,
  accessTokenExpiresAt,
  accessTokenSessionId,
  restoreAccessToken,
  restoreAccountPrincipal,
  setAccessToken,
  setAccountPrincipal,
  endSession,
  refreshAccessToken,
} from '@/shared/api/client';
import { beginActivitySession, endActivitySession, watchSessionActivity } from '@/shared/api/sessionActivity';
import { getPushPermission } from '@/shared/push/permission';
import { registerPushNotifications, unregisterPushNotifications } from '@/shared/push/register';

interface SessionValue {
  isDemo: boolean;
  authenticated: boolean;
  principalKey: string | null;
  signIn: (principalKey: string, demo?: boolean) => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [demoPrincipal, setDemoPrincipal] = useState(() => sessionStorage.getItem('rxvita.demo-principal'));
  const [principalKey, setPrincipalKey] = useState(() => restoreAccountPrincipal());
  const [authenticated, setAuthenticated] = useState(
    () => Boolean(restoreAccessToken() && restoreAccountPrincipal()),
  );

  useEffect(() => {
    if (!authenticated || getPushPermission() !== 'granted') return;

    // Push 재등록 실패가 로그인 자체를 막지는 않습니다. 다음 로그인이나 알림 설정에서 재시도합니다.
    void registerPushNotifications().catch(() => undefined);
  }, [authenticated, principalKey]);

  useEffect(() => {
    const expireCurrentSession = () => {
      sessionStorage.removeItem('rxvita.demo-principal');
      setDemoPrincipal(null);
      void unregisterPushNotifications({ deactivateServer: false });
      const principal = restoreAccountPrincipal();
      if (principal) endActivitySession(principal);
      setAccessToken(null);
      setAccountPrincipal(null);
      setPrincipalKey(null);
      setAuthenticated(false);
    };
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);

    if (!authenticated || !principalKey) {
      return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);
    }
    const stopActivity = watchSessionActivity(principalKey, () => { void endSession(); });
    const refreshIfNeeded = () => {
      const token = restoreAccessToken();
      const expiresAt = token ? accessTokenExpiresAt(token) : null;
      if (expiresAt !== null && expiresAt <= Date.now() + 60_000) {
        // Temporary network errors are retried later; they must not log the user out.
        void refreshAccessToken().catch(() => undefined);
      }
    };
    refreshIfNeeded();
    const refreshTimer = window.setInterval(refreshIfNeeded, 30_000);
    window.addEventListener('focus', refreshIfNeeded);
    return () => {
      stopActivity();
      window.clearInterval(refreshTimer);
      window.removeEventListener('focus', refreshIfNeeded);
      window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);
    };
  }, [authenticated, principalKey]);

  const value = useMemo(
    () => ({
      authenticated,
      isDemo: authenticated && demoPrincipal === principalKey,
      principalKey,
      signIn: (nextPrincipalKey: string, demo = false) => {
        const normalizedPrincipal = nextPrincipalKey.trim().toLowerCase();
        if (demo) sessionStorage.setItem('rxvita.demo-principal', normalizedPrincipal);
        else sessionStorage.removeItem('rxvita.demo-principal');
        setDemoPrincipal(demo ? normalizedPrincipal : null);
        if (!restoreAccessToken() || !normalizedPrincipal) {
          setAccountPrincipal(null);
          setPrincipalKey(null);
          setAuthenticated(false);
          return;
        }
        setAccountPrincipal(normalizedPrincipal);
        beginActivitySession(normalizedPrincipal, accessTokenSessionId(restoreAccessToken()!));
        setPrincipalKey(normalizedPrincipal);
        setAuthenticated(true);
      },
      signOut: async () => {
        sessionStorage.removeItem('rxvita.demo-principal');
        setDemoPrincipal(null);
        // Invalidate earlier refreshes, then preserve server Push cleanup with a bounded wait.
        setAccessToken(restoreAccessToken());
        let timeout: number | undefined;
        await Promise.race([
          unregisterPushNotifications(),
          new Promise<void>(resolve => { timeout = window.setTimeout(resolve, 3_000); }),
        ]);
        window.clearTimeout(timeout);
        await endSession();
      },
    }),
    [authenticated, principalKey, demoPrincipal],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (value === null) throw new Error('useSession은 SessionProvider 안에서 사용해야 합니다.');
  return value;
}
