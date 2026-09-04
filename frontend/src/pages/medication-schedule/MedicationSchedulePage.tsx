import { useEffect, useState, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  Button,
  Card,
  ErrorDialog,
  Header,
  Input,
  NotifyPermissionDialog,
  RegistrationProgress,
  TimePickerSheet,
} from '@/shared/ui';
import { cn } from '@/shared/lib/cn';
import {
  getMedicationSchedule,
  saveMedicationSchedule,
  type MealSlot,
  type MealTimes,
  type MedicationSchedule,
  type MedicationStartPoint,
  type ScheduleMedication,
} from '@/entities/medication';
import {
  getNotifySettings,
  updateNotifySettings,
  type NotifySettings,
  type UpdateNotifySettingsPayload,
} from '@/entities/settings';
import {
  getPushPermission,
  requestPushPermission,
  type PushPermission,
} from '@/shared/push/permission';
import { registerPushNotifications } from '@/shared/push/register';
import {
  DEFAULT_MEAL_TIMES,
  MEAL_SLOTS,
  SLOT_ORDER,
  defaultSlotsFor,
  exceedsSlotCapacity,
  isMealTimeOrderValid,
  needsSlotConfirmation,
} from '@/shared/model/mealSlot';

/**
 * REQ-CARE-003 · 통합 슬롯 구조 (2026-08-14 기획 결정)
 *
 * 사용자는 아침약·점심약·저녁약·취침약 시각 4개만 정하고, 약은 "어느 시간에 먹는지"만
 * 가집니다. 약이 4개여도 시각 입력은 4개로 끝납니다.
 *
 * **Figma `09`(125:50)는 아직 옛 구조(약별 시각)입니다.** 이 화면은 작업지시 문서와
 * 이후 피드백이 기준이며 Figma 수정은 별도 작업으로 뒤따릅니다. `09-A 시간 선택` 시트는
 * 구조가 바뀌지 않아 그대로 씁니다(description prop만 다르게 넘깁니다).
 */
interface ScheduleLocationState {
  recordId?: number;
  dispensedDate?: string;
  draftStartDate?: string;
  ocrJobId?: string;
  registrationFlow?: boolean;
  episodeAlias?: string;
}

interface MedicationSchedulePageProps {
  scheduleOverride?: MedicationSchedule;
  defaultRecordId?: number;
  scheduleSaver?: typeof saveMedicationSchedule;
  notifySettingsLoader?: () => Promise<NotifySettings>;
  notifySettingsUpdater?: (payload: UpdateNotifySettingsPayload) => Promise<NotifySettings>;
  permissionReader?: () => PushPermission;
  permissionRequester?: () => Promise<PushPermission>;
  pushRegistrar?: () => Promise<void>;
}

/** info = 아직 안 고른 것(안내), error = 잘못 고른 것(오류). */
interface Blocker {
  message: string;
  tone: 'info' | 'error';
}

function blockerClass(tone: Blocker['tone']): string {
  return tone === 'error' ? 'text-sm text-danger-strong' : 'text-sm text-muted-foreground';
}

/**
 * 오늘 날짜(YYYY-MM-DD). "처음 약을 언제부터 드셨나요?"의 기본값으로만 씁니다.
 *
 * 이 프로젝트는 날짜 계산을 서버에서 하기로 정했지만(기기 시간 의존을 피하려고),
 * 이건 계산이 아니라 사용자가 화면에서 보고 고칠 수 있는 입력값의 초기값입니다.
 * 저장되는 값은 어디까지나 사용자가 확인한 날짜입니다.
 */
function toISODate(date: Date): string {
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${m}-${d}`;
}

function todayISO(): string {
  return toISODate(new Date());
}

/** todayISO() 와 같은 로컬 기준으로 n년 전 날짜를 만듭니다. */
function isoYearsAgo(years: number): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() - years);
  return toISODate(date);
}

/**
 * 복용 시작일 하한 = 오늘 − 2년.
 *
 * **업무 규칙이 아니라 연도 오타 방어입니다.** 2016 같은 오입력은 걸러내면서 과거 기록
 * 등록은 막지 않는 선으로 잡았습니다. 07 퇴원일에는 하한이 없어 몇 달 전 입원기록도
 * 등록할 수 있는데, 여기 하한을 좁게 잡으면 그 흐름에서 사실대로 복용 시작일을 넣는 것이
 * 막혀 사용자가 거짓 날짜를 넣어야 통과하게 됩니다(이전 90일 하한이 그랬습니다).
 *
 * 상한은 오늘입니다 — "언제부터 드셨나요"는 과거를 묻는 질문이라 미래는 답이 될 수 없고,
 * 활성 기간이 `복용시작일 + 처방일수 - 1`로 계산되므로 미래 날짜를 넣으면 기간이 앞으로
 * 밀려 홈에 아무것도 안 뜨면서 오류도 나지 않습니다.
 */
const MIN_START_DATE_YEARS = 2;

/**
 * 약 카드 2행. `timing` 은 nullable 이 아니지만 실 OCR 이 빈 문자열을 보낼 수 있어
 * 빈 값을 걸러냅니다 — 그러지 않으면 "1일 2회 · " 처럼 구분자만 덜렁 남습니다.
 * 목업 4건은 전부 값이 차 있어서 화면으로는 드러나지 않고, 실 API 를 붙이는 순간 나타납니다.
 * (MedicationEditDialog 의 frequencyText 와 같은 방식)
 */
function medicationMetaText(med: ScheduleMedication): string {
  if (med.timesPerDay === null) return '필요 시';
  return [`1일 ${med.timesPerDay}회`, med.timing.trim()].filter(Boolean).join(' · ');
}

/** "2026-08-14" + lunch → "8월 14일 점심약" */
function formatStartPoint(date: string, slot: MealSlot): string {
  const label = MEAL_SLOTS.find((s) => s.value === slot)?.label ?? '';
  const [, month, day] = date.split('-');
  if (!month || !day) return label;
  return `${Number(month)}월 ${Number(day)}일 ${label}`;
}

function parseRecordId(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export function MedicationSchedulePage({
  scheduleOverride,
  defaultRecordId,
  scheduleSaver = saveMedicationSchedule,
  notifySettingsLoader = getNotifySettings,
  notifySettingsUpdater = updateNotifySettings,
  permissionReader = getPushPermission,
  permissionRequester = requestPushPermission,
  pushRegistrar = registerPushNotifications,
}: MedicationSchedulePageProps = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ScheduleLocationState | null) ?? {};
  const searchParams = new URLSearchParams(location.search);
  const queryRecordId = parseRecordId(searchParams.get('recordId'));
  const queryOcrJobId = searchParams.get('ocrJobId')?.trim() || null;
  const recordId = state.recordId ?? queryRecordId ?? defaultRecordId ?? (scheduleOverride ? 12 : null);
  const dispensedDate = state.dispensedDate;
  const draftStartDate = state.draftStartDate;
  const ocrJobId = state.ocrJobId ?? queryOcrJobId;
  const registrationFlow = state.registrationFlow === true;

  const [schedule, setSchedule] = useState<MedicationSchedule | null>(null);
  const [mealTimes, setMealTimes] = useState<MealTimes>(DEFAULT_MEAL_TIMES);
  /** medicationId → 시간대 */
  const [slots, setSlots] = useState<Record<number, MealSlot[]>>({});
  const [startDate, setStartDate] = useState('');
  const [startDateEdited, setStartDateEdited] = useState(draftStartDate !== undefined);
  const [startSlot, setStartSlot] = useState<MealSlot | null>(null);
  /** 시각 편집 대상 시간대 */
  const [editingSlot, setEditingSlot] = useState<MealSlot | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  /** 저장 실패 팝업. 재시도가 같은 인자로 다시 보내야 해서 콜백을 함께 담습니다. */
  const [saveError, setSaveError] = useState<{ message: string; retry: () => void } | null>(null);
  const [notifyError, setNotifyError] = useState<{
    message: string;
    retry: () => void;
  } | null>(null);
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);
  const [permissionBusy, setPermissionBusy] = useState(false);
  const [savedMealTimes, setSavedMealTimes] = useState<MealTimes | null>(null);
  const [timeOrderError, setTimeOrderError] = useState(false);

  useEffect(() => {
    const applySchedule = (data: MedicationSchedule) => {
      setSchedule(data);
      setMealTimes(data.mealTimes ?? DEFAULT_MEAL_TIMES);
      // 저장값 우선. 최초 등록이면 바로 전 화면에서 확인한 조제일을 채워 사용자가 고칩니다.
      setStartDate(data.start?.date ?? draftStartDate ?? dispensedDate ?? todayISO());
      setStartDateEdited(data.start === null && draftStartDate !== undefined);
      setStartSlot(data.start?.slot ?? null);

      const next: Record<number, MealSlot[]> = {};
      for (const med of data.medications) {
        next[med.medicationId] =
          med.slots.length > 0 ? med.slots : defaultSlotsFor(med.timesPerDay, med.timing);
      }
      setSlots(next);
    };

    if (scheduleOverride) {
      applySchedule(scheduleOverride);
      return;
    }

    if (recordId === null) return;

    let cancelled = false;
    getMedicationSchedule(recordId)
      .then((data) => {
        if (cancelled) return;
        applySchedule(data);
      })
      // catch 가 없으면 실 API 오류에서 schedule 이 null 로 남아 "불러오는 중"에
      // 영구히 멈춥니다. 로딩과 실패는 화면에서 구분되어야 합니다.
      .catch((error: unknown) => {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : '복약 정보를 불러오지 못했어요.');
      });
    return () => {
      cancelled = true;
    };
  }, [dispensedDate, draftStartDate, recordId, scheduleOverride]);

  /** 토글. SLOT_ORDER 순서를 유지해 담습니다 — 클릭 순서대로 쌓으면 재진입 시 표시가 흔들립니다. */
  function toggleSlot(medicationId: number, slot: MealSlot) {
    setSlots((prev) => {
      const current = prev[medicationId] ?? [];
      const nextSet = new Set(current);
      if (nextSet.has(slot)) {
        nextSet.delete(slot);
      } else {
        nextSet.add(slot);
      }
      return { ...prev, [medicationId]: SLOT_ORDER.filter((s) => nextSet.has(s)) };
    });
  }

  function applyTime(time: string) {
    if (!editingSlot) return;
    const nextMealTimes = { ...mealTimes, [editingSlot]: time };
    if (!isMealTimeOrderValid(nextMealTimes)) {
      setTimeOrderError(true);
      return;
    }
    setMealTimes(nextMealTimes);
    setEditingSlot(null);
  }

  /** 07 퇴원일과 같은 이유로, 입력칸 아무 곳이나 눌러도 달력이 열리게 합니다. */
  function openDatePicker(event: MouseEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (typeof input.showPicker !== 'function') return;
    try {
      input.showPicker();
    } catch {
      // 미지원·제스처 아님 — 기본 동작에 맡깁니다.
    }
  }

  /**
   * 저장 실패는 사용자가 버튼을 눌러 생긴 실패고 뒤에 입력 화면이 그대로 남아 있으므로
   * 팝업으로 알립니다. catch 가 없으면 finally 가 saving 만 풀고 아무 표시가 없어서,
   * 사용자는 저장된 줄 압니다.
   *
   * **실패하면 navigate 에 도달하지 않습니다** — navigate 를 try 안 await 뒤에 두어
   * 요청이 throw 하면 그 줄을 건너뛰고 catch 로 갑니다.
   *
   * 재시도가 같은 인자로 다시 보내야 해서, 실패 시 인자를 통째로 클로저에 담아둡니다.
   */
  async function persist(
    start: MedicationStartPoint,
    times: MealTimes,
    payloadSlots: Record<number, MealSlot[]>,
  ) {
    if (!schedule || recordId === null) return;
    setSaving(true);
    setSaveError(null);
    try {
      await scheduleSaver(recordId, {
        start,
        mealTimes: times,
        medications: schedule.medications
          .filter((m) => m.timesPerDay !== null)
          .map((m) => ({ medicationId: m.medicationId, slots: payloadSlots[m.medicationId] ?? [] })),
      });
      setSavedMealTimes(times);
      await continueAfterScheduleSave(times);
    } catch (error: unknown) {
      setSaveError({
        message: error instanceof Error ? error.message : '복약 시간을 저장하지 못했어요.',
        retry: () => persist(start, times, payloadSlots),
      });
    } finally {
      setSaving(false);
    }
  }

  function finishScheduleFlow() {
    // 저장이 끝난 흐름으로 뒤로가기를 해도 시간 설정 화면으로 돌아오지 않게 교체합니다.
    navigate('/home', { replace: true });
  }

  function showNotifyError(error: unknown, retry: () => void) {
    setNotifyError({
      message: error instanceof Error ? error.message : '알림 설정을 저장하지 못했어요.',
      retry,
    });
  }

  async function enableInitialNotifications() {
    setPermissionBusy(true);
    setNotifyError(null);
    try {
      await pushRegistrar();
      await notifySettingsUpdater({
        notifyMedication: true,
        notifySupplement: true,
      });
      finishScheduleFlow();
    } catch (error: unknown) {
      showNotifyError(error, () => void enableInitialNotifications());
    } finally {
      setPermissionBusy(false);
    }
  }

  async function recordInitialNotificationChoice() {
    setPermissionBusy(true);
    setNotifyError(null);
    try {
      // notifyConsentedAt은 서버 응답 전용입니다. 빈 부분 수정 요청으로 최초 선택만 기록합니다.
      await notifySettingsUpdater({});
      finishScheduleFlow();
    } catch (error: unknown) {
      showNotifyError(error, () => void recordInitialNotificationChoice());
    } finally {
      setPermissionBusy(false);
    }
  }

  async function continueAfterScheduleSave(times: MealTimes) {
    if (permissionReader() === 'unsupported') {
      finishScheduleFlow();
      return;
    }
    try {
      const settings = await notifySettingsLoader();
      if (settings.notifyConsentedAt) {
        finishScheduleFlow();
        return;
      }

      const permission = permissionReader();
      if (permission === 'default') {
        setSavedMealTimes(times);
        setPermissionDialogOpen(true);
        return;
      }
      if (permission === 'granted') {
        await enableInitialNotifications();
        return;
      }
      await recordInitialNotificationChoice();
    } catch (error: unknown) {
      showNotifyError(error, () => void continueAfterScheduleSave(times));
    }
  }

  async function handlePermissionAccept() {
    setPermissionBusy(true);
    let permission: PushPermission;
    try {
      permission = await permissionRequester();
    } catch (error: unknown) {
      setPermissionDialogOpen(false);
      setPermissionBusy(false);
      showNotifyError(error, () => void handlePermissionAccept());
      return;
    }
    setPermissionDialogOpen(false);
    setPermissionBusy(false);

    if (permission === 'granted') {
      await enableInitialNotifications();
      return;
    }
    // 브라우저 프롬프트에서 차단하거나 닫은 것은 작업 실패가 아닙니다.
    await recordInitialNotificationChoice();
  }

  async function handlePermissionDismiss() {
    setPermissionDialogOpen(false);
    await recordInitialNotificationChoice();
  }

  function handleSave() {
    if (!startSlot || !startDate) return;
    void persist({ date: startDate, slot: startSlot }, mealTimes, slots);
  }

  /** 건너뛰기 — 기본 시각 + 자동 배정 결과를 그대로 보냅니다. */
  function handleSkip() {
    if (!schedule || recordId === null) return;
    const defaults: Record<number, MealSlot[]> = {};
    for (const med of schedule.medications) {
      defaults[med.medicationId] = defaultSlotsFor(med.timesPerDay, med.timing);
    }
    void persist(
      { date: startDate || todayISO(), slot: startSlot ?? 'morning' },
      DEFAULT_MEAL_TIMES,
      defaults,
    );
  }

  function handleBack() {
    if (recordId !== null && ocrJobId) {
      const params = new URLSearchParams({
        batchId: ocrJobId,
        recordId: String(recordId),
        mode: 'confirmed',
      });
      navigate(`/ocr-review?${params.toString()}`, {
        replace: true,
        state: {
          batchId: ocrJobId,
          ...(startDateEdited ? { scheduleStartDate: startDate } : {}),
          ...(registrationFlow ? { registrationFlow: true, episodeAlias: state.episodeAlias } : {}),
        },
      });
      return;
    }
    navigate(-1);
  }

  if (recordId === null) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="복약 시간 설정" onBack={handleBack} />
        <main className="flex flex-1 flex-col px-page-x py-4">
          <Card title="복약 기록을 선택해주세요.">
            <div className="flex flex-col gap-4">
              <p>약봉투 등록을 완료한 뒤 복약 시간을 설정할 수 있어요.</p>
              <Button onClick={() => navigate('/document-upload')}>약봉투 등록하기</Button>
            </div>
          </Card>
        </main>
      </div>
    );
  }

  if (loadError !== null || !schedule) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="복약 시간 설정" onBack={handleBack} />
        <main className="flex flex-1 flex-col px-page-x py-4">
          {loadError !== null ? (
            <Card title="복약 정보를 불러오지 못했어요">{loadError}</Card>
          ) : (
            <p className="text-sm text-muted-foreground">불러오는 중...</p>
          )}
        </main>
      </div>
    );
  }

  const scheduledMeds = schedule.medications.filter((m) => m.timesPerDay !== null);
  const hasAutomaticallyAssignedMeds = scheduledMeds.some((medication) =>
    needsSlotConfirmation(medication.timesPerDay, medication.timing),
  );
  const usedSlots = new Set<MealSlot>(scheduledMeds.flatMap((m) => slots[m.medicationId] ?? []));
  const orderValid = isMealTimeOrderValid(mealTimes);
  const emptyMedIds = new Set(
    scheduledMeds
      .filter((m) => (slots[m.medicationId] ?? []).length === 0)
      .map((m) => m.medicationId),
  );
  const editingLabel = editingSlot
    ? MEAL_SLOTS.find((s) => s.value === editingSlot)?.label
    : undefined;

  // ISO 문자열은 사전순 = 시간순이라 그대로 비교할 수 있습니다.
  const minDate = isoYearsAgo(MIN_START_DATE_YEARS);
  const maxDate = todayISO();
  const dateInRange = startDate >= minDate && startDate <= maxDate;

  /**
   * 저장을 막는 사유. **화면의 단일 출처입니다** — 시작 시점 블록의 인라인 문구와
   * 저장 버튼 위 문구가 같은 값을 읽고, `canSave`도 여기서 파생됩니다.
   * 조건 목록과 문구 목록을 따로 두면 한쪽만 고쳐져서 "이유 없이 비활성된 버튼"이 생깁니다.
   *
   * tone 은 심각도입니다. 아직 안 고른 것(info)과 잘못 고른 것(error)을 나눕니다 —
   * 진입 직후에는 날짜만 프리필되고 시간대가 비어 있는 게 정상 상태이므로, 사용자가
   * 아무것도 잘못하지 않았는데 빨간 경고가 먼저 보이면 안 됩니다.
   */
  const startPointBlocker: Blocker | null = !startDate
    ? { message: '복용을 시작한 날짜를 선택해주세요.', tone: 'info' }
    : !dateInRange
      ? {
          message:
            startDate > maxDate
              ? '복용 시작일은 오늘까지만 고를 수 있어요.'
              : `복용 시작일은 최근 ${MIN_START_DATE_YEARS}년 이내로 골라주세요.`,
          tone: 'error',
        }
      : !startSlot
        ? { message: '알림을 받으려면 복약 시작 시간대를 선택해주세요.', tone: 'info' }
        : null;

  const blocker: Blocker | null =
    startPointBlocker ??
    (!orderValid
      ? { message: '시간을 아침약 → 점심약 → 저녁약 → 취침약 순서로 맞춰주세요.', tone: 'error' }
      : emptyMedIds.size > 0
        ? { message: `복용 시간이 비어 있는 약이 ${emptyMedIds.size}개 있어요.`, tone: 'error' }
        : null);

  const canSave = blocker === null;

  if (registrationFlow) {
    return (
      <MedicationRegistrationWizard
        recordId={recordId}
        schedule={schedule}
        scheduleSaver={scheduleSaver}
        initialSlots={slots}
        initialMealTimes={mealTimes}
        initialStartDate={startDate || dispensedDate || todayISO()}
        initialStartSlot={startSlot}
        alias={state.episodeAlias ?? ''}
        onBack={handleBack}
      />
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="복약 시간 설정" onBack={handleBack} />

      <main className="flex flex-1 flex-col gap-5 px-page-x py-4">
        {/* [1] 자동 배정 여부와 무관하게 모든 정기약의 시간대를 보여줍니다. */}
        {scheduledMeds.length > 0 && (
          <section aria-label="약별 복용 시간 확인" className="flex flex-col gap-2">
            <div>
              <p className="text-base font-bold text-foreground">약마다 먹는 시간을 확인해주세요</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {hasAutomaticallyAssignedMeds
                  ? '봉투에 시간대가 없는 약은 복용 횟수에 맞춰 정했어요.'
                  : '봉투에서 읽은 시간입니다. 맞는지 확인해주세요.'}
              </p>
            </div>
            <div className="flex flex-col gap-3">
              {scheduledMeds.map((med) => {
                const medSlots = slots[med.medicationId] ?? [];
                return (
                  <div
                    key={med.medicationId}
                    className="flex flex-col gap-2 rounded-card border border-border bg-card px-4 py-3 shadow-card"
                  >
                    <div className="flex flex-col gap-0.5">
                      <p className="text-base font-bold text-foreground">
                        {med.name} {med.dose}
                      </p>
                      <p className="text-sm text-muted-foreground">{medicationMetaText(med)}</p>
                    </div>

                    {/* 4개는 flex-1로 두면 라벨 길이 차이로 폭이 들쭉날쭉해집니다. */}
                    <div className="grid grid-cols-4 gap-2 border-t border-border pt-2">
                      {MEAL_SLOTS.map((slot) => {
                        const on = medSlots.includes(slot.value);
                        return (
                          <button
                            key={slot.value}
                            type="button"
                            aria-pressed={on}
                            aria-label={`${med.name} ${slot.label}`}
                            onClick={() => toggleSlot(med.medicationId, slot.value)}
                            className={cn(
                              'h-touch rounded-input border text-sm transition-colors',
                              on
                                ? 'border-primary bg-primary font-bold text-card'
                                : 'border-border bg-card text-muted-foreground hover:bg-muted-bg',
                            )}
                          >
                            {slot.short}
                          </button>
                        );
                      })}
                    </div>

                    {emptyMedIds.has(med.medicationId) && (
                      <p className="text-sm text-danger-strong">
                        복용 시간을 하나 이상 선택해주세요.
                      </p>
                    )}

                    {exceedsSlotCapacity(med.timesPerDay) && (
                      <p className="text-sm text-warning-strong">
                        1일 {med.timesPerDay}회 처방이에요. 시간 4개로는 다 담기지 않아 복용
                        간격을 의료진·약사에게 확인해주세요.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* [2] 복용 시작 시점 — 날짜와 시간대를 직접 고릅니다 */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <p className="text-base font-bold text-foreground">처음 약을 언제부터 드셨나요?</p>
            <span className="text-sm font-bold text-danger-strong">필수</span>
          </div>
          {/*
            min·max 는 달력 UI와 :invalid 상태만 제한합니다. 키보드로 넣은 범위 밖 값은
            그대로 올라오므로 blocker(→ canSave)에서 같은 조건을 한 번 더 검사합니다.
          */}
          <Input
            aria-label="복용 시작 날짜"
            type="date"
            min={minDate}
            max={maxDate}
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setStartDateEdited(true);
            }}
            onClick={openDatePicker}
          />
          <div
            role="group"
            aria-label="복약 시작 시간대 (필수)"
            className="flex flex-wrap gap-2"
          >
            {MEAL_SLOTS.map((slot) => {
              const selected = slot.value === startSlot;
              return (
                <button
                  key={slot.value}
                  type="button"
                  aria-pressed={selected}
                  aria-label={`시작 ${slot.label}`}
                  onClick={() => setStartSlot(slot.value)}
                  className={cn(
                    'min-h-touch rounded-pill border px-4 text-sm transition-colors',
                    selected
                      ? 'border-primary bg-primary-bg font-bold text-primary-strong'
                      : 'border-border bg-card text-foreground hover:bg-muted-bg',
                  )}
                >
                  {slot.label}
                </button>
              );
            })}
          </div>
          {/* 문구는 blocker 한 곳에서만 만듭니다. 두 벌로 두면 한쪽만 고쳐지는 날이 옵니다. */}
          {startPointBlocker ? (
            <p className={blockerClass(startPointBlocker.tone)}>{startPointBlocker.message}</p>
          ) : startDate && startSlot ? (
            <p className="text-sm text-muted-foreground">
              {formatStartPoint(startDate, startSlot)}부터 복용을 시작한 것으로 기록합니다.
            </p>
          ) : null}
        </div>

        {/* [3] 시간대 카드 */}
        <div className="flex flex-col gap-2">
          <p className="text-base font-bold text-foreground">어느 시간에 알람을 드릴까요?</p>
          <div className="overflow-hidden rounded-card border border-border bg-card">
            {MEAL_SLOTS.map((slot, index) => {
              const unused = !usedSlots.has(slot.value);
              return (
                <button
                  key={slot.value}
                  type="button"
                  onClick={() => setEditingSlot(slot.value)}
                  className={cn(
                    'flex min-h-touch w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-muted-bg',
                    index > 0 && 'border-t border-border',
                  )}
                >
                  <span
                    className={cn(
                      'w-16 shrink-0 text-sm font-bold',
                      unused ? 'text-disabled-foreground' : 'text-foreground',
                    )}
                  >
                    {slot.label}
                  </span>
                  <span
                    className={cn(
                      'text-base',
                      unused ? 'text-disabled-foreground' : 'text-foreground',
                    )}
                  >
                    {mealTimes[slot.value]}
                  </span>
                  {unused && (
                    <span className="text-sm text-disabled-foreground">이 시간에 먹는 약 없음</span>
                  )}
                  <span aria-hidden className="ml-auto text-muted-foreground">
                    ›
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <p className="text-sm text-muted-foreground">
          저장한 시간에 알림을 보내요. 나중에 복용약 화면에서 바꿀 수 있어요.
        </p>

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button onClick={handleSave} disabled={saving || !canSave}>
            {saving ? '저장 중...' : '저장하고 계속'}
          </Button>
          <Button variant="secondary" onClick={handleSkip} disabled={saving}>
            알람 없이 저장
          </Button>
        </div>
      </main>

      <ErrorDialog
        open={saveError !== null}
        title="복약 시간을 저장하지 못했어요"
        message={saveError?.message ?? ''}
        onRetry={() => {
          const retry = saveError?.retry;
          setSaveError(null);
          retry?.();
        }}
      />

      <NotifyPermissionDialog
        open={permissionDialogOpen}
        mealTimes={savedMealTimes ?? mealTimes}
        busy={permissionBusy}
        onAccept={() => void handlePermissionAccept()}
        onDismiss={() => void handlePermissionDismiss()}
      />

      <ErrorDialog
        open={notifyError !== null}
        title="알림 설정을 저장하지 못했어요"
        message={notifyError?.message ?? ''}
        onRetry={() => {
          const retry = notifyError?.retry;
          setNotifyError(null);
          retry?.();
        }}
      />

      <TimePickerSheet
        open={editingSlot !== null}
        description={editingLabel ? `${editingLabel} 알림 시각` : ''}
        value={editingSlot ? mealTimes[editingSlot] : '08:00'}
        onApply={applyTime}
        onCancel={() => setEditingSlot(null)}
      />
      <ErrorDialog
        open={timeOrderError}
        title="시간을 적용할 수 없어요"
        message="복약 시간은 아침약 → 점심약 → 저녁약 → 취침약 순서로 설정해주세요."
        retryLabel="확인"
        onRetry={() => setTimeOrderError(false)}
      />
    </div>
  );
}

interface MedicationRegistrationWizardProps {
  recordId: number | null;
  schedule: MedicationSchedule;
  scheduleSaver: typeof saveMedicationSchedule;
  initialSlots: Record<number, MealSlot[]>;
  initialMealTimes: MealTimes;
  initialStartDate: string;
  initialStartSlot: MealSlot | null;
  alias: string;
  onBack: () => void;
}

/**
 * OCR 확인 뒤에만 사용하는 3~5단계 등록 흐름입니다.
 * 기존 `/dev/medication-schedule`와 설정 화면은 위의 기존 계약을 그대로 사용합니다.
 */
function MedicationRegistrationWizard({
  recordId,
  schedule,
  scheduleSaver,
  initialSlots,
  initialMealTimes,
  initialStartDate,
  initialStartSlot,
  alias,
  onBack,
}: MedicationRegistrationWizardProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<3 | 4 | 5>(3);
  const [slots, setSlots] = useState<Record<number, MealSlot[]>>(initialSlots);
  const [mealTimes] = useState<MealTimes>(initialMealTimes);
  const [startDate, setStartDate] = useState(initialStartDate);
  const [startSlot, setStartSlot] = useState<MealSlot | null>(initialStartSlot);
  const [enabledAlarmSlots, setEnabledAlarmSlots] = useState<MealSlot[]>(() =>
    SLOT_ORDER.filter((slot) =>
      Object.values(initialSlots).some((medicationSlots) => medicationSlots.includes(slot)),
    ),
  );
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);

  const scheduledMeds = schedule.medications.filter((medication) => medication.timesPerDay !== null);
  const usedSlots = new Set<MealSlot>(scheduledMeds.flatMap((medication) => slots[medication.medicationId] ?? []));
  const selectedAlarmSlots = SLOT_ORDER.filter(
    (slot) => usedSlots.has(slot) && enabledAlarmSlots.includes(slot),
  );
  const canContinueFromSlots = scheduledMeds.every(
    (medication) => (slots[medication.medicationId] ?? []).length > 0,
  );

  function toggleSlot(medicationId: number, slot: MealSlot) {
    setSlots((current) => {
      const next = new Set(current[medicationId] ?? []);
      const wasSelected = next.has(slot);
      if (next.has(slot)) next.delete(slot);
      else next.add(slot);
      if (!wasSelected) {
        setEnabledAlarmSlots((enabled) =>
          enabled.includes(slot) ? enabled : SLOT_ORDER.filter((value) => value === slot || enabled.includes(value)),
        );
      }
      return { ...current, [medicationId]: SLOT_ORDER.filter((value) => next.has(value)) };
    });
  }

  async function completeRegistration() {
    if (recordId === null || !startSlot || !startDate || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      await scheduleSaver(recordId, {
        start: { date: startDate, slot: startSlot },
        mealTimes,
        medications: scheduledMeds.map((medication) => ({
          medicationId: medication.medicationId,
          slots: slots[medication.medicationId] ?? [],
        })),
      });
      setCompleted(true);
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '복약 등록을 완료하지 못했어요.');
    } finally {
      setSaving(false);
    }
  }

  function formatCompletionStart(): string {
    const [, month, day] = startDate.split('-');
    const slotLabel = MEAL_SLOTS.find((slot) => slot.value === startSlot)?.label ?? '';
    return month && day ? `${Number(month)}월 ${Number(day)}일 ${slotLabel}` : slotLabel;
  }

  function handleWizardBack() {
    if (step === 5) {
      setStep(4);
      return;
    }
    if (step === 4) {
      setStep(3);
      return;
    }
    onBack();
  }

  if (completed) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="약봉투 등록" onBack={onBack} />
        <main className="flex flex-1 flex-col items-center gap-5 px-page-x py-8 text-center">
          <RegistrationProgress step={5} />
          <div className="mt-10 flex size-16 items-center justify-center rounded-full bg-success-bg text-success-strong">
            <span aria-hidden className="text-3xl">✓</span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">약 등록을 완료했어요</h1>
            <p className="mt-2 text-base text-muted-foreground">
              오늘 일정부터 홈에서 확인할 수 있어요.
            </p>
          </div>
          <Card className="w-full gap-2 p-4 text-left">
            <p className="font-bold text-foreground">등록한 약 {scheduledMeds.length}개</p>
            <p className="text-sm text-muted-foreground">첫 복용 {formatCompletionStart()}</p>
            <p className="text-sm text-muted-foreground">
              알림 {selectedAlarmSlots.map((slot) => mealTimes[slot]).join(' · ') || '없음'}
            </p>
            {alias && <p className="text-sm text-muted-foreground">별칭 {alias}</p>}
          </Card>
          <div className="mt-auto w-full pb-4">
            <Button onClick={() => navigate('/home', { replace: true })}>홈에서 확인</Button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="약봉투 등록" onBack={handleWizardBack} />
      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        <RegistrationProgress step={step} />

        {step === 3 && (
          <>
            <section>
              <h1 className="text-2xl font-bold text-foreground">약마다 먹는 시간을 확인해주세요</h1>
              <p className="mt-1 text-base text-muted-foreground">
                봉투에서 읽은 시간이에요. 다르면 눌러 바꿔주세요.
              </p>
            </section>
            {/* 이전 계약에서 바로 노출하던 날짜 입력도 유지해, 새 흐름에서도 값 확인이 가능합니다. */}
            <Input
              label="첫 복용 날짜"
              aria-label="복용 시작 날짜"
              type="date"
              value={startDate}
              max={todayISO()}
              onChange={(event) => setStartDate(event.target.value)}
            />
            <div className="flex flex-col gap-3">
              {scheduledMeds.map((medication) => (
                <Card key={medication.medicationId} className="gap-3 p-4">
                  <div>
                    <p className="font-bold text-foreground">{medication.name} {medication.dose}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{medication.timing || '복용 시간을 선택해주세요'}</p>
                  </div>
                  <div className="grid grid-cols-4 gap-2 border-t border-border pt-3">
                    {MEAL_SLOTS.map((slot) => {
                      const selected = (slots[medication.medicationId] ?? []).includes(slot.value);
                      return (
                        <button
                          key={slot.value}
                          type="button"
                          aria-pressed={selected}
                          aria-label={`${medication.name} ${slot.label}`}
                          onClick={() => toggleSlot(medication.medicationId, slot.value)}
                          className={cn(
                            'min-h-touch rounded-input border text-sm',
                            selected
                              ? 'border-primary bg-primary font-bold text-card'
                              : 'border-border bg-card text-muted-foreground',
                          )}
                        >
                          {slot.value === 'bedtime' ? '자기전' : slot.short}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    선택한 복용 시간{' '}
                    {(slots[medication.medicationId] ?? [])
                      .map((slot) => MEAL_SLOTS.find((item) => item.value === slot)?.label)
                      .join(' · ') || '없음'}
                  </p>
                </Card>
              ))}
            </div>
            <div className="mt-auto pb-4">
              <Button disabled={!canContinueFromSlots} onClick={() => setStep(4)}>
                확인
              </Button>
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <section>
              <h1 className="text-2xl font-bold text-foreground">처음 약을 언제 드셨나요?</h1>
              <p className="mt-1 text-base text-muted-foreground">
                복용 기록이 시작되는 날짜와 시간이에요.
              </p>
            </section>
            <div className="flex flex-col gap-4">
              <Input
                label="첫 복용 날짜"
                aria-label="복용 시작 날짜"
                type="date"
                value={startDate}
                max={todayISO()}
                onChange={(event) => setStartDate(event.target.value)}
              />
              <div className="flex flex-col gap-2">
                <p className="text-sm font-bold text-foreground">첫 복용 시간</p>
                <div className="flex flex-wrap gap-2">
                  {MEAL_SLOTS.map((slot) => (
                    <button
                      key={slot.value}
                      type="button"
                      aria-pressed={startSlot === slot.value}
                      aria-label={`시작 ${slot.label}`}
                      onClick={() => setStartSlot(slot.value)}
                      className={cn(
                        'min-h-touch rounded-pill border px-4 text-sm',
                        startSlot === slot.value
                          ? 'border-primary bg-primary-bg font-bold text-primary-strong'
                          : 'border-border bg-card text-foreground',
                      )}
                    >
                      {slot.value === 'bedtime' ? '자기전' : slot.short}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-auto pb-4">
              <Button disabled={!startDate || !startSlot} onClick={() => setStep(5)}>
                확인
              </Button>
            </div>
          </>
        )}

        {step === 5 && (
          <>
            <section>
              <h1 className="text-2xl font-bold text-foreground">알람 시간을 확인해주세요</h1>
              <p className="mt-1 text-base text-muted-foreground">쓰지 않는 시간은 끌 수 있어요.</p>
            </section>
            <div className="overflow-hidden rounded-card border border-border bg-card">
              {MEAL_SLOTS.map((slot, index) => {
                const used = usedSlots.has(slot.value);
                return (
                  <label
                    key={slot.value}
                    className={cn(
                      'flex min-h-touch items-center gap-3 px-4 py-3',
                      index > 0 && 'border-t border-border',
                      !used && 'text-disabled-foreground',
                    )}
                  >
                    <span className="w-16 font-bold">
                      {slot.value === 'bedtime' ? '자기전' : slot.short}
                    </span>
                    <span className="tnum">{mealTimes[slot.value]}</span>
                    <span className="ml-auto flex items-center gap-2 text-sm">
                      {used ? '사용' : '사용 안 함'}
                      <input
                        type="checkbox"
                        aria-label={`${slot.label} 복약 알림`}
                        checked={used && enabledAlarmSlots.includes(slot.value)}
                        disabled={!used}
                        onChange={() =>
                          setEnabledAlarmSlots((current) =>
                            current.includes(slot.value)
                              ? current.filter((value) => value !== slot.value)
                              : SLOT_ORDER.filter((value) => value === slot.value || current.includes(value)),
                          )
                        }
                        className="size-5 accent-primary"
                      />
                    </span>
                  </label>
                );
              })}
            </div>
            <Card tone="info" className="p-4">
              저장하면 복약 일정과 알람 설정이 함께 끝나요.
            </Card>
            {saveError && <p role="alert" className="text-sm text-danger-strong">{saveError}</p>}
            <div className="mt-auto pb-4">
              <Button disabled={saving} onClick={() => void completeRegistration()}>
                {saving ? '등록 중...' : '등록 완료'}
              </Button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
