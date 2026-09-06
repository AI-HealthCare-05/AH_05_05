import { useEffect, useState } from 'react';
import { Star } from 'lucide-react';
import { toast } from 'sonner';
import {
  fetchSupplementReviews,
  reportSupplementReview,
  type SupplementReview,
  type SupplementReviewList,
} from '@/entities/supplement';
import {
  Button,
  Card,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  StatusBadge,
} from '@/shared/ui';

const PAGE_SIZE = 10;
const reviewDateFormat = new Intl.DateTimeFormat('ko-KR', {
  month: 'long',
  day: 'numeric',
  timeZone: 'Asia/Seoul',
});

export function SupplementReviewSection({ productId }: { productId: string }) {
  const [result, setResult] = useState<SupplementReviewList | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [reportTarget, setReportTarget] = useState<SupplementReview | null>(null);
  const [reporting, setReporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setLoadError(null);
    fetchSupplementReviews(productId, { offset: 0, limit: PAGE_SIZE })
      .then((value) => {
        if (!cancelled) setResult(value);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '후기를 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  async function loadMore() {
    if (!result || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await fetchSupplementReviews(productId, {
        offset: result.items.length,
        limit: PAGE_SIZE,
      });
      setResult((current) =>
        current
          ? { ...next, items: [...current.items, ...next.items] }
          : next,
      );
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요');
    } finally {
      setLoadingMore(false);
    }
  }

  async function report() {
    if (!reportTarget || reporting) return;
    setReporting(true);
    try {
      await reportSupplementReview(reportTarget.id);
      setResult((current) =>
        current
          ? {
              ...current,
              items: current.items.filter((item) => item.id !== reportTarget.id),
              total: Math.max(0, current.total - 1),
            }
          : current,
      );
      setReportTarget(null);
      toast.success('신고했어요');
    } catch {
      setReportTarget(null);
      toast.error('잠시 후 다시 시도해주세요');
    } finally {
      setReporting(false);
    }
  }

  return (
    <section className="flex flex-col gap-3" aria-labelledby="supplement-reviews-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="supplement-reviews-title" className="text-xl font-bold text-foreground">
          후기
        </h2>
        {result && result.reviewCount > 0 && (
          <p className="text-sm font-bold text-warning-strong">
            ★{result.ratingAverage?.toFixed(1)} · {result.reviewCount}개
          </p>
        )}
      </div>

      {loadError ? (
        <p className="text-sm text-muted-foreground">{loadError}</p>
      ) : result === null ? (
        <p className="text-sm text-muted-foreground">후기를 불러오는 중...</p>
      ) : result.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">아직 후기가 없어요</p>
      ) : (
        <Card className="gap-0 overflow-hidden p-0">
          {result.items.map((review) => (
            <article
              key={review.id}
              aria-label={`${review.authorLabel} 후기`}
              className="flex flex-col gap-2 border-t border-border px-4 py-4 first:border-t-0"
            >
              <div className="flex min-w-0 items-center justify-between gap-3">
                <strong className="truncate text-sm text-foreground">{review.authorLabel}</strong>
                {review.isMine ? (
                  <StatusBadge type="done" className="shrink-0 px-2.5 py-1 text-xs">
                    내 후기
                  </StatusBadge>
                ) : (
                  <button
                    type="button"
                    className="min-h-touch shrink-0 px-1 text-sm font-bold text-muted-foreground"
                    onClick={() => setReportTarget(review)}
                  >
                    신고
                  </button>
                )}
              </div>
              {review.score !== null && (
                <div className="flex items-center gap-0.5" aria-label={`별 ${review.score}점`}>
                  {Array.from({ length: 5 }, (_, index) => (
                    <Star
                      key={index}
                      aria-hidden
                      className={`size-4 text-warning-strong ${index < review.score! ? 'fill-current' : ''}`}
                    />
                  ))}
                </div>
              )}
              {review.reviewBody !== null && (
                <p className="whitespace-pre-wrap break-words text-sm text-foreground">
                  {review.reviewBody}
                </p>
              )}
              <time className="text-xs text-muted-foreground" dateTime={review.updatedAt}>
                {reviewDateFormat.format(new Date(review.updatedAt))}
              </time>
            </article>
          ))}
        </Card>
      )}

      {result && result.items.length < result.total && (
        <Button variant="secondary" disabled={loadingMore} onClick={() => void loadMore()}>
          {loadingMore ? '불러오는 중...' : '더 보기'}
        </Button>
      )}
      {result && result.total > 0 && (
        <p className="text-xs text-muted-foreground">개인의 경험이며 효능을 보장하지 않아요</p>
      )}

      <Dialog open={reportTarget !== null} onOpenChange={(open) => !open && setReportTarget(null)}>
        <DialogContent variant="sheet" showCloseButton={false} aria-describedby="review-report-description">
          <DialogHeader>
            <DialogTitle>이 후기를 신고할까요?</DialogTitle>
            <DialogDescription id="review-report-description" className="sr-only">
              선택한 공개 후기를 신고합니다.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" disabled={reporting} onClick={() => setReportTarget(null)}>
              취소
            </Button>
            <Button variant="danger" disabled={reporting} onClick={() => void report()}>
              {reporting ? '신고 중...' : '신고하기'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
