import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import {
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
