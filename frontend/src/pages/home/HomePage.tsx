import { Fragment, useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useSession } from '@/app/SessionContext';
import {
  getDoseRecords,
  getMedicationOverview,
  saveDoseTaken,
  type DoseRecord,
  type DoseRecordRange,
  type MealSlot,
  type MedicationOverview,
  type MedicationOverviewItem,
  type SaveDoseTakenPayload,
} from '@/entities/medication';
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

export type MedicationHomeState = 'empty' | 'active' | 'ended';

interface HomePageProps {
  authenticatedOverride?: boolean;
  medicationState?: MedicationHomeState;
  medicationOverviewLoader?: () => Promise<MedicationOverview>;
  doseRecordsLoader?: (range: DoseRecordRange) => Promise<DoseRecord[]>;
  doseRecordSaver?: (payload: SaveDoseTakenPayload) => Promise<DoseRecord>;
}

const SLOT_ORDER: MealSlot[] = ['morning', 'lunch', 'evening', 'bedtime'];
const SLOT_LABEL: Record<MealSlot, string> = {
  morning: '아침',
  lunch: '점심',
  evening: '저녁',
  bedtime: '취침 전',
};

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
  medicationOverviewLoader = getMedicationOverview,
  doseRecordsLoader = getDoseRecords,
  doseRecordSaver = saveDoseTaken,
}: HomePageProps) {
  const navigate = useNavigate();
  const { authenticated } = useSession();
  const isAuthenticated = authenticatedOverride ?? authenticated;
  const [loginPromptOpen, setLoginPromptOpen] = useState(false);
  const [medicationOverview, setMedicationOverview] = useState<MedicationOverview | null>(null);
  const [medicationLoadError, setMedicationLoadError] = useState<string | null>(null);
  const [doseRecords, setDoseRecords] = useState<DoseRecord[] | null>(null);
  const [doseLoadError, setDoseLoadError] = useState<string | null>(null);
  const [failedDoseChange, setFailedDoseChange] = useState<SaveDoseTakenPayload | null>(null);
  const [currentDate, setCurrentDate] = useState(() => localISODate(new Date()));
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (
      !isAuthenticated ||
      (medicationState !== undefined && medicationState !== 'active')
    ) return;

    let cancelled = false;
    setMedicationOverview(null);
    setMedicationLoadError(null);
    medicationOverviewLoader()
      .then((overview) => {
        if (!cancelled) setMedicationOverview(overview);
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
  }, [isAuthenticated, medicationOverviewLoader, medicationState, reloadKey]);

  useEffect(() => {
    if (!isAuthenticated || !medicationOverview || medicationOverview.medications.length === 0) {
      return;
    }
    let cancelled = false;
    setDoseRecords(null);
    setDoseLoadError(null);
    doseRecordsLoader({ from: medicationOverview.start.date, to: medicationOverview.endDate })
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
  }, [currentDate, doseRecordsLoader, isAuthenticated, medicationOverview, reloadKey]);

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
    (medicationOverview ? medicationHomeStateFromOverview(medicationOverview) : null);

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

  async function changeDose(payload: SaveDoseTakenPayload, showUndo = true) {
    if (!doseRecords) return;
    const previousRecords = doseRecords;
    setFailedDoseChange(null);
    setDoseRecords(updateDoseRecords(previousRecords, payload));
    try {
      await doseRecordSaver(payload);
      if (showUndo) {
        toast.success(payload.taken ? '복약을 기록했어요.' : '복약 기록을 취소했어요.', {
          action: {
            label: '되돌리기',
            onClick: () => {
              void changeDose({ ...payload, taken: !payload.taken }, false);
            },
          },
        });
      }
    } catch {
      setDoseRecords(previousRecords);
      setFailedDoseChange(payload);
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
        {isAuthenticated ? (
          medicationLoadError || doseLoadError ? (
            <Card title="복약 정보를 불러오지 못했어요">
              {medicationLoadError ?? doseLoadError}
            </Card>
          ) : resolvedMedicationState &&
            (resolvedMedicationState !== 'active' || medicationOverview) &&
            (!medicationOverview?.medications.length || doseRecords !== null) ? (
            <>
              <LoggedInHero
                state={resolvedMedicationState}
                overview={medicationOverview}
                doseRecords={doseRecords ?? []}
                currentDate={currentDate}
                onDoseChange={(slot, taken) =>
                  void changeDose({ date: currentDate, slot, taken })
                }
                onUpload={() => navigate('/document-upload')}
              />
              {medicationOverview?.medications.length && doseRecords ? (
                <MedicationRecordGrid
                  overview={medicationOverview}
                  records={doseRecords}
                  now={new Date()}
                  onMarkTaken={(date, slot) => void changeDose({ date, slot, taken: true })}
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
        ) : (
          <PokeFeatureCarousel />
        )}

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
          const payload = failedDoseChange;
          setFailedDoseChange(null);
          if (payload) void changeDose(payload);
        }}
      />
    </div>
  );
}

function LoggedInHero({
  state,
  overview,
  doseRecords,
  currentDate,
  onDoseChange,
  onUpload,
}: {
  state: MedicationHomeState;
  overview: MedicationOverview | null;
  doseRecords: DoseRecord[];
  currentDate: string;
  onDoseChange: (slot: MealSlot, taken: boolean) => void;
  onUpload: () => void;
}) {
  if (state === 'empty') {
    return (
      <Card className="gap-4 bg-primary-bg p-5">
        <div>
          <p className="text-xl font-bold text-foreground">약봉투를 등록해 주세요</p>
          <p className="mt-1 text-sm text-muted-foreground">사진 한 장이면 오늘부터 알림을 드릴게요.</p>
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
          <p className="mt-1 text-sm text-muted-foreground">새 처방을 받았다면 약봉투를 다시 등록해 주세요.</p>
        </div>
        <Button variant="secondary" onClick={onUpload}>
          새 약봉투 등록
        </Button>
      </Card>
    );
  }

  if (!overview) return null;

  const timeline = medicationTimeline(overview, new Date(), currentDate, doseRecords);
  const dayNumber = Math.max(1, daysBetween(overview.start.date, currentDate) + 1);
  const allTaken = timeline.length > 0 && timeline.every((item) => item.status === 'completed');

  return (
    <section className="flex flex-col gap-3" aria-labelledby="today-medication-title">
      <div className="flex items-center justify-between">
        <h2 id="today-medication-title" className="text-xl font-bold text-foreground">
          오늘의 복약
        </h2>
        <span className="text-base text-muted-foreground tnum">
          {dayNumber}일째 · {overview.daysRemaining}일 남음
        </span>
      </div>
      <div
        role="group"
        aria-label="하루 복약 시간표"
        className="overflow-hidden rounded-card bg-card shadow-card"
      >
        {allTaken && (
          <p className="px-4 pt-4 text-base font-bold text-foreground">오늘 다 드셨어요</p>
        )}
        {timeline.map((item, index) => (
          <Fragment key={item.slot}>
            {index > 0 && <div className="mx-4 border-t border-border" />}
            <TimelineItem item={item} onDoseChange={onDoseChange} />
          </Fragment>
        ))}
      </div>
    </section>
  );
}

type TimelineStatus = 'completed' | 'current' | 'next' | 'missed';

interface TimelineItemData {
  slot: MealSlot;
  label: string;
  time: string;
  medications: MedicationOverviewItem[];
  status: TimelineStatus;
  expanded: boolean;
}

function TimelineItem({
  item,
  onDoseChange,
}: {
  item: TimelineItemData;
  onDoseChange: (slot: MealSlot, taken: boolean) => void;
}) {
  if (item.status === 'completed') {
    return (
      <button
        type="button"
        aria-label={`완료한 복약 ${item.label}`}
        className="flex min-h-12 w-full items-center gap-3 px-4 py-2 text-left text-disabled-foreground"
        onClick={() => onDoseChange(item.slot, false)}
      >
        <span className="flex size-5.5 shrink-0 items-center justify-center rounded-pill bg-primary text-card">
          <Check aria-hidden className="size-4" />
        </span>
        <span className="text-base tnum">
          {item.label} {item.time}
        </span>
        <span className="ml-auto text-sm tnum">{item.medications.length}개 먹었어요</span>
      </button>
    );
  }

  const ariaLabel =
    item.status === 'current'
      ? '현재 복약'
      : item.status === 'missed'
        ? `놓친 복약 ${item.label}`
        : `다음 복약 ${item.label}`;

  if (!item.expanded) {
    return (
      <div
        role="group"
        aria-label={ariaLabel}
        className={`flex min-h-12 items-center gap-3 px-4 py-2 ${
          item.status === 'missed' ? 'text-muted-foreground' : 'text-foreground'
        }`}
      >
        <span className="size-5.5 shrink-0 rounded-pill border border-border" />
        <span className="text-base tnum">
          {item.label} {item.time}
        </span>
        <span className="ml-auto text-base text-muted-foreground tnum">
          {item.medications.length}개
        </span>
      </div>
    );
  }

  const current = item.status === 'current';
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`flex flex-col px-4 py-4 ${current ? 'bg-primary-bg' : 'bg-card'}`}
    >
      <div className="flex items-center gap-3">
        <span
          className={`size-5.5 shrink-0 rounded-pill ${
            current ? 'border-2 border-primary' : 'border border-border'
          }`}
        />
        <p className="text-metric font-bold text-foreground tnum">
          {item.label} {item.time}
        </p>
        <span
          className={`ml-auto rounded-pill px-3 py-1 text-sm font-bold ${
            current
              ? 'bg-primary text-card'
              : 'bg-muted-bg text-muted-foreground'
          }`}
        >
          {current ? '지금' : '다음'}
        </span>
      </div>
      <ul
        aria-label={current ? '지금 먹을 약' : '다음에 먹을 약'}
        className="ml-8.5 mt-2 flex flex-col gap-1"
      >
        {item.medications.map((medication) => (
          <li key={medication.medicationId} className="text-base text-foreground">
            {medication.name}{' '}
            <span className="text-muted-foreground">{medication.dose}</span>
          </li>
        ))}
      </ul>
      <Button
        variant={current ? 'primary' : 'secondary'}
        fullWidth={false}
        className="ml-8.5 mt-3 w-auto gap-2 text-base tnum"
        onClick={() => onDoseChange(item.slot, true)}
      >
        <Check aria-hidden className="size-5" />
        {item.medications.length}개 먹었어요
      </Button>
    </div>
  );
}

function medicationTimeline(
  overview: MedicationOverview,
  now: Date,
  currentDate: string,
  doseRecords: DoseRecord[],
): TimelineItemData[] {
  const todayOffset = daysBetween(overview.start.date, currentDate);
  const medications = overview.medications.filter(
    (medication) =>
      !medication.asNeeded && todayOffset >= 0 && todayOffset < medication.days,
  );
  const items = SLOT_ORDER.map((slot) => ({
    slot,
    label: SLOT_LABEL[slot],
    time: overview.mealTimes[slot],
    medications: medications.filter((medication) => medication.slots.includes(slot)),
  }))
    .filter((item) => item.medications.length > 0)
    .sort((left, right) => timeInMinutes(left.time) - timeInMinutes(right.time));
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  let currentIndex = -1;
  items.forEach((item, index) => {
    if (timeInMinutes(item.time) <= nowMinutes) currentIndex = index;
  });
  const takenSlots = new Set(
    doseRecords
      .filter((record) => record.date === currentDate && record.taken)
      .map((record) => record.slot),
  );
  const currentSlot = items[currentIndex]?.slot;
  const expandedIndex =
    currentSlot && !takenSlots.has(currentSlot)
      ? currentIndex
      : items.findIndex((item, index) => index > currentIndex && !takenSlots.has(item.slot));

  return items.map((item, index) => ({
    ...item,
    status: takenSlots.has(item.slot)
      ? 'completed'
      : index === currentIndex
        ? 'current'
        : index < currentIndex
          ? 'missed'
          : 'next',
    expanded: index === expandedIndex,
  }));
}

function updateDoseRecords(
  records: DoseRecord[],
  payload: SaveDoseTakenPayload,
): DoseRecord[] {
  const withoutSlot = records.filter(
    (record) => record.date !== payload.date || record.slot !== payload.slot,
  );
  return payload.taken ? [...withoutSlot, { ...payload }] : withoutSlot;
}

function timeInMinutes(value: string): number {
  const [hours = '0', minutes = '0'] = value.split(':');
  return Number(hours) * 60 + Number(minutes);
}

function daysBetween(from: string, to: string): number {
  const fromDate = localDate(from);
  const toDate = localDate(to);
  return Math.round((toDate.getTime() - fromDate.getTime()) / 86_400_000);
}

function localDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function localISODate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function medicationHomeStateFromOverview(overview: MedicationOverview): MedicationHomeState {
  if (overview.medications.length === 0) return 'empty';
  return overview.daysRemaining > 0 ? 'active' : 'ended';
}
