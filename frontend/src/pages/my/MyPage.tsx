import { useEffect, useRef, useState } from 'react';
import { ChevronRight, Pill, Sprout, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  NotifyBlockedDialog,
  NotifyPermissionDialog,
  Switch,
  type TabKey,
} from '@/shared/ui';
import {
  getNotifySettings,
  updateNotifySettings,
  type NotifySettingKey,
  type NotifySettings,
  type UpdateNotifySettingsPayload,
} from '@/entities/settings';
import {
  getPushPermission,
  requestPushPermission,
  type PushPermission,
} from '@/shared/push/permission';
import { registerPushNotifications } from '@/shared/push/register';

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

interface MyPageProps {
  authenticatedOverride?: boolean;
  notifySettingsLoader?: () => Promise<NotifySettings>;
  notifySettingsUpdater?: (payload: UpdateNotifySettingsPayload) => Promise<NotifySettings>;
  permissionReader?: () => PushPermission;
  permissionRequester?: () => Promise<PushPermission>;
  pushRegistrar?: () => Promise<void>;
}

export function MyPage({
  authenticatedOverride,
  notifySettingsLoader = getNotifySettings,
  notifySettingsUpdater = updateNotifySettings,
  permissionReader = getPushPermission,
  permissionRequester = requestPushPermission,
  pushRegistrar = registerPushNotifications,
}: MyPageProps) {
  const navigate = useNavigate();
  const { authenticated, signOut } = useSession();
  const isAuthenticated = authenticatedOverride ?? authenticated;
  const logoutNavigationRef = useRef(false);
  const [notifySettings, setNotifySettings] = useState<NotifySettings | null>(null);
  const [notifyLoadError, setNotifyLoadError] = useState<string | null>(null);
  const [notifyActionError, setNotifyActionError] = useState<{
    message: string;
    retry: () => void;
  } | null>(null);
  const [pendingToggle, setPendingToggle] = useState<NotifySettingKey | null>(null);
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);
  const [blockedDialogOpen, setBlockedDialogOpen] = useState(false);
  const [notificationBusy, setNotificationBusy] = useState(false);
  const [pendingSettingKeys, setPendingSettingKeys] = useState<NotifySettingKey[]>([]);
  const pushPermission = permissionReader();
  const pushUnsupported = pushPermission === 'unsupported';

  useEffect(() => {
    if (
      authenticatedOverride === undefined &&
      !authenticated &&
      !logoutNavigationRef.current
    ) {
      navigate('/login', { replace: true });
    }
  }, [authenticated, authenticatedOverride, navigate]);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    setNotifyLoadError(null);
    notifySettingsLoader()
      .then((settings) => {
        if (!cancelled) setNotifySettings(settings);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setNotifyLoadError(
          error instanceof Error ? error.message : '알림 설정을 불러오지 못했어요.',
        );
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, notifySettingsLoader]);

  async function persistNotifySettings(
    payload: UpdateNotifySettingsPayload,
    retry: () => void,
  ): Promise<NotifySettings | null> {
    setNotificationBusy(true);
    setNotifyActionError(null);
    try {
      const updated = await notifySettingsUpdater(payload);
      setNotifySettings(updated);
      return updated;
    } catch (error: unknown) {
      setNotifyActionError({
        message: error instanceof Error ? error.message : '알림 설정을 저장하지 못했어요.',
        retry,
      });
      return null;
    } finally {
      setNotificationBusy(false);
    }
  }

  function setSettingPending(key: NotifySettingKey, pending: boolean) {
    setPendingSettingKeys((current) =>
      pending
        ? current.includes(key)
          ? current
          : [...current, key]
        : current.filter((pendingKey) => pendingKey !== key),
    );
  }

  async function persistToggleOptimistically(
    key: NotifySettingKey,
    checked: boolean,
    beforeSave: (() => Promise<void>) | undefined,
    retry: () => void,
  ) {
    const previousValue = notifySettings?.[key];
    if (previousValue === undefined) return;

    setNotifySettings((current) => (current ? { ...current, [key]: checked } : current));
    setSettingPending(key, true);
    setNotifyActionError(null);
    try {
      await beforeSave?.();
      const updated = await notifySettingsUpdater({ [key]: checked });
      setNotifySettings((current) =>
        current
          ? {
              ...current,
              [key]: updated[key],
              notifyConsentedAt: updated.notifyConsentedAt,
            }
          : updated,
      );
      setPendingToggle(null);
    } catch (error: unknown) {
      setNotifySettings((current) =>
        current ? { ...current, [key]: previousValue } : current,
      );
      setNotifyActionError({
        message: error instanceof Error ? error.message : '알림 설정을 저장하지 못했어요.',
        retry,
      });
    } finally {
      setSettingPending(key, false);
    }
  }

  function enableNotification(key: NotifySettingKey) {
    return persistToggleOptimistically(
      key,
      true,
      pushRegistrar,
      () => void enableNotification(key),
    );
  }

  async function acknowledgeConsentIfNeeded(): Promise<boolean> {
    if (notifySettings?.notifyConsentedAt) return true;
    return (await persistNotifySettings({}, () => void acknowledgeConsentIfNeeded())) !== null;
  }

  function handleNotificationChange(key: NotifySettingKey, checked: boolean) {
    if (!notifySettings || pendingSettingKeys.includes(key) || pushUnsupported) return;
    if (!checked) {
      void persistToggleOptimistically(
        key,
        false,
        undefined,
        () => handleNotificationChange(key, false),
      );
      return;
    }

    const permission = permissionReader();
    if (permission === 'granted') {
      void enableNotification(key);
      return;
    }
    if (permission === 'denied') {
      setBlockedDialogOpen(true);
      return;
    }
    if (permission === 'default') {
      setPendingToggle(key);
      setPermissionDialogOpen(true);
    }
  }

  async function handlePermissionAccept() {
    const key = pendingToggle;
    if (!key) return;
    setNotificationBusy(true);
    let permission: PushPermission;
    try {
      permission = await permissionRequester();
    } catch (error: unknown) {
      setNotificationBusy(false);
      setPermissionDialogOpen(false);
      setNotifyActionError({
        message: error instanceof Error ? error.message : '알림 권한을 확인하지 못했어요.',
        retry: () => void handlePermissionAccept(),
      });
      return;
    }
    setPermissionDialogOpen(false);
    setNotificationBusy(false);

    if (permission === 'granted') {
      await enableNotification(key);
      return;
    }

    const acknowledged = await acknowledgeConsentIfNeeded();
    if (!acknowledged) return;
    setPendingToggle(null);
    if (permission === 'denied') setBlockedDialogOpen(true);
  }

  async function handlePermissionDismiss() {
    setPermissionDialogOpen(false);
    const acknowledged = await acknowledgeConsentIfNeeded();
    if (!acknowledged) return;
    setPendingToggle(null);
  }

  function handleTabChange(key: TabKey) {
    if (key === 'my') return;
    if (!isAuthenticated && key !== 'home') {
      navigate('/login');
      return;
    }
    navigate(TAB_ROUTES[key]);
  }

  function handleSignOut() {
    logoutNavigationRef.current = true;
    signOut();
    navigate('/home', { replace: true });
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="마이페이지" />
      <main className="flex flex-1 flex-col gap-6 overflow-y-auto px-page-x py-5">
        {isAuthenticated ? (
          <>
            <button
              type="button"
              className="flex min-h-20 items-center gap-4 rounded-card bg-card p-4 text-left shadow-card"
              onClick={() => navigate('/my/profile')}
            >
              <span className="flex size-12 shrink-0 items-center justify-center rounded-pill bg-muted-bg text-muted-foreground">
                <UserRound aria-hidden className="size-6" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-lg font-bold text-foreground">포케 사용자</p>
                <p className="text-sm text-muted-foreground">기본정보</p>
              </div>
              <ChevronRight aria-hidden className="size-5 text-disabled-foreground" />
            </button>

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
                {notifyLoadError ? (
                  <div className="p-4">
                    <p className="font-bold text-foreground">알림 설정을 불러오지 못했어요</p>
                    <p className="mt-1 text-sm text-muted-foreground">{notifyLoadError}</p>
                  </div>
                ) : notifySettings ? (
                  <>
                    <NotificationRow
                      label="복약 알림"
                      checked={notifySettings.notifyMedication}
                      disabled={
                        pendingSettingKeys.includes('notifyMedication') || pushUnsupported
                      }
                      onCheckedChange={(checked) =>
                        handleNotificationChange('notifyMedication', checked)
                      }
                    />
                    <NotificationRow
                      label="영양제 알림"
                      checked={notifySettings.notifySupplement}
                      disabled={
                        pendingSettingKeys.includes('notifySupplement') || pushUnsupported
                      }
                      onCheckedChange={(checked) =>
                        handleNotificationChange('notifySupplement', checked)
                      }
                      divided
                    />
                  </>
                ) : (
                  <p className="p-4 text-sm text-muted-foreground">알림 설정을 불러오는 중...</p>
                )}
              </Card>
              {pushUnsupported && (
                <p className="text-sm text-muted-foreground">
                  이 브라우저에서는 알림을 지원하지 않아요
                </p>
              )}
            </section>

            <section className="flex flex-col gap-3" aria-labelledby="account-title">
              <h2 id="account-title" className="text-xl font-bold text-foreground">
                계정
              </h2>
              <Card className="p-4">
                <Button
                  variant="secondary"
                  onClick={handleSignOut}
                >
                  로그아웃
                </Button>
              </Card>
            </section>
          </>
        ) : null}
      </main>
      <BottomTabbar
        active="my"
        onChange={handleTabChange}
        className="border-t border-border"
      />
      <NotifyPermissionDialog
        open={permissionDialogOpen}
        title={
          pendingToggle === 'notifySupplement'
            ? '영양제 알림을 보내드릴까요?'
            : '복약 시간에 알림을 보내드릴까요?'
        }
        busy={notificationBusy}
        onAccept={() => void handlePermissionAccept()}
        onDismiss={() => void handlePermissionDismiss()}
      />
      <NotifyBlockedDialog
        open={blockedDialogOpen}
        onConfirm={() => setBlockedDialogOpen(false)}
      />
      <ErrorDialog
        open={notifyActionError !== null}
        title="알림 설정을 저장하지 못했어요"
        message={notifyActionError?.message ?? ''}
        onRetry={() => {
          const retry = notifyActionError?.retry;
          setNotifyActionError(null);
          retry?.();
        }}
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
  disabled = false,
  divided = false,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
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
        disabled={disabled}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}
