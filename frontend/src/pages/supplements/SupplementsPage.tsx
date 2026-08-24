import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ChevronRight, Plus, Sprout } from 'lucide-react';
import { useNavigate } from 'react-router';
import {
  addSupplement,
  getSupplements,
  summarizeNutrients,
  type AddSupplementPayload,
  type NutrientTotal,
  type Supplement,
} from '@/entities/supplement';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  type TabKey,
} from '@/shared/ui';
import { AddSupplementSheet } from './AddSupplementSheet';

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
}

export function SupplementsPage({ supplementsOverride }: SupplementsPageProps = {}) {
  const navigate = useNavigate();
  const [supplements, setSupplements] = useState<Supplement[] | null>(supplementsOverride ?? null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const totals = useMemo(() => summarizeNutrients(supplements ?? []), [supplements]);
  const exceeded = totals.filter((total) => total.exceeded);
  const neutral = totals.filter((total) => !total.exceeded);

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

  async function saveSupplement(payload: AddSupplementPayload) {
    try {
      const saved = await addSupplement(payload);
      setSupplements((current) => [...(current ?? []), saved]);
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '영양제를 추가하지 못했어요.');
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
            <section className="flex flex-col gap-3" aria-labelledby="supplement-list-title">
              <h2 id="supplement-list-title" className="text-xl font-bold text-foreground">
                먹고 있는 영양제 {supplements.length}개
              </h2>
              {supplements.map((supplement) => (
                <button
                  key={supplement.supplementId}
                  type="button"
                  className="flex min-h-20 items-center gap-4 rounded-card bg-card px-4 py-3 text-left shadow-card"
                >
                  <span className="flex size-12 items-center justify-center rounded-pill bg-primary-bg text-primary-strong">
                    <Sprout aria-hidden className="size-6" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <strong className="block text-lg text-foreground">{supplement.name}</strong>
                    <span className="block text-sm text-muted-foreground">
                      1일 {supplement.dailyCount}정 · {supplement.times.join(' · ')}
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
                <ExceededNutrientCard key={total.nutrientId} total={total} />
              ))}
              {neutral.length > 0 && <NeutralNutrientCard totals={neutral} />}
            </section>

            <div className="flex flex-col gap-1 text-sm text-muted-foreground">
              <p>기준 · 2025 한국인 영양소 섭취기준 상한섭취량</p>
              <p>
                등록한 건강기능식품 {supplements.length}개만 더한 값입니다. 음식과 의약품을 통한
                섭취량은 포함되지 않았습니다.
              </p>
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
      <ErrorDialog
        open={saveError !== null}
        title="영양제를 추가하지 못했어요"
        message={saveError ?? ''}
        retryLabel="확인"
        onRetry={() => setSaveError(null)}
      />
    </div>
  );
}

function ExceededNutrientCard({ total }: { total: NutrientTotal }) {
  const excess = total.amount - total.upperLimit;
  return (
    <article aria-label={`${total.name} 성분 합계`}>
      <Card tone="warning" className="gap-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <AlertCircle aria-hidden className="size-5 shrink-0 text-warning" />
          <h3 className="text-lg font-bold text-foreground">{total.name}</h3>
        </div>
        <span className="rounded-pill bg-card px-3 py-1 text-sm font-bold text-warning-strong">
          상한 초과
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <strong className="text-metric font-bold text-warning-strong tnum">
          {numberFormat.format(total.amount)}
        </strong>
        <span className="text-unit text-muted-foreground tnum">
          / {numberFormat.format(total.upperLimit)} {total.unit}
        </span>
      </div>
      <div>
        <div className="relative h-2 rounded-pill bg-card" aria-hidden>
          <div className="h-full w-full rounded-pill bg-warning" />
          <span className="absolute top-0 right-0 h-full w-px bg-foreground" />
        </div>
        <div className="mt-1 flex justify-between text-unit font-bold text-warning-strong tnum">
          <span>+{numberFormat.format(excess)}</span>
          <span>상한 {numberFormat.format(total.upperLimit)}</span>
        </div>
      </div>
      <p className="border-t border-border pt-3 text-sm text-muted-foreground">
        {total.sourceNames.join('과 ')}에 함께 들어 있어요. 하나를 줄일지 담당 의사·약사에게
        확인해 주세요.
      </p>
      </Card>
    </article>
  );
}

function NeutralNutrientCard({ totals }: { totals: NutrientTotal[] }) {
  return (
    <Card className="gap-4 p-4">
      {totals.map((total) => {
        const percent = Math.min(100, (total.amount / total.upperLimit) * 100);
        return (
          <div
            key={total.nutrientId}
            role="article"
            aria-label={`${total.name} 성분 합계`}
            className="flex flex-col gap-2"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-base font-bold text-foreground">{total.name}</span>
              <span className="text-sm text-muted-foreground tnum">
                {numberFormat.format(total.amount)} / {numberFormat.format(total.upperLimit)} {total.unit}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-pill bg-muted-bg" aria-hidden>
              <div
                className="h-full rounded-pill bg-disabled-foreground"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        );
      })}
    </Card>
  );
}
