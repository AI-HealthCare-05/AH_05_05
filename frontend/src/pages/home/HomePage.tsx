import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useSession } from '@/app/SessionContext';
import {
  getDoseRecords,
  getMedicationOverviews,
  saveDoseTaken,
  type DoseRecord,
  type DoseRecordRange,
  type MealSlot,
  type MedicationOverview,
  type SaveDoseTakenPayload,
} from '@/entities/medication';
import {
  getSupplementRanking,
  getSupplements,
  type SupplementRanking,
  type Supplement,
} from '@/entities/supplement';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  RxVitaFeatureCarousel,
  type TabKey,
} from '@/shared/ui';
import { LoginPromptSheet } from './LoginPromptSheet';
import { MedicationTimeline } from './MedicationTimeline';
import { SupplementRankingCard } from './SupplementRankingCard';
import { SupplementTodayCard } from './SupplementTodayCard';

export type MedicationHomeState = 'empty' | 'active' | 'ended';

interface HomePageProps {
  authenticatedOverride?: boolean;
  medicationState?: MedicationHomeState;
  medicationOverviewsLoader?: () => Promise<MedicationOverview[]>;
  /** DevGallery의 기존 단일 fixture를 위한 전환기 호환 prop. */
  medicationOverviewLoader?: () => Promise<MedicationOverview>;
  doseRecordsLoader?: (range: DoseRecordRange) => Promise<DoseRecord[]>;
  doseRecordSaver?: (payload: SaveDoseTakenPayload) => Promise<DoseRecord>;
}

interface DoseBatchChange {
  date: string;
  slot: MealSlot;
  taken: boolean;
  /** 선택한 처방 회차. 저장 API를 recordId마다 한 번 호출합니다. */
  recordIds: number[];
}

export function HomePage({
  authenticatedOverride,
  medicationState,
  medicationOverviewsLoader,
  medicationOverviewLoader,
  doseRecordsLoader = getDoseRecords,
  doseRecordSaver = saveDoseTaken,
}: HomePageProps) {
  const navigate = useNavigate();
  const { authenticated } = useSession();
  const isAuthenticated = authenticatedOverride ?? authenticated;
  const [loginPromptOpen, setLoginPromptOpen] = useState(false);
  const [medicationOverviews, setMedicationOverviews] = useState<MedicationOverview[] | null>(null);
  const [medicationLoadError, setMedicationLoadError] = useState<string | null>(null);
  const [doseRecords, setDoseRecords] = useState<DoseRecord[] | null>(null);
  const [doseLoadError, setDoseLoadError] = useState<string | null>(null);
  const [failedDoseChange, setFailedDoseChange] = useState<DoseBatchChange | null>(null);
  const [supplementRanking, setSupplementRanking] = useState<SupplementRanking | null>(null);
  const [registeredSupplements, setRegisteredSupplements] = useState<Supplement[]>([]);
  const [registeredProductIds, setRegisteredProductIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [supplementRegistrationPending, setSupplementRegistrationPending] = useState(false);
  const [supplementLoadError, setSupplementLoadError] = useState<string | null>(null);
  const [supplementReloadKey, setSupplementReloadKey] = useState(0);
  const [homeTab, setHomeTab] = useState<'medication' | 'supplement'>('medication');
  const [currentDate, setCurrentDate] = useState(() => localISODate(new Date()));
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getSupplementRanking()
      .then((ranking) => {
        if (!cancelled) {
          setSupplementRanking(ranking && ranking.items.length > 0 ? ranking : null);
        }
      })
      .catch(() => {
        if (!cancelled) setSupplementRanking(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setRegisteredSupplements([]);
      setRegisteredProductIds(new Set());
      setSupplementRegistrationPending(false);
      return;
    }

    let cancelled = false;
    setSupplementRegistrationPending(true);
    setSupplementLoadError(null);
    getSupplements()
      .then((result) => {
        if (!cancelled) {
          setRegisteredSupplements(result.items);
          setRegisteredProductIds(
            new Set(
              result.items.flatMap((supplement) =>
                supplement.productId === null ? [] : [supplement.productId],
              ),
            ),
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRegisteredSupplements([]);
          setRegisteredProductIds(new Set());
          setSupplementLoadError('영양제 목록을 불러오지 못했어요.');
        }
      })
      .finally(() => {
        if (!cancelled) setSupplementRegistrationPending(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, supplementReloadKey]);

  useEffect(() => {
    if (!isAuthenticated || (medicationState !== undefined && medicationState !== 'active')) {
      return;
    }

    let cancelled = false;
    setMedicationOverviews(null);
    setMedicationLoadError(null);
    const request = medicationOverviewsLoader
      ? medicationOverviewsLoader()
      : medicationOverviewLoader
        ? medicationOverviewLoader().then((overview) => [overview])
        : getMedicationOverviews();
    request
      .then((overviews) => {
        if (!cancelled) setMedicationOverviews(overviews);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMedicationLoadError(
            error instanceof Error ? error.message : '복약 정보를 불러오지 못했어요.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    isAuthenticated,
    medicationOverviewLoader,
    medicationOverviewsLoader,
    medicationState,
    reloadKey,
  ]);

  useEffect(() => {
    const withMedication = (medicationOverviews ?? []).filter(
      (overview) => overview.medications.length > 0,
    );
    if (!isAuthenticated || medicationOverviews === null) return;
    if (withMedication.length === 0) {
      setDoseRecords([]);
      return;
    }

    let cancelled = false;
    setDoseRecords(null);
    setDoseLoadError(null);
    const firstOverview = withMedication[0];
    const rawFrom = withMedication.reduce(
      (minimum, overview) => overview.start.date < minimum ? overview.start.date : minimum,
      firstOverview.start.date,
    );
    const to = withMedication.reduce(
      (maximum, overview) => overview.endDate > maximum ? overview.endDate : maximum,
      firstOverview.endDate,
    );
    const earliestDate = new Date(`${to}T00:00:00`);
    earliestDate.setDate(earliestDate.getDate() - 365);
    const earliest = localISODate(earliestDate);
    const from = rawFrom < earliest ? earliest : rawFrom;
    doseRecordsLoader({ from, to })
      .then((records) => {
        if (!cancelled) setDoseRecords(records);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDoseLoadError(
            error instanceof Error ? error.message : '복약 기록을 불러오지 못했어요.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentDate, doseRecordsLoader, isAuthenticated, medicationOverviews, reloadKey]);

  useEffect(() => {
    function refreshAfterDateChange() {
      const nextDate = localISODate(new Date());
      if (nextDate === currentDate) return;
      setCurrentDate(nextDate);
      setReloadKey((key) => key + 1);
    }
    window.addEventListener('focus', refreshAfterDateChange);
    return () => window.removeEventListener('focus', refreshAfterDateChange);
  }, [currentDate]);

  const resolvedMedicationState =
    medicationState ??
    (medicationOverviews ? medicationHomeStateFromOverviews(medicationOverviews) : null);
  const overviewDataReady =
    medicationState !== undefined && medicationState !== 'active'
      ? true
      : medicationOverviews !== null;
  const hasMedication = Boolean(
    medicationOverviews?.some((overview) => overview.medications.length > 0),
  );
  const pageDataReady = overviewDataReady && (!hasMedication || doseRecords !== null);
  const visibleSupplementRanking = supplementRanking
    ? {
        ...supplementRanking,
        items: supplementRanking.items.map((item) => ({
          ...item,
          alreadyRegistered: registeredProductIds.has(item.productId),
        })),
      }
    : null;

  function openFeature(key: Exclude<TabKey, 'home' | 'my'>) {
    if (!isAuthenticated) {
      setLoginPromptOpen(true);
      return;
    }
    navigate(TAB_ROUTES[key]);
  }

  function handleTabChange(key: TabKey) {
    if (key === 'home') return;
    if (key === 'my') {
      navigate('/my');
      return;
    }
    openFeature(key);
  }

  async function changeDose(
    change: DoseBatchChange,
    showUndo = true,
    knownChangedRecordIds?: number[],
  ): Promise<boolean> {
    if (!doseRecords) return false;
    const previousRecords = doseRecords;
    const changedRecordIds = knownChangedRecordIds ??
      change.recordIds.filter((recordId) => {
        const wasTaken = previousRecords.some(
          (record) =>
            record.date === change.date &&
            record.slot === change.slot &&
            record.recordId === recordId &&
            record.taken,
        );
        return wasTaken !== change.taken;
      });
    if (changedRecordIds.length === 0) return true;
    const appliedChange = { ...change, recordIds: changedRecordIds };
    setFailedDoseChange(null);
    setDoseRecords(updateDoseRecords(previousRecords, appliedChange));
    const results = await Promise.allSettled(
      changedRecordIds.map((recordId) =>
        doseRecordSaver({
          date: change.date,
          slot: change.slot,
          taken: change.taken,
          recordId,
        }),
      ),
    );
    const failedRecordIds = changedRecordIds.filter(
      (_recordId, index) => results[index]?.status === 'rejected',
    );
    if (failedRecordIds.length === 0) {
      if (showUndo) {
        toast.success(change.taken ? '복약을 기록했어요.' : '복약 기록을 취소했어요.', {
          action: {
            label: '되돌리기',
            onClick: () => {
              void changeDose(
                { ...appliedChange, taken: !change.taken },
                false,
                appliedChange.recordIds,
              );
            },
          },
        });
      }
      return true;
    }
    const failedChange = { ...appliedChange, recordIds: failedRecordIds };
    setDoseRecords((currentRecords) =>
      currentRecords
        ? restoreFailedDoseRecords(currentRecords, previousRecords, failedChange)
        : currentRecords,
    );
    setFailedDoseChange(failedChange);
    return false;
  }

  return (
    <div className="mx-auto flex h-dvh min-h-dvh w-full max-w-app flex-col overflow-hidden bg-background">
      {isAuthenticated ? (
        <Header
          title={
            <img src="/images/rxvita-logo-480.png" alt="RxVita" className="h-6 w-auto" />
          }
        />
      ) : (
        <header className="flex h-header shrink-0 items-center justify-between bg-card px-page-x">
          <h1 className="flex items-center">
            <img src="/images/rxvita-logo-480.png" alt="RxVita" className="h-6 w-auto" />
          </h1>
          <button
            type="button"
            className="min-h-touch text-sm font-bold text-primary-strong"
            onClick={() => navigate('/login')}
          >
            로그인
          </button>
        </header>
      )}

      <main className={`min-h-0 flex flex-1 flex-col overflow-y-auto px-page-x py-5 [scrollbar-gutter:stable] ${isAuthenticated ? 'gap-5' : 'gap-3'}`}>
        {isAuthenticated ? (
          <>
            <HomeSectionTabs activeTab={homeTab} onChange={setHomeTab} />
            {homeTab === 'medication' && (medicationLoadError || doseLoadError) ? (
              <Card title="복약 정보를 불러오지 못했어요">
                {medicationLoadError ?? doseLoadError}
              </Card>
            ) : homeTab === 'supplement' || (resolvedMedicationState && pageDataReady) ? (
              <>
                {homeTab === 'medication' && resolvedMedicationState ? (
                  <div
                    id="home-panel-medication"
                    role="tabpanel"
                    aria-labelledby="home-tab-medication"
                  >
                    <LoggedInMedicationContent
                      state={resolvedMedicationState}
                      overviews={medicationOverviews ?? []}
                      doseRecords={doseRecords ?? []}
                      currentDate={currentDate}
                      onDoseChange={(recordIds, slot, taken) => {
                        if (recordIds.length === 0) return;
                        return changeDose({ date: currentDate, slot, taken, recordIds });
                      }}
                      onMemo={() => navigate('/medications/notes/new')}
                      onUpload={() => navigate('/document-upload')}
                    />
                  </div>
                ) : (
                  <div
                    id="home-panel-supplement"
                    role="tabpanel"
                    aria-labelledby="home-tab-supplement"
                  >
                    <SupplementTodayCard
                      key={currentDate}
                      supplements={registeredSupplements}
                      date={currentDate}
                      loading={supplementRegistrationPending}
                      loadError={supplementLoadError}
                      onRetry={() => setSupplementReloadKey(key => key + 1)}
                      onBrowse={() => navigate('/supplements?tab=browse')}
                      onManage={(editSupplementId) => navigate('/supplements', { state: { editSupplementId } })}
                    />
                  </div>
                )}
                {hasMedication && doseRecords ? (
                  <section aria-labelledby="home-challenge-title" className="flex flex-col gap-3">
                    <h2 id="home-challenge-title" className="text-lg font-bold text-foreground">
                      챌린지
                    </h2>
                    <div
                      data-challenge-placeholder
                      className="flex h-[132px] items-center justify-center rounded-card bg-card shadow-card"
                    >
                      <p className="text-caption text-tertiary-foreground">준비 중이에요</p>
                    </div>
                  </section>
                ) : null}
              </>
            ) : (
              <div
                role="status"
                aria-label="복약 정보 불러오는 중"
                className="min-h-84 animate-pulse rounded-card bg-muted-bg"
              />
            )}
            {visibleSupplementRanking && (
              <SupplementRankingCard
                ranking={visibleSupplementRanking}
                registrationPending={supplementRegistrationPending}
                maxItems={3}
                onMore={() => navigate('/supplements?tab=browse')}
                onSelect={(productId) =>
                  navigate('/supplements', { state: { presetProductId: String(productId) } })
                }
              />
            )}
          </>
        ) : (
          <>
            <GuestMedicationPrompt onLogin={() => navigate('/login')} />
            {visibleSupplementRanking && (
              <SupplementRankingCard
                ranking={visibleSupplementRanking}
                registrationPending={false}
                maxItems={5}
                title="인기 영양제"
                subtitle="개인별 복용 추천이 아닌 일반 인기 정보예요"
              />
            )}
          </>
        )}
        {!isAuthenticated && <RxVitaFeatureCarousel autoAdvanceMs={3_000} size="compact" />}
      </main>

      <BottomTabbar
        active="home"
        onChange={handleTabChange}
        className="border-t border-border"
      />
      <LoginPromptSheet
        open={loginPromptOpen}
        onOpenChange={setLoginPromptOpen}
        onLogin={() => navigate('/login')}
      />
      <ErrorDialog
        open={failedDoseChange !== null}
        title="기록하지 못했어요"
        message="기록하지 못했어요. 다시 시도해주세요."
        onRetry={() => {
          const change = failedDoseChange;
          setFailedDoseChange(null);
          if (change) void changeDose(change);
        }}
      />
    </div>
  );
}

function HomeSectionTabs({
  activeTab,
  onChange,
}: {
  activeTab: 'medication' | 'supplement';
  onChange: (tab: 'medication' | 'supplement') => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="오늘의 홈 탭"
      className="grid grid-cols-2 rounded-input bg-muted-bg p-1"
    >
      {([
        ['medication', '오늘의 복약'],
        ['supplement', '오늘의 영양제'],
      ] as const).map(([tab, label]) => {
        const selected = activeTab === tab;
        return (
          <button
            key={tab}
            id={`home-tab-${tab}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={`home-panel-${tab}`}
            className={`min-h-touch rounded-input text-sm font-bold ${
              selected ? 'bg-card text-primary shadow-card' : 'text-muted-foreground'
            }`}
            onClick={() => onChange(tab)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function GuestMedicationPrompt({ onLogin }: { onLogin: () => void }) {
  return (
    <section aria-labelledby="guest-medication-title" className="flex flex-col gap-3">
      <div>
        <h2 id="guest-medication-title" className="text-2xl font-bold text-foreground">
          오늘의 복약
        </h2>
        <p className="mt-1 text-base text-muted-foreground">
          로그인하면 오늘 먹을 약을 바로 확인할 수 있어요
        </p>
      </div>
      <Card className="gap-3 p-5">
        <p className="text-lg font-bold text-foreground">복약 일정을 확인해보세요</p>
        <p>로그인하면 기록과 알림을 이어서 볼 수 있어요.</p>
        <Button onClick={onLogin}>로그인하고 시작하기</Button>
      </Card>
    </section>
  );
}

function LoggedInMedicationContent({
  state,
  overviews,
  doseRecords,
  currentDate,
  onDoseChange,
  onMemo,
  onUpload,
}: {
  state: MedicationHomeState;
  overviews: MedicationOverview[];
  doseRecords: DoseRecord[];
  currentDate: string;
  onDoseChange: (recordIds: number[], slot: MealSlot, taken: boolean) => void | Promise<boolean>;
  onMemo: () => void;
  onUpload: () => void;
}) {
  if (state === 'empty') {
    return (
      <Card title="오늘의 복약" className="gap-4 bg-primary-bg p-5">
        <p className="text-sm text-muted-foreground">
          복약정보를 등록하시면 시간에 맞춰 알림을 받으실 수 있어요.
        </p>
        <Button onClick={onUpload}>약봉투 등록하기</Button>
      </Card>
    );
  }

  if (state === 'ended') {
    return (
      <Card className="gap-4 p-5">
        <div>
          <p className="text-xl font-bold text-foreground">복용이 끝났어요</p>
          <p className="mt-1 text-sm text-muted-foreground">
            새 처방을 받았다면 약봉투를 다시 등록해 주세요.
          </p>
        </div>
        <Button variant="secondary" onClick={onUpload}>
          새 약봉투 등록
        </Button>
      </Card>
    );
  }

  return (
    <MedicationTimeline
      overviews={overviews}
      doseRecords={doseRecords}
      currentDate={currentDate}
      onDoseChange={onDoseChange}
      onMemo={onMemo}
    />
  );
}

function updateDoseRecords(records: DoseRecord[], change: DoseBatchChange): DoseRecord[] {
  const changedRecordIds = new Set(change.recordIds);
  const remaining = records.filter(
    (record) =>
      record.date !== change.date ||
      record.slot !== change.slot ||
      !changedRecordIds.has(record.recordId),
  );
  if (!change.taken) return remaining;
  return [
    ...remaining,
    ...change.recordIds.map((recordId) => ({
      date: change.date,
      slot: change.slot,
      taken: true,
      recordId,
    })),
  ];
}

function restoreFailedDoseRecords(
  currentRecords: DoseRecord[],
  previousRecords: DoseRecord[],
  failedChange: DoseBatchChange,
): DoseRecord[] {
  const failedRecordIds = new Set(failedChange.recordIds);
  const withoutFailedOptimisticRecords = currentRecords.filter(
    (record) =>
      record.date !== failedChange.date ||
      record.slot !== failedChange.slot ||
      !failedRecordIds.has(record.recordId),
  );
  const previousFailedRecords = previousRecords.filter(
    (record) =>
      record.date === failedChange.date &&
      record.slot === failedChange.slot &&
      failedRecordIds.has(record.recordId),
  );
  return [...withoutFailedOptimisticRecords, ...previousFailedRecords];
}

function localISODate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function medicationHomeStateFromOverviews(
  overviews: MedicationOverview[],
): MedicationHomeState {
  if (!overviews.some((overview) => overview.medications.length > 0)) return 'empty';
  return overviews.some((overview) => overview.daysRemaining > 0) ? 'active' : 'ended';
}
