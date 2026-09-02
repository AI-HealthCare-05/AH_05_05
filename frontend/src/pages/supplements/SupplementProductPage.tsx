import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  addSupplement,
  getSupplementProduct,
  getSupplements,
  type AddSupplementPayload,
  type SupplementProduct,
} from '@/entities/supplement';
import { Button, Card, ErrorDialog, Header } from '@/shared/ui';
import { AddSupplementSheet } from './AddSupplementSheet';
import { SupplementReviewSection } from './SupplementReviewSection';

const numberFormat = new Intl.NumberFormat('ko-KR');

export function SupplementProductPage() {
  const navigate = useNavigate();
  const { productId = '' } = useParams();
  const [product, setProduct] = useState<SupplementProduct | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [registrationPending, setRegistrationPending] = useState(true);
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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
    try {
      await addSupplement(payload);
      setAlreadyRegistered(true);
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '영양제를 추가하지 못했어요.');
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
            <section className="flex flex-col gap-2" aria-labelledby="product-name">
              <h2 id="product-name" className="text-2xl font-bold text-foreground">
                {product.productName}
              </h2>
              <p className="text-sm text-muted-foreground">
                {product.manufacturer} · {product.servingDescription} · {product.dailyFrequency}
              </p>
            </section>

            <section className="flex flex-col gap-3" aria-labelledby="product-nutrients-title">
              <h2 id="product-nutrients-title" className="text-xl font-bold text-foreground">
                성분
              </h2>
              <Card className="gap-0 overflow-hidden p-0">
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
              </Card>
            </section>

            <SupplementReviewSection productId={product.productId} />

            <Button
              className="mt-auto"
              disabled={registrationPending}
              onClick={() => {
                if (alreadyRegistered) {
                  navigate('/supplements');
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
