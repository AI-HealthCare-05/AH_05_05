import { useEffect, useRef, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useSession } from '@/app/SessionContext';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import {
  getMedicationOverviews,
  type MedicationOverview,
} from '@/entities/medication';
import { getSupplements } from '@/entities/supplement';
import { listFollowUpVisits, type FollowUpVisit } from '@/entities/follow-up-visit';
import {
  BottomTabbar,
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
  type MedicationTimes,
  type NotifySettingKey,
  type NotifySettings,
  type UpdateNotifySettingsPayload,
} from '@/entities/settings';
import { SLOT_ORDER, isMealTimeOrderValid, mealSlotLabel } from '@/shared/model/mealSlot';
import {
  getPushPermission,
  requestPushPermission,
  type PushPermission,
} from '@/shared/push/permission';
import { registerPushNotifications } from '@/shared/push/register';
import { MedicationTimeSettingsSheet } from './MedicationTimeSettingsSheet';

const SHORT_MEAL_SLOT_ORDER = SLOT_ORDER.map((slot) => mealSlotLabel(slot, 'short')).join(' < ');

function medicationTimesFromSettings(settings: NotifySettings): MedicationTimes {
  return {
    morningMedicationTime: settings.morningMedicationTime,
    lunchMedicationTime: settings.lunchMedicationTime,
    eveningMedicationTime: settings.eveningMedicationTime,
    bedtimeMedicationTime: settings.bedtimeMedicationTime,
  };
}

function mealSlotTimesFromMedicationTimes(times: MedicationTimes) {
  return {
    morning: times.morningMedicationTime,
    lunch: times.lunchMedicationTime,
    evening: times.eveningMedicationTime,
    bedtime: times.bedtimeMedicationTime,
  };
}

function todayString(): string {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${today.getFullYear()}-${month}-${day}`;
}

function countActiveMedications(overviews: MedicationOverview[]): number {
  return overviews
    .filter((overview) => !overview.isFinished)
    .reduce((total, overview) => total + overview.medications.length, 0);
}

function countUpcomingVisits(visits: FollowUpVisit[]): number {
  const today = todayString();
  return visits.filter((visit) => visit.visitDate >= today).length;
}

interface ManagementCounts {
  medication: number;
  supplement: number;
  upcomingVisit: number;
}

interface MyPageProps {
  authenticatedOverride?: boolean;
  medicationOverviewsLoader?: typeof getMedicationOverviews;
  supplementsLoader?: typeof getSupplements;
  followUpVisitsLoader?: typeof listFollowUpVisits;
  notifySettingsLoader?: () => Promise<NotifySettings>;
  notifySettingsUpdater?: (payload: UpdateNotifySettingsPayload) => Promise<NotifySettings>;
  permissionReader?: () => PushPermission;
  permissionRequester?: () => Promise<PushPermission>;
  pushRegistrar?: () => Promise<void>;
}

export function MyPage({
  authenticatedOverride,
  medicationOverviewsLoader = getMedicationOverviews,
  supplementsLoader = getSupplements,
  followUpVisitsLoader = listFollowUpVisits,
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
  const [managementCounts, setManagementCounts] = useState<ManagementCounts | null>(null);
  const [managementLoadError, setManagementLoadError] = useState<string | null>(null);
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
  const [timeSheetOpen, setTimeSheetOpen] = useState(false);
  const [timeDraft, setTimeDraft] = useState<MedicationTimes | null>(null);
  const [timeSaveError, setTimeSaveError] = useState<string | null>(null);
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

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    setManagementCounts(null);
    setManagementLoadError(null);
    Promise.all([
      medicationOverviewsLoader(),
      supplementsLoader(),
      followUpVisitsLoader({ startDate: todayString() }),
    ])
      .then(([medicationOverviews, supplements, visits]) => {
        if (cancelled) return;
        setManagementCounts({
          medication: countActiveMedications(medicationOverviews),
          supplement: supplements.items.length,
          upcomingVisit: countUpcomingVisits(visits),
        });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setManagementLoadError(
          error instanceof Error ? error.message : '관리 정보를 불러오지 못했어요.',
        );
      });
    return () => {
      cancelled = true;
    };
  }, [followUpVisitsLoader, isAuthenticated, medicationOverviewsLoader, supplementsLoader]);

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

  function openMedicationTimeSheet() {
    if (!notifySettings) return;
    setTimeDraft(medicationTimesFromSettings(notifySettings));
    setTimeSaveError(null);
    setTimeSheetOpen(true);
  }

  function cancelMedicationTimeSheet() {
    setTimeSheetOpen(false);
    setTimeDraft(null);
    setTimeSaveError(null);
  }

  function updateMedicationTimeDraft(values: MedicationTimes) {
    setTimeDraft(values);
    setTimeSaveError(null);
  }

  async function saveMedicationTimes() {
    if (!timeDraft) return;
    if (!isMealTimeOrderValid(mealSlotTimesFromMedicationTimes(timeDraft))) {
      setTimeSaveError(`${SHORT_MEAL_SLOT_ORDER} 순서로 정해주세요`);
      return;
    }

    setNotificationBusy(true);
    setTimeSaveError(null);
    try {
      const updated = await notifySettingsUpdater(timeDraft);
      setNotifySettings(updated);
      setTimeSheetOpen(false);
      setTimeDraft(null);
      toast.success('알림 시간을 바꿨어요.');
    } catch (error: unknown) {
      setTimeSaveError(
        error instanceof Error ? error.message : '알림 설정을 저장하지 못했어요.',
      );
    } finally {
      setNotificationBusy(false);
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
    window.location.replace('/home');
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="마이페이지" />
      <main className="flex flex-1 flex-col overflow-y-auto px-page-x pb-3 pt-3">
        {isAuthenticated ? (
          <>
            <button
              type="button"
              className="flex min-h-[84px] items-center gap-4 rounded-card border border-border bg-card p-3.5 text-left"
              onClick={() => navigate('/my/profile')}
            >
              <span className="flex size-14 shrink-0 items-center justify-center rounded-pill bg-muted-bg text-sm font-bold text-muted-foreground">
                사람
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[17px] font-bold text-foreground">RxVita 사용자</p>
                <p className="text-sm text-muted-foreground">기본정보</p>
              </div>
              <ChevronRight aria-hidden className="size-5 shrink-0 text-disabled-foreground" />
            </button>

            <section
              className="mt-5 flex flex-col"
              aria-labelledby="my-management-title"
              aria-busy={managementCounts === null && managementLoadError === null}
            >
              <h2 id="my-management-title" className="text-xl font-bold text-foreground">
                내 관리
              </h2>
              {!managementCounts && !managementLoadError && (
                <p role="status" aria-label="내 관리 불러오는 중" className="sr-only">
                  관리 정보를 불러오는 중...
                </p>
              )}
              {managementLoadError && (
                <p role="alert" aria-label="관리 정보 불러오기 실패" className="mt-1 text-sm text-danger-strong">
                  관리 항목 수를 확인하지 못했어요.
                </p>
              )}
              <div className="mt-3 overflow-hidden bg-card">
                <ManagementRow
                  label="복용약"
                  value={
                    managementCounts
                      ? `${managementCounts.medication}개`
                      : managementLoadError
                        ? '확인 불가'
                        : '확인 중'
                  }
                  onClick={() => navigate('/medications')}
                />
                <ManagementRow
                  label="영양제"
                  value={
                    managementCounts
                      ? `${managementCounts.supplement}개`
                      : managementLoadError
                        ? '확인 불가'
                        : '확인 중'
                  }
                  onClick={() => navigate('/supplements')}
                  divided
                />
                <ManagementRow
                  label="진료일정"
                  value={
                    managementCounts
                      ? `예정 ${managementCounts.upcomingVisit}개`
                      : managementLoadError
                        ? '확인 불가'
                        : '확인 중'
                  }
                  onClick={() => navigate('/my/visits')}
                  divided
                />
              </div>
            </section>

            <section className="mt-4 flex flex-col" aria-labelledby="notification-title">
              <h2 id="notification-title" className="text-xl font-bold text-foreground">
                알림
              </h2>
              <div className="mt-3 overflow-hidden rounded-card border border-border bg-card">
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
                    <NotificationRow
                      label="일정 알림"
                      checked={notifySettings.notifySchedule}
                      disabled={
                        pendingSettingKeys.includes('notifySchedule') || pushUnsupported
                      }
                      onCheckedChange={(checked) =>
                        handleNotificationChange('notifySchedule', checked)
                      }
                      divided
                    />
                    <button
                      type="button"
                      className="flex min-h-16 w-full items-center gap-3 border-t border-border px-4 text-left"
                      onClick={openMedicationTimeSheet}
                    >
                      <span className="flex min-w-0 flex-1 flex-col text-left">
                        <span className="text-[15px] font-bold text-foreground">알림 시간 설정</span>
                        <span className="truncate text-sm text-muted-foreground">
                          {[
                            notifySettings.morningMedicationTime,
                            notifySettings.lunchMedicationTime,
                            notifySettings.eveningMedicationTime,
                            notifySettings.bedtimeMedicationTime,
                          ].join(' · ')}
                        </span>
                      </span>
                      <ChevronRight
                        aria-hidden
                        className="size-5 shrink-0 text-disabled-foreground"
                      />
                    </button>
                  </>
                ) : (
                  <p className="p-4 text-sm text-muted-foreground">알림 설정을 불러오는 중...</p>
                )}
              </div>
              {pushUnsupported && (
                <p className="text-sm text-muted-foreground">
                  이 브라우저에서는 알림을 지원하지 않아요
                </p>
              )}
            </section>

            <button
              type="button"
              className="mt-1 h-11 min-h-touch w-full rounded-card border border-border bg-card px-4 text-sm font-bold text-muted-foreground transition-colors hover:bg-muted-bg"
              onClick={handleSignOut}
            >
              로그아웃
            </button>
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
            : pendingToggle === 'notifySchedule'
              ? '일정 알림을 보내드릴까요?'
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
      {notifySettings && timeDraft && (
        <MedicationTimeSettingsSheet
          open={timeSheetOpen}
          values={timeDraft}
          busy={notificationBusy}
          error={timeSaveError}
          onChange={updateMedicationTimeDraft}
          onSave={() => void saveMedicationTimes()}
          onCancel={cancelMedicationTimeSheet}
        />
      )}
    </div>
  );
}

function ManagementRow({
  label,
  value,
  onClick,
  divided = false,
}: {
  label: string;
  value: string;
  onClick: () => void;
  divided?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-16 w-full items-center gap-3 px-4 text-left ${
        divided ? 'border-t border-border' : ''
      }`}
    >
      <span className="flex-1 text-[15px] font-bold text-foreground">{label}</span>
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
    <div className={`flex min-h-16 items-center justify-between px-4 ${divided ? 'border-t border-border' : ''}`}>
      <label htmlFor={`notification-${label}`} className="text-base font-bold text-foreground">
        {label}
      </label>
      <Switch
        id={`notification-${label}`}
        aria-label={label}
        className="data-[state=unchecked]:bg-input"
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}
