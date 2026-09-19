import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { getAuthGeneration, http, setAccessToken } from '@/shared/api/client';
import { Button } from '@/shared/ui';

type DemoLogin = { access_token: string; email: string };
let pendingLogin: Promise<DemoLogin> | null = null;
function requestDemoLogin() {
  pendingLogin ??= http.post<DemoLogin>('/v1/auth/demo-login', {}).finally(() => { pendingLogin = null; });
  return pendingLogin;
}

export function DemoPage() {
  const navigate = useNavigate();
  const { signIn, isDemo } = useSession();
  const [error, setError] = useState<string | null>(null);
  const completed = useRef(false);
  useEffect(() => {
    if (isDemo) {
      navigate('/home', { replace: true });
      return;
    }
    if (completed.current) return;
    let cancelled = false;
    const generation = getAuthGeneration();
    void requestDemoLogin().then(result => {
      if (cancelled || generation !== getAuthGeneration()) return;
      completed.current = true;
      setAccessToken(result.access_token);
      signIn(result.email, true);
      navigate('/home', { replace: true });
    }).catch(cause => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : '데모 로그인에 실패했습니다.');
    });
    return () => { cancelled = true; };
  }, [navigate, signIn, isDemo]);
  return <main className="mx-auto max-w-app space-y-4 p-6">
    {error ? <><p role="alert">{error}</p><Button onClick={() => window.location.reload()}>다시 시도</Button></>
      : <p role="status">데모 로그인 중입니다.</p>}
  </main>;
}
