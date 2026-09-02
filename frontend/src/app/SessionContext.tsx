import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AUTH_SESSION_EXPIRED_EVENT,
  accessTokenExpiresAt,
  restoreAccessToken,
  restoreAccountPrincipal,
  setAccessToken,
  setAccountPrincipal,
} from '@/shared/api/client';

interface SessionValue {
  authenticated: boolean;
  principalKey: string | null;
  signIn: (principalKey: string) => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [principalKey, setPrincipalKey] = useState(() => restoreAccountPrincipal());
  const [authenticated, setAuthenticated] = useState(
    () => Boolean(restoreAccessToken() && restoreAccountPrincipal()),
  );

  useEffect(() => {
    const expireCurrentSession = () => {
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
      signOut: () => {
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
