import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AUTH_SESSION_EXPIRED_EVENT,
  accessTokenExpiresAt,
  restoreAccessToken,
  restoreAccountPrincipal,
  setAccessToken,
  setAccountPrincipal,
} from '@/shared/api/client';
import { getPushPermission } from '@/shared/push/permission';
import { registerPushNotifications, unregisterPushNotifications } from '@/shared/push/register';

interface SessionValue {
  authenticated: boolean;
  principalKey: string | null;
  signIn: (principalKey: string) => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
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
      void unregisterPushNotifications({ deactivateServer: false });
      setAccessToken(null);
      setAccountPrincipal(null);
      setPrincipalKey(null);
      setAuthenticated(false);
    };
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);

    const token = restoreAccessToken();
    const expiresAt = token ? accessTokenExpiresAt(token) : null;
    if (expiresAt === null) {
      return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);
    }

    const remainingMs = expiresAt - Date.now();
    if (remainingMs <= 0) {
      expireCurrentSession();
      return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);
    }

    const expirationTimer = window.setTimeout(
      expireCurrentSession,
      Math.min(remainingMs, 2_147_483_647),
    );
    return () => {
      window.clearTimeout(expirationTimer);
      window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expireCurrentSession);
    };
  }, [authenticated, principalKey]);

  const value = useMemo(
    () => ({
      authenticated,
      principalKey,
      signIn: (nextPrincipalKey: string) => {
        const normalizedPrincipal = nextPrincipalKey.trim().toLowerCase();
        if (!restoreAccessToken() || !normalizedPrincipal) {
          setAccountPrincipal(null);
          setPrincipalKey(null);
          setAuthenticated(false);
          return;
        }
        setAccountPrincipal(normalizedPrincipal);
        setPrincipalKey(normalizedPrincipal);
        setAuthenticated(true);
      },
      signOut: async () => {
        await unregisterPushNotifications();
        setAccessToken(null);
        setAccountPrincipal(null);
        setPrincipalKey(null);
        setAuthenticated(false);
      },
    }),
    [authenticated, principalKey],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (value === null) throw new Error('useSession은 SessionProvider 안에서 사용해야 합니다.');
  return value;
}
