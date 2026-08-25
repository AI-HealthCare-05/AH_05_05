import { useState } from 'react';
import { ChevronRight, Pill, Sprout, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { BottomTabbar, Button, Card, Header, Switch, type TabKey } from '@/shared/ui';

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

interface MyPageProps {
  authenticatedOverride?: boolean;
}

export function MyPage({ authenticatedOverride }: MyPageProps) {
  const navigate = useNavigate();
  const { authenticated, signOut } = useSession();
  const isAuthenticated = authenticatedOverride ?? authenticated;
  const [medicationNotifications, setMedicationNotifications] = useState(true);
  const [supplementNotifications, setSupplementNotifications] = useState(false);

  function handleTabChange(key: TabKey) {
    if (key === 'my') return;
    if (!isAuthenticated && key !== 'home') {
      navigate('/login');
      return;
    }
    navigate(TAB_ROUTES[key]);
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="마이페이지" />
      <main className="flex flex-1 flex-col gap-6 overflow-y-auto px-page-x py-5">
        {isAuthenticated ? (
          <>
            <Card className="flex-row items-center gap-4 p-4">
              <span className="flex size-12 shrink-0 items-center justify-center rounded-pill bg-muted-bg text-muted-foreground">
                <UserRound aria-hidden className="size-6" />
              </span>
              <div>
                <p className="text-lg font-bold text-foreground">포케 사용자</p>
              </div>
            </Card>

            <section className="flex flex-col gap-3" aria-labelledby="my-management-title">
              <h2 id="my-management-title" className="text-xl font-bold text-foreground">
                내 관리
              </h2>
              <Card className="gap-0 overflow-hidden p-0">
                <ManagementRow
                  icon={Pill}
                  label="복용약"
                  value="4개"
                  onClick={() => navigate('/medications')}
                />
                <ManagementRow
                  icon={Sprout}
                  label="영양제"
                  value="3개"
                  onClick={() => navigate('/supplements')}
                  divided
                />
              </Card>
            </section>

            <section className="flex flex-col gap-3" aria-labelledby="notification-title">
              <h2 id="notification-title" className="text-xl font-bold text-foreground">
                알림
              </h2>
              <Card className="gap-0 overflow-hidden p-0">
                <NotificationRow
                  label="복약 알림"
                  checked={medicationNotifications}
                  onCheckedChange={setMedicationNotifications}
                />
                <NotificationRow
                  label="영양제 알림"
                  checked={supplementNotifications}
                  onCheckedChange={setSupplementNotifications}
                  divided
                />
              </Card>
            </section>

            <section className="flex flex-col gap-3" aria-labelledby="account-title">
              <h2 id="account-title" className="text-xl font-bold text-foreground">
                계정
              </h2>
              <Card className="p-4">
                <Button
                  variant="secondary"
                  onClick={() => {
                    signOut();
                    navigate('/home', { replace: true });
                  }}
                >
                  로그아웃
                </Button>
              </Card>
            </section>
          </>
        ) : (
          <>
            <Card className="flex-row items-center gap-4 p-5">
              <span className="flex size-12 shrink-0 items-center justify-center rounded-pill bg-muted-bg text-muted-foreground">
                <UserRound aria-hidden className="size-6" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-lg font-bold text-foreground">로그인하지 않았어요</p>
                <p className="text-sm text-muted-foreground">저장한 기록을 이어서 보려면 로그인해 주세요.</p>
              </div>
              <Button fullWidth={false} className="px-4" onClick={() => navigate('/login')}>
                로그인
              </Button>
            </Card>

            <nav className="mt-auto flex flex-col" aria-label="법적 안내">
              <a href="/terms" className="flex min-h-touch items-center text-sm text-muted-foreground">
                이용약관
              </a>
              <a href="/privacy" className="flex min-h-touch items-center text-sm text-muted-foreground">
                개인정보 처리 안내
              </a>
            </nav>
          </>
        )}
      </main>
      <BottomTabbar
        active="my"
        onChange={handleTabChange}
        className="border-t border-border"
      />
    </div>
  );
}

function ManagementRow({
  icon: Icon,
  label,
  value,
  onClick,
  divided = false,
}: {
  icon: typeof Pill;
  label: string;
  value: string;
  onClick: () => void;
  divided?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-20 w-full items-center gap-3 px-4 text-left ${
        divided ? 'border-t border-border' : ''
      }`}
    >
      <span className="flex size-12 items-center justify-center rounded-pill bg-primary-bg text-primary-strong">
        <Icon aria-hidden className="size-6" />
      </span>
      <span className="flex-1 text-base font-bold text-foreground">{label}</span>
      <span className="text-sm text-muted-foreground">{value}</span>
      <ChevronRight aria-hidden className="size-5 text-disabled-foreground" />
    </button>
  );
}

function NotificationRow({
  label,
  checked,
  onCheckedChange,
  divided = false,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  divided?: boolean;
}) {
  return (
    <div className={`flex min-h-20 items-center justify-between px-4 ${divided ? 'border-t border-border' : ''}`}>
      <label htmlFor={`notification-${label}`} className="text-base font-bold text-foreground">
        {label}
      </label>
      <Switch
        id={`notification-${label}`}
        aria-label={label}
        checked={checked}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}
