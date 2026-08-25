import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { restoreAccessToken, setAccessToken } from '@/shared/api/client';

interface SessionValue {
  authenticated: boolean;
  signIn: () => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(() => Boolean(restoreAccessToken()));
  const value = useMemo(
    () => ({
      authenticated,
      signIn: () => setAuthenticated(true),
      signOut: () => {
        setAccessToken(null);
        setAuthenticated(false);
      },
    }),
    [authenticated],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (value === null) throw new Error('useSession은 SessionProvider 안에서 사용해야 합니다.');
  return value;
}
