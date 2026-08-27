import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ChevronRight, Plus, Sprout } from 'lucide-react';
import { useNavigate } from 'react-router';
import { getMyProfile, type Gender } from '@/entities/account';
import {
  addSupplement,
  evaluateNutrientStandard,
  getSupplements,
  stopSupplement,
  summarizeNutrients,
  updateSupplement,
  type AddSupplementPayload,
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
}

export function SupplementsPage({
  supplementsOverride,
  profileOverride,
}: SupplementsPageProps = {}) {
  const navigate = useNavigate();
  const [supplements, setSupplements] = useState<Supplement[] | null>(supplementsOverride ?? null);
  const [profile, setProfile] = useState<NutrientStandardProfile | null>(
    profileOverride ?? null,
  );
  const [profileResolved, setProfileResolved] = useState(profileOverride !== undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editingSupplement, setEditingSupplement] = useState<Supplement | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveErrorTitle, setSaveErrorTitle] = useState('영양제를 추가하지 못했어요');
  const totals = useMemo(() => summarizeNutrients(supplements ?? []), [supplements]);
  const hasStandardProfile = Boolean(profile?.birthDate && profile.gender);
  const exceeded = hasStandardProfile ? totals.filter((total) => total.exceeded) : [];
  const neutral = hasStandardProfile ? totals.filter((total) => !total.exceeded) : totals;
  const supplementsWithNutrients = (supplements ?? []).filter(
    (supplement) => supplement.nutrientDataAvailable,
  ).length;
  const manuallyEnteredSupplements = (supplements ?? []).length - supplementsWithNutrients;

  useEffect(() => {
    if (supplementsOverride) {
      setSupplements(supplementsOverride);
      return;
    }
    let cancelled = false;
    getSupplements()
      .then((result) => {
        if (!cancelled) setSupplements(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '영양제를 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [supplementsOverride]);

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
      setSupplements((current) => [saved, ...(current ?? [])]);
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
            onClick={() => setAddOpen(true)}
          >
            <Plus aria-hidden className="size-6" />
          </button>
        }
      />

      <main className="flex flex-1 flex-col gap-6 overflow-y-auto px-page-x py-5">
        {loadError !== null ? (
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
                      1일 {supplement.dailyCount}정 ·{' '}
                      {supplement.slots.map((slot) => mealSlotLabel(slot, 'short')).join(' · ')}
                    </span>
                  </span>
                  <ChevronRight aria-hidden className="size-5 text-disabled-foreground" />
                </button>
              ))}
            </section>

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
              <p>
                등록한 건강기능식품 {supplementsWithNutrients}개만 더한 값입니다. 음식과 의약품을 통한
                섭취량은 포함되지 않았습니다.
              </p>
              <p>
                직접 입력한 {manuallyEnteredSupplements}개는 성분을 알 수 없어 합계에 포함하지
                않았습니다.
              </p>
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

            <Button variant="secondary" onClick={() => setAddOpen(true)}>
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
      <AddSupplementSheet open={addOpen} onOpenChange={setAddOpen} onSave={saveSupplement} />
      <EditSupplementSheet
        open={editingSupplement !== null}
        supplement={editingSupplement}
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
          <div className="flex items-center gap-2">
            {isOverUpperLimit && (
              <AlertCircle aria-hidden className="size-5 shrink-0 text-warning" />
            )}
            <h3 className="text-lg font-bold text-foreground">{total.name}</h3>
          </div>
        </div>

        <div className="flex items-baseline gap-2">
          <strong
            className={`text-metric font-bold tnum ${
              isOverUpperLimit ? 'text-warning-strong' : 'text-foreground'
            }`}
          >
            {numberFormat.format(total.amount)}
          </strong>
          <span className="text-unit text-muted-foreground">{total.unit}</span>
        </div>

        {showStandards && (
          <>
            {evaluation.base === null && total.ul === null ? (
              <p className="text-sm text-muted-foreground">기준이 없는 성분이에요</p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-unit text-muted-foreground tnum">
                  {evaluation.base !== null && (
                    <span>
                      {evaluation.baseKind === 'ai' ? '충분' : '권장'}{' '}
                      {numberFormat.format(evaluation.base)}
                    </span>
                  )}
                  {total.ul !== null ? (
                    <span>상한 {numberFormat.format(total.ul)}</span>
                  ) : (
                    <span>상한 기준이 없어요</span>
                  )}
                </div>
                <NutrientRangeBar total={total} />
                <StandardStatus total={total} />
              </>
            )}
          </>
        )}

        {isOverUpperLimit && (
          <p className="border-t border-border pt-3 text-sm text-muted-foreground">
            {total.sourceNames.join('과 ')}에 함께 들어 있어요. 하나를 줄일지 담당 의사·약사에게
            확인해 주세요.
          </p>
        )}
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
      <Card tone={isOverUpperLimit ? 'warning' : 'default'} className="gap-4 p-4">
        {content}
      </Card>
    </article>
  );
}

function StandardStatus({ total }: { total: NutrientTotal }) {
  const evaluation = evaluateNutrientStandard(total);
  if (evaluation.status === 'over-upper-limit') {
    return <p className="text-sm font-bold text-warning-strong">상한 초과</p>;
  }
  if (evaluation.status === 'below-base' && evaluation.percentOfBase !== null) {
    return (
      <p className="text-sm text-muted-foreground">
        영양제로는 권장량의 {evaluation.percentOfBase}%
      </p>
    );
  }
  if (evaluation.status === 'recommended') {
    return <p className="text-sm text-muted-foreground">권장 범위예요</p>;
  }
  return null;
}

function NutrientRangeBar({ total }: { total: NutrientTotal }) {
  const evaluation = evaluateNutrientStandard(total);
  const positions = rangePositions(total, evaluation.base);
  const overUpperLimit = evaluation.status === 'over-upper-limit';

  return (
    <div
      role="meter"
      aria-label={`${total.name} 섭취기준 위치`}
      aria-valuemin={0}
      aria-valuenow={total.amount}
      aria-valuemax={Math.max(total.amount, total.ul ?? evaluation.base ?? total.amount)}
      className="relative mx-1 h-5"
    >
      <div className="absolute inset-x-0 top-2 h-2 rounded-pill bg-muted-bg">
        <div
          className={`h-full rounded-pill ${overUpperLimit ? 'bg-warning' : 'bg-primary-bg'}`}
          style={{ width: `${positions.marker}%` }}
        />
      </div>
      {positions.base !== null && (
        <span
          data-threshold="base"
          aria-hidden
          className="absolute top-1 h-4 w-px bg-muted-foreground"
          style={{ left: `${positions.base}%` }}
        />
      )}
      {positions.upper !== null && (
        <span
          data-threshold="upper-limit"
          aria-hidden
          className={`absolute top-1 h-4 w-px ${
            overUpperLimit ? 'bg-warning' : 'bg-muted-foreground'
          }`}
          style={{ left: `${positions.upper}%` }}
        />
      )}
      <span
        aria-hidden
        className={`absolute top-1 size-4 -translate-x-1/2 rounded-pill border-2 border-card ${
          overUpperLimit ? 'bg-warning' : 'bg-muted-foreground'
        }`}
        style={{ left: `${positions.marker}%` }}
      />
    </div>
  );
}

function rangePositions(total: NutrientTotal, base: number | null) {
  if (total.ul !== null) {
    const upper = 88;
    const marker = total.amount > total.ul
      ? 100
      : Math.max(0, Math.min(upper, (total.amount / total.ul) * upper));
    const basePosition = base === null
      ? null
      : Math.max(8, Math.min(upper - 8, (base / total.ul) * upper));
    return { base: basePosition, upper, marker };
  }

  if (base !== null) {
    const basePosition = 64;
    const marker = Math.max(0, Math.min(100, (total.amount / base) * basePosition));
    return { base: basePosition, upper: null, marker };
  }

  return { base: null, upper: null, marker: 0 };
}

function standardSourceLabel(profile: NutrientStandardProfile | null): string {
  if (!profile?.birthDate || !profile.gender) {
    return '기준 · 2025 한국인 영양소 섭취기준';
  }
  const age = calculateFullAge(profile.birthDate);
  const gender = profile.gender === 'female' ? '여성' : '남성';
  return `기준 · 2025 한국인 영양소 섭취기준 · 만 ${age}세 ${gender}`;
}
