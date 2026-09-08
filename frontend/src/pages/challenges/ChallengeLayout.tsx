import { Outlet, useLocation, useNavigate } from 'react-router';

import { BottomTabbar, type TabKey } from '@/shared/ui/BottomTabbar';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';

export function ChallengeLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const isDev = location.pathname.startsWith('/dev/');

  function handleTabChange(key: TabKey) {
    if (key === 'home') {
      navigate(isDev ? '/dev/home-challenges' : TAB_ROUTES.home);
      return;
    }
    if (key === 'my') {
      navigate(isDev ? '/dev/my-authenticated' : '/my');
      return;
    }
    navigate(TAB_ROUTES[key]);
  }

  return (
    <div className="mx-auto flex h-dvh min-h-dvh w-full max-w-app flex-col overflow-hidden bg-background">
      {isDev ? (
        <p className="shrink-0 border-b border-border bg-muted-bg px-page-x py-1.5 text-center text-micro text-tertiary-foreground">
          목업 미리보기 · 기준일 2026.09.13 · 새로고침 시 초기화
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-gutter:stable]">
        <Outlet />
      </div>
      <BottomTabbar active="my" onChange={handleTabChange} className="border-t border-border" />
    </div>
  );
}
