import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import {
  addSupplement,
  getSupplementProduct,
  getSupplements,
  type AddSupplementPayload,
  type SupplementProduct,
} from '@/entities/supplement';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import { BottomTabbar, Button, Card, ErrorDialog, Header } from '@/shared/ui';
import { AddSupplementSheet } from './AddSupplementSheet';
import { SupplementReviewSection } from './SupplementReviewSection';

const numberFormat = new Intl.NumberFormat('ko-KR');

export function SupplementProductPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { productId = '' } = useParams();
  const [product, setProduct] = useState<SupplementProduct | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [registrationPending, setRegistrationPending] = useState(true);
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const activeLocationKeyRef = useRef(location.key);
  activeLocationKeyRef.current = location.key;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setProduct(null);
    setLoadError(null);
    getSupplementProduct(productId)
      .then((value) => {
        if (!cancelled) setProduct(value);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '제품 정보를 불러오지 못했어요.');
        }
      });

    setRegistrationPending(true);
    getSupplements()
      .then((result) => {
        if (!cancelled) {
          setAlreadyRegistered(
            result.items.some((supplement) => supplement.productId === productId),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setAlreadyRegistered(false);
      })
      .finally(() => {
        if (!cancelled) setRegistrationPending(false);
      });

    return () => {
      cancelled = true;
    };
  }, [productId]);

  async function saveSupplement(payload: AddSupplementPayload) {
    const saveLocationKey = location.key;
    try {
      await addSupplement(payload);
      if (!mountedRef.current || activeLocationKeyRef.current !== saveLocationKey) return;
      setAlreadyRegistered(true);
      navigate(location.pathname.startsWith('/dev/') ? '/dev/supplements' : '/supplements');
    } catch (error: unknown) {
      if (mountedRef.current && activeLocationKeyRef.current === saveLocationKey) {
        setSaveError(error instanceof Error ? error.message : '영양제를 추가하지 못했어요.');
      }
      throw error;
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="제품 정보" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-6 overflow-y-auto px-page-x py-5">
        {loadError ? (
          <Card title="제품 정보를 불러오지 못했어요">{loadError}</Card>
        ) : product === null ? (
          <p className="text-sm text-muted-foreground">제품 정보를 불러오는 중...</p>
        ) : (
          <>
            <section className="flex min-w-0 flex-col gap-2" aria-labelledby="product-name">
              <h2 id="product-name" className="[overflow-wrap:anywhere] text-2xl font-bold text-foreground">
                {product.productName}
              </h2>
            </section>

            <ProductInformation product={product} />

            <section className="flex flex-col gap-3" aria-labelledby="product-nutrients-title">
              <h2 id="product-nutrients-title" className="text-xl font-bold text-foreground">
                성분
              </h2>
              <div className="overflow-hidden border border-border bg-card text-sm">
                <dl aria-label="제품 성분">
                  {product.nutrients.map((nutrient) => (
                    <div
                      key={nutrient.nutrientId}
                      className="flex min-h-touch items-center justify-between gap-4 border-t border-border px-4 py-3 first:border-t-0"
                    >
                      <dt className="font-bold text-foreground">{nutrient.name}</dt>
                      <dd className="text-foreground tnum">
                        {numberFormat.format(nutrient.amount)} {nutrient.unit}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            </section>

            <SupplementReviewSection productId={product.productId} />

            <Button
              className="mt-auto"
              disabled={registrationPending}
              onClick={() => {
                if (alreadyRegistered) {
                  navigate(location.pathname.startsWith('/dev/') ? '/dev/supplements' : '/supplements');
                } else {
                  setAddOpen(true);
                }
              }}
            >
              {registrationPending
                ? '등록 상태 확인 중...'
                : alreadyRegistered
                  ? '내 영양제에서 보기'
                  : '내 영양제에 추가'}
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
        presetProductId={product?.productId ?? null}
        onOpenChange={setAddOpen}
        onSave={saveSupplement}
      />
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

function ProductInformation({ product }: { product: SupplementProduct }) {
  const rows = [
    { label: '섭취 대상', value: availableProductInformation(product.manufacturer) },
    { label: '1회 섭취량', value: availableProductInformation(product.servingDescription) },
    { label: '하루 섭취 횟수', value: availableProductInformation(product.dailyFrequency) },
  ].filter((row): row is { label: string; value: string } => row.value !== null);

  if (rows.length === 0) return null;

  return (
    <section aria-label="제품 정보 상세" className="border border-border bg-card px-4">
      <dl>
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex min-h-touch min-w-0 items-center justify-between gap-4 border-t border-border py-3 first:border-t-0"
          >
            <dt className="shrink-0 text-sm font-bold text-muted-foreground">{row.label}</dt>
            <dd className="min-w-0 [overflow-wrap:anywhere] text-right text-sm font-bold text-foreground">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function availableProductInformation(value: string): string | null {
  const normalized = value.trim();
  if (!normalized || normalized === '-' || normalized.includes('정보 없음')) return null;
  return normalized;
}
