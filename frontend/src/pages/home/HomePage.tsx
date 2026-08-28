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
} from '@/entities/supplement';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  PokeFeatureCarousel,
  type TabKey,
} from '@/shared/ui';
import { LoginPromptSheet } from './LoginPromptSheet';
import { MedicationRecordGrid } from './MedicationRecordGrid';
import { MedicationTimeline } from './MedicationTimeline';
import { SupplementRankingCard } from './SupplementRankingCard';

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
  recordIds: number[];
  date: string;
  slot: MealSlot;
  taken: boolean;
}

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

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
  const [animatedDoseKey, setAnimatedDoseKey] = useState<string | null>(null);
  const [supplementRanking, setSupplementRanking] = useState<SupplementRanking | null>(null);
  const [registeredProductIds, setRegisteredProductIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [supplementRegistrationPending, setSupplementRegistrationPending] = useState(false);
  const [currentDate, setCurrentDate] = useState(() => localISODate(new Date()));
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!isAuthenticated) {
      setSupplementRanking(null);
      setRegisteredProductIds(new Set());
      setSupplementRegistrationPending(false);
      return;
    }

    let cancelled = false;
    setSupplementRegistrationPending(true);
    getSupplementRanking()
      .then((ranking) => {
        if (!cancelled) {
          setSupplementRanking(ranking && ranking.items.length > 0 ? ranking : null);
        }
      })
      .catch(() => {
        if (!cancelled) setSupplementRanking(null);
      });
    getSupplements()
      .then((supplements) => {
        if (!cancelled) {
          setRegisteredProductIds(
            new Set(
              supplements.flatMap((supplement) =>
                supplement.productId === null ? [] : [supplement.productId],
              ),
            ),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setRegisteredProductIds(new Set());
      })
      .finally(() => {
        if (!cancelled) setSupplementRegistrationPending(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

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
    Promise.all(
      withMedication.map((overview) =>
        doseRecordsLoader({
          recordId: overview.recordId,
          from: overview.start.date,
          to: overview.endDate,
        }),
      ),
    )
      .then((records) => {
        if (!cancelled) setDoseRecords(records.flat());
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
  const visibleSupplementRanking = isAuthenticated && supplementRanking
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

  async function changeDose(change: DoseBatchChange, showUndo = true) {
    if (!doseRecords || change.recordIds.length === 0) return;
    const previousRecords = doseRecords;
    setFailedDoseChange(null);
    setAnimatedDoseKey(change.taken ? doseKey(change.date, change.slot) : null);
    setDoseRecords(updateDoseRecords(previousRecords, change));
    try {
      await Promise.all(
        change.recordIds.map((recordId) => doseRecordSaver({ ...change, recordId })),
      );
      if (showUndo) {
        toast.success(change.taken ? '복약을 기록했어요.' : '복약 기록을 취소했어요.', {
          action: {
            label: '되돌리기',
            onClick: () => {
              void changeDose({ ...change, taken: !change.taken }, false);
            },
          },
        });
      }
    } catch {
      setDoseRecords(previousRecords);
      setAnimatedDoseKey(null);
      setFailedDoseChange(change);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      {isAuthenticated ? (
        <Header title="포케" />
      ) : (
        <header className="flex h-header shrink-0 items-center justify-between bg-card px-page-x">
          <h1 className="text-xl font-bold text-foreground">포케</h1>
          <button
            type="button"
            className="min-h-touch text-sm font-bold text-primary-strong"
            onClick={() => navigate('/login')}
          >
            로그인
          </button>
        </header>
      )}

      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        <PokeFeatureCarousel autoAdvanceMs={3_000} size="compact" />

        {visibleSupplementRanking && (
          <SupplementRankingCard
            ranking={visibleSupplementRanking}
            registrationPending={supplementRegistrationPending}
            onSelect={(productId) =>
              navigate('/supplements', { state: { presetProductId: String(productId) } })
            }
          />
        )}

        {isAuthenticated ? (
          medicationLoadError || doseLoadError ? (
            <Card title="복약 정보를 불러오지 못했어요">
              {medicationLoadError ?? doseLoadError}
            </Card>
          ) : resolvedMedicationState && pageDataReady ? (
            <>
              <LoggedInMedicationContent
                state={resolvedMedicationState}
                overviews={medicationOverviews ?? []}
                doseRecords={doseRecords ?? []}
                currentDate={currentDate}
                onDoseChange={(recordIds, slot, taken) =>
                  void changeDose({ recordIds, date: currentDate, slot, taken })
                }
                onUpload={() => navigate('/document-upload')}
              />
              {hasMedication && doseRecords ? (
                <MedicationRecordGrid
                  overviews={medicationOverviews ?? []}
                  records={doseRecords}
                  now={new Date()}
                  animatedRecordKey={animatedDoseKey}
                  onMarkTaken={(date, slot, recordIds) =>
                    void changeDose({ recordIds, date, slot, taken: true })
                  }
                />
              ) : null}
            </>
          ) : (
            <div
              role="status"
              aria-label="복약 정보 불러오는 중"
              className="min-h-84 animate-pulse rounded-card bg-muted-bg"
            />
          )
        ) : null}

        {!isAuthenticated && (
          <p className="mt-auto py-4 text-center text-sm text-disabled-foreground">
            기능을 쓰려면 로그인이 필요해요
          </p>
        )}
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

function LoggedInMedicationContent({
  state,
  overviews,
  doseRecords,
  currentDate,
  onDoseChange,
  onUpload,
}: {
  state: MedicationHomeState;
  overviews: MedicationOverview[];
  doseRecords: DoseRecord[];
  currentDate: string;
  onDoseChange: (recordIds: number[], slot: MealSlot, taken: boolean) => void;
  onUpload: () => void;
}) {
  if (state === 'empty') {
    return (
      <Card className="gap-4 bg-primary-bg p-5">
        <div>
          <p className="text-xl font-bold text-foreground">약봉투를 등록해 주세요</p>
          <p className="mt-1 text-sm text-muted-foreground">
            사진 한 장이면 오늘부터 알림을 드릴게요.
          </p>
        </div>
        <Button onClick={onUpload}>약봉투 등록</Button>
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
    />
  );
}

function updateDoseRecords(records: DoseRecord[], change: DoseBatchChange): DoseRecord[] {
  const recordIds = new Set(change.recordIds);
  const remaining = records.filter(
    (record) =>
      !recordIds.has(record.recordId) ||
      record.date !== change.date ||
      record.slot !== change.slot,
  );
  if (!change.taken) return remaining;
  return [
    ...remaining,
    ...change.recordIds.map((recordId) => ({
      recordId,
      date: change.date,
      slot: change.slot,
      taken: true,
    })),
  ];
}

function doseKey(date: string, slot: MealSlot): string {
  return `${date}:${slot}`;
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
