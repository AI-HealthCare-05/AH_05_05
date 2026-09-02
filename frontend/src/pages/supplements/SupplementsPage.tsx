import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, Plus, Sprout, Star } from 'lucide-react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { getMyProfile, type Gender } from '@/entities/account';
import {
  addSupplement,
  evaluateNutrientStandard,
  getSupplements,
  stopSupplement,
  summarizeNutrients,
  updateSupplement,
  type AddSupplementPayload,
  type NutrientStandards,
  type NutrientTotal,
  type Supplement,
  type UpdateSupplementPayload,
} from '@/entities/supplement';
import { calculateFullAge } from '@/shared/lib/birthDate';
import { mealSlotLabel } from '@/shared/model/mealSlot';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  StatusBadge,
  type TabKey,
} from '@/shared/ui';
import { AddSupplementSheet } from './AddSupplementSheet';
import { EditSupplementSheet } from './EditSupplementSheet';
import { SupplementsBrowseView } from './SupplementsBrowseView';

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

const numberFormat = new Intl.NumberFormat('ko-KR');

interface SupplementsPageProps {
  supplementsOverride?: Supplement[];
  profileOverride?: NutrientStandardProfile;
}

export interface NutrientStandardProfile {
  birthDate: string | null;
  gender: Gender | null;
  maskedName: string;
}

export function SupplementsPage({
  supplementsOverride,
  profileOverride,
}: SupplementsPageProps = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const activeView = searchParams.get('tab') === 'browse' ? 'browse' : 'my';
  const routePresetProductId = presetProductIdFromState(location.state);
  const [supplements, setSupplements] = useState<Supplement[] | null>(supplementsOverride ?? null);
  const [standards, setStandards] = useState<NutrientStandards | null>(null);
  const [profile, setProfile] = useState<NutrientStandardProfile | null>(
    profileOverride ?? null,
  );
  const [profileResolved, setProfileResolved] = useState(profileOverride !== undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(routePresetProductId !== null);
  const [presetProductId, setPresetProductId] = useState<string | null>(routePresetProductId);
  const [editingSupplement, setEditingSupplement] = useState<Supplement | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveErrorTitle, setSaveErrorTitle] = useState('영양제를 추가하지 못했어요');
  const totals = useMemo(
    () => summarizeNutrients(supplements ?? [], standards),
    [standards, supplements],
  );
  const hasStandardProfile = standards !== null;
  const exceeded = hasStandardProfile ? totals.filter((total) => total.exceeded) : [];
  const neutral = hasStandardProfile ? totals.filter((total) => !total.exceeded) : totals;
  const supplementsWithNutrients = (supplements ?? []).filter(
    (supplement) => supplement.nutrientDataAvailable,
  ).length;
  const manuallyEnteredSupplements = (supplements ?? []).length - supplementsWithNutrients;
  const registeredProductIds = useMemo(
    () =>
      new Set(
        (supplements ?? []).flatMap((supplement) =>
          supplement.productId === null ? [] : [supplement.productId],
        ),
      ),
    [supplements],
  );

  useEffect(() => {
    if (routePresetProductId === null) return;
    setPresetProductId(routePresetProductId);
    setAddOpen(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, navigate, routePresetProductId]);

  function openAddSheet() {
    setPresetProductId(null);
    setAddOpen(true);
  }

  function changeView(view: 'my' | 'browse') {
    const search = view === 'browse' ? '?tab=browse' : '';
    navigate(`${location.pathname}${search}`, { replace: true });
  }

  function changeAddOpen(open: boolean) {
    setAddOpen(open);
    if (!open) setPresetProductId(null);
  }

  useEffect(() => {
    if (supplementsOverride) {
      setSupplements(supplementsOverride);
    }
    let cancelled = false;
    getSupplements()
      .then((result) => {
        if (cancelled) return;
        if (!supplementsOverride) setSupplements(result.items);
        const overrideHasProfile =
          profileOverride === undefined ||
          Boolean(profileOverride.birthDate && profileOverride.gender);
        setStandards(overrideHasProfile ? result.standards : null);
      })
      .catch((error: unknown) => {
        if (cancelled || supplementsOverride) return;
        setLoadError(error instanceof Error ? error.message : '영양제를 불러오지 못했어요.');
      });
    return () => {
      cancelled = true;
    };
  }, [profileOverride, supplementsOverride]);

  useEffect(() => {
    if (profileOverride !== undefined) {
      setProfile(profileOverride);
      setProfileResolved(true);
      return;
    }
    let cancelled = false;
    getMyProfile()
      .then((result) => {
        if (!cancelled) setProfile(result);
      })
      .catch(() => {
        if (!cancelled) setProfile(null);
      })
      .finally(() => {
        if (!cancelled) setProfileResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [profileOverride]);

  async function saveSupplement(payload: AddSupplementPayload) {
    try {
      const saved = await addSupplement(payload);
      setSupplements((current) => [
        saved,
        ...(current ?? []).filter(
          (supplement) =>
            supplement.supplementId !== saved.supplementId &&
            (saved.productId === null || supplement.productId !== saved.productId),
        ),
      ]);
    } catch (error: unknown) {
      setSaveErrorTitle('영양제를 추가하지 못했어요');
      setSaveError(error instanceof Error ? error.message : '영양제를 추가하지 못했어요.');
      throw error;
    }
  }

  async function editSupplement(
    supplementId: number,
    payload: UpdateSupplementPayload,
  ) {
    try {
      const updated = await updateSupplement(supplementId, payload);
      setSupplements((current) =>
        (current ?? []).map((supplement) =>
          supplement.supplementId === supplementId ? updated : supplement,
        ),
      );
    } catch (error: unknown) {
      setSaveErrorTitle('영양제 정보를 저장하지 못했어요');
      setSaveError(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.');
      throw error;
    }
  }

  async function stopActiveSupplement(supplementId: number) {
    try {
      await stopSupplement(supplementId);
      setSupplements((current) =>
        (current ?? []).filter((supplement) => supplement.supplementId !== supplementId),
      );
    } catch (error: unknown) {
      setSaveErrorTitle('영양제 복용을 중단하지 못했어요');
      setSaveError(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.');
      throw error;
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title="영양제"
        onBack={() => navigate(-1)}
        right={
          <button
            type="button"
            aria-label="영양제 추가"
            className="flex size-touch items-center justify-center text-primary"
            onClick={openAddSheet}
          >
            <Plus aria-hidden className="size-6" />
          </button>
        }
      />

      <div className="px-page-x pt-5">
        <div
          className="grid grid-cols-2 rounded-input bg-muted-bg p-1"
          role="group"
          aria-label="영양제 화면"
        >
          {(['my', 'browse'] as const).map((view) => {
            const selected = view === activeView;
            return (
              <button
                key={view}
                type="button"
                aria-pressed={selected}
                className={`min-h-touch rounded-input text-sm font-bold ${
                  selected ? 'bg-card text-foreground shadow-card' : 'text-muted-foreground'
                }`}
                onClick={() => changeView(view)}
              >
                {view === 'my' ? '내 영양제' : '둘러보기'}
              </button>
            );
          })}
        </div>
      </div>

      <main className="flex flex-1 flex-col gap-6 overflow-y-auto px-page-x py-5">
        {activeView === 'browse' ? (
          <SupplementsBrowseView
            registeredProductIds={registeredProductIds}
            registrationPending={supplements === null}
            onSelectProduct={(productId) =>
              navigate(`/supplements/product/${encodeURIComponent(productId)}`)
            }
          />
        ) : loadError !== null ? (
          <Card title="영양제를 불러오지 못했어요">{loadError}</Card>
        ) : supplements === null ? (
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        ) : (
          <>
            <section
              className="flex flex-col gap-3"
              aria-label="먹고 있는 영양제"
              aria-labelledby="supplement-list-title"
            >
              <h2 id="supplement-list-title" className="text-xl font-bold text-foreground">
                먹고 있는 영양제 {supplements.length}개
              </h2>
              {supplements.map((supplement) => (
                <button
                  key={supplement.supplementId}
                  type="button"
                  className="flex min-h-20 items-center gap-4 rounded-card bg-card px-4 py-3 text-left shadow-card"
                  onClick={() => setEditingSupplement(supplement)}
                >
                  <span className="flex size-12 items-center justify-center rounded-pill bg-primary-bg text-primary-strong">
                    <Sprout aria-hidden className="size-6" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <strong className="text-lg text-foreground">{supplement.name}</strong>
                      {!supplement.nutrientDataAvailable && (
                        <StatusBadge type="done" className="px-2.5 py-1 text-sm">
                          성분 정보 없음
                        </StatusBadge>
                      )}
                    </span>
                    <span className="block text-sm text-muted-foreground">
                      하루 {supplement.slots.length}회 · 1회 {formatDoseAmount(supplement.doseAmount)}
                      {supplement.doseUnit} ·{' '}
                      {supplement.slots.map((slot) => mealSlotLabel(slot, 'short')).join(' · ')}
                    </span>
                    {supplement.score !== null && (
                      <span
                        className="mt-1 flex items-center gap-0.5"
                        aria-label={`별 ${supplement.score}점`}
                      >
                        {Array.from({ length: supplement.score }, (_, index) => (
                          <Star
                            key={index}
                            aria-hidden
                            className="size-4 fill-current text-primary"
                          />
                        ))}
                      </span>
                    )}
                  </span>
                  <ChevronRight aria-hidden className="size-5 text-disabled-foreground" />
                </button>
              ))}
            </section>

            {supplements.length > 0 && (
              <>
                <section className="flex flex-col gap-3" aria-labelledby="nutrient-total-title">
                  <h2 id="nutrient-total-title" className="text-xl font-bold text-foreground">
                    성분 합계
                  </h2>
                  {exceeded.map((total) => (
                    <NutrientTotalCard
                      key={total.nutrientId}
                      total={total}
                      showStandards={hasStandardProfile}
                    />
                  ))}
                  {neutral.length > 0 && (
                    <Card className="gap-0 overflow-hidden p-0">
                      {neutral.map((total) => (
                        <NutrientTotalCard
                          key={total.nutrientId}
                          total={total}
                          showStandards={hasStandardProfile}
                          grouped
                        />
                      ))}
                    </Card>
                  )}
                </section>

                <div className="flex flex-col gap-1 text-sm text-muted-foreground">
                  <p>{standardSourceLabel(profile)}</p>
                  {supplementsWithNutrients > 0 && (
                    <p>
                      등록한 건강기능식품 {supplementsWithNutrients}개만 더한 값입니다. 음식과 의약품을
                      통한 섭취량은 포함되지 않았습니다.
                    </p>
                  )}
                  {manuallyEnteredSupplements > 0 && (
                    <p>
                      직접 입력한 {manuallyEnteredSupplements}개는 성분을 알 수 없어 합계에 포함하지
                      않았습니다.
                    </p>
                  )}
                  {profileResolved && !hasStandardProfile && (
                    <button
                      type="button"
                      className="mt-2 flex min-h-touch items-center justify-between gap-3 rounded-control bg-card px-4 py-3 text-left text-sm font-bold text-foreground shadow-card"
                      onClick={() => navigate('/my/profile')}
                    >
                      <span>생년월일과 성별을 입력하면 나이·성별에 맞는 기준을 보여드려요</span>
                      <ChevronRight aria-hidden className="size-5 shrink-0 text-disabled-foreground" />
                    </button>
                  )}
                </div>
              </>
            )}

            <Button variant="secondary" onClick={openAddSheet}>
              <Plus aria-hidden className="mr-2 size-5" />
              영양제 추가
            </Button>
          </>
        )}
      </main>

      <BottomTabbar
        active="supplement"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
      <AddSupplementSheet
        open={addOpen}
        presetProductId={presetProductId}
        onOpenChange={changeAddOpen}
        onSave={saveSupplement}
      />
      <EditSupplementSheet
        open={editingSupplement !== null}
        supplement={editingSupplement}
        maskedName={profile?.maskedName ?? '익명'}
        onOpenChange={(open) => {
          if (!open) setEditingSupplement(null);
        }}
        onSave={editSupplement}
        onStop={stopActiveSupplement}
      />
      <ErrorDialog
        open={saveError !== null}
        title={saveErrorTitle}
        message={saveError ?? ''}
        retryLabel="확인"
        onRetry={() => setSaveError(null)}
      />
    </div>
  );
}

function NutrientTotalCard({
  total,
  showStandards,
  grouped = false,
}: {
  total: NutrientTotal;
  showStandards: boolean;
  grouped?: boolean;
}) {
  const evaluation = evaluateNutrientStandard(total);
  const isOverUpperLimit = showStandards && evaluation.status === 'over-upper-limit';

  const content = (
    <>
        <div className="flex items-start gap-3">
          <h3 className="text-lg font-bold text-foreground">{total.name}</h3>
        </div>

        <div className="flex items-baseline gap-2">
          <strong
            className={`text-metric font-bold tnum ${
              isOverUpperLimit ? 'text-danger-strong' : 'text-foreground'
            }`}
          >
            {numberFormat.format(total.amount)}
          </strong>
          <span className="text-unit text-muted-foreground">{total.unit}</span>
        </div>

        {showStandards && (
          <>
            {(evaluation.base !== null || total.ul !== null) && <NutrientRangeBar total={total} />}
            <StandardStatus total={total} />
          </>
        )}

        <p className="text-sm text-muted-foreground">
          {total.sourceNames.join(' · ')}에 들어 있어요
        </p>
    </>
  );

  if (grouped) {
    return (
      <article
        aria-label={`${total.name} 성분 합계`}
        className="flex flex-col gap-4 border-t border-border p-4 first:border-t-0"
      >
        {content}
      </article>
    );
  }

  return (
    <article aria-label={`${total.name} 성분 합계`}>
      <Card className="gap-4 p-4">
        {content}
      </Card>
    </article>
  );
}

function StandardStatus({ total }: { total: NutrientTotal }) {
  const evaluation = evaluateNutrientStandard(total);
  const baseLabel = evaluation.baseKind === 'ai' ? '충분섭취량' : '권장량';
  if (evaluation.status === 'unrated') {
    return null;
  }
  if (evaluation.status === 'over-upper-limit') {
    return <p className="text-sm font-bold text-danger-strong">상한 초과</p>;
  }
  if (evaluation.status === 'below-base' && evaluation.percentOfBase !== null) {
    return (
      <p className="text-sm text-muted-foreground">
        {baseLabel}의 {numberFormat.format(evaluation.percentOfBase)}%예요
      </p>
    );
  }
  if (evaluation.status === 'recommended') {
    if (total.ul === null && evaluation.percentOfBase !== null) {
      return (
        <p className="text-sm text-muted-foreground">
          {baseLabel}의 {numberFormat.format(evaluation.percentOfBase)}%예요
        </p>
      );
    }
    return <p className="text-sm text-muted-foreground">권장 범위예요</p>;
  }
  return null;
}

function NutrientRangeBar({ total }: { total: NutrientTotal }) {
  const evaluation = evaluateNutrientStandard(total);
  if (total.ul === null && evaluation.base === null) return null;

  const positions = rangePositions(total, evaluation.base);
  const upperLimit = total.ul;
  const hasUpperLimit = upperLimit !== null;
  const labelsAreClose =
    positions.base !== null &&
    positions.upper !== null &&
    Math.abs(positions.upper - positions.base) < 20;
  const fillColor =
    evaluation.status === 'below-base'
      ? 'bg-warning'
      : evaluation.status === 'over-upper-limit'
        ? 'bg-danger'
        : 'bg-primary';
  const markerColor =
    evaluation.status === 'below-base'
      ? 'bg-warning-strong'
      : evaluation.status === 'over-upper-limit'
        ? 'bg-danger-strong'
        : 'bg-primary-strong';

  return (
    <div
      data-nutrient-range
      data-threshold-labels
      aria-hidden={hasUpperLimit ? undefined : true}
      className="relative mx-1 h-14"
    >
      {positions.base !== null && evaluation.base !== null && (
        <div
          data-threshold-label="base"
          className={`absolute top-0 grid h-14 grid-rows-[1rem_1.5rem_1rem] whitespace-nowrap text-xs text-muted-foreground ${
            labelsAreClose ? '-translate-x-full text-left' : '-translate-x-1/2 text-center'
          }`}
          style={{ left: `${clampThresholdLabel(positions.base)}%` }}
        >
          <span className="row-start-1">
            {evaluation.baseKind === 'ai' ? '충분' : '권장'}
          </span>
          <span className="row-start-3 tnum">{numberFormat.format(evaluation.base)}</span>
        </div>
      )}
      {positions.upper !== null && upperLimit !== null && (
        <div
          data-threshold-label="upper-limit"
          className={`absolute top-0 grid h-14 grid-rows-[1rem_1.5rem_1rem] whitespace-nowrap text-xs text-muted-foreground ${
            labelsAreClose ? 'text-right' : '-translate-x-1/2 text-center'
          }`}
          style={{ left: `${clampThresholdLabel(positions.upper)}%` }}
        >
          <span className="row-start-1">상한</span>
          <span className="row-start-3 tnum">{numberFormat.format(upperLimit)}</span>
        </div>
      )}
      <div
        role={hasUpperLimit ? 'meter' : undefined}
        aria-label={hasUpperLimit ? `${total.name} 섭취기준 위치` : undefined}
        aria-valuemin={hasUpperLimit ? 0 : undefined}
        aria-valuenow={upperLimit !== null ? Math.min(total.amount, upperLimit) : undefined}
        aria-valuemax={upperLimit ?? undefined}
        aria-valuetext={
          hasUpperLimit ? `${numberFormat.format(total.amount)}${total.unit}` : undefined
        }
        className="absolute inset-x-0 top-4 h-5"
      >
        <div
          data-range-track
          className="absolute inset-x-0 top-2 h-2 rounded-pill bg-muted-bg"
          style={
            hasUpperLimit
              ? undefined
              : {
                  maskImage: 'linear-gradient(to right, black 0%, black 80%, transparent 100%)',
                  WebkitMaskImage:
                    'linear-gradient(to right, black 0%, black 80%, transparent 100%)',
                }
          }
        >
          <div
            data-range-fill
            className={`h-full rounded-pill ${fillColor}`}
            style={{ width: `${positions.marker}%` }}
          />
        </div>
        {positions.base !== null && (
          <span
            data-threshold="base"
            aria-hidden
            className="absolute top-1 h-4 w-0.5 bg-muted-foreground"
            style={{ left: `${positions.base}%` }}
          />
        )}
        {positions.upper !== null && (
          <span
            data-threshold="upper-limit"
            aria-hidden
            className="absolute top-1 h-4 w-0.5 bg-muted-foreground"
            style={{ left: `${positions.upper}%` }}
          />
        )}
        <span
          data-range-marker
          aria-hidden
          className={`absolute top-1 size-4 -translate-x-1/2 rounded-pill border-2 border-card ${markerColor}`}
          style={{ left: `${positions.marker}%` }}
        />
      </div>
    </div>
  );
}

function clampThresholdLabel(position: number): number {
  return Math.max(8, Math.min(92, position));
}

function rangePositions(total: NutrientTotal, base: number | null) {
  if (total.ul === null) {
    if (base === null || base === 0) return { base: null, upper: null, marker: 0 };
    return {
      base: 70,
      upper: null,
      marker: Math.max(0, Math.min(100, (total.amount / base) * 70)),
    };
  }
  const upper = 88;
  const marker =
    total.amount > total.ul
      ? 100
      : Math.max(0, Math.min(upper, (total.amount / total.ul) * upper));
  const basePosition =
    base === null ? null : Math.max(4, Math.min(upper - 4, (base / total.ul) * upper));
  return { base: basePosition, upper, marker };
}

function standardSourceLabel(profile: NutrientStandardProfile | null): string {
  if (!profile?.birthDate || !profile.gender) {
    return '기준 · 2025 한국인 영양소 섭취기준';
  }
  const age = calculateFullAge(profile.birthDate);
  const gender = profile.gender === 'female' ? '여성' : '남성';
  return `기준 · 2025 한국인 영양소 섭취기준 · 만 ${age}세 ${gender}`;
}

function formatDoseAmount(amount: number): string {
  return numberFormat.format(amount);
}

function presetProductIdFromState(state: unknown): string | null {
  if (state === null || typeof state !== 'object' || !('presetProductId' in state)) return null;
  const productId = (state as { presetProductId?: unknown }).presetProductId;
  return typeof productId === 'string' && productId ? productId : null;
}
