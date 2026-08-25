import { useEffect, useState, type UIEvent } from 'react';
import { Check, Info, Minus, Plus, Search } from 'lucide-react';
import {
  searchSupplementProducts,
  type AddSupplementPayload,
  type SupplementProduct,
} from '@/entities/supplement';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Input,
} from '@/shared/ui';
import { cn } from '@/shared/lib/cn';

interface AddSupplementSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (payload: AddSupplementPayload) => Promise<void>;
}

const PAGE_SIZE = 20;
const MIN_DAILY_COUNT = 1;
const MAX_DAILY_COUNT = 20;

export function AddSupplementSheet({ open, onOpenChange, onSave }: AddSupplementSheetProps) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [results, setResults] = useState<SupplementProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [dailyCount, setDailyCount] = useState(MIN_DAILY_COUNT);
  const [searching, setSearching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [manualMode, setManualMode] = useState(false);
  const [manualName, setManualName] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || manualMode) return;
    setDebouncedQuery('');
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;
    const timer = window.setTimeout(() => setDebouncedQuery(trimmedQuery), 300);
    return () => window.clearTimeout(timer);
  }, [manualMode, open, query]);

  useEffect(() => {
    if (!open || !debouncedQuery || manualMode) {
      setResults([]);
      setTotal(0);
      setNextOffset(null);
      setSearching(false);
      setSearchError(null);
      return;
    }

    let cancelled = false;
    setSearching(true);
    setSearchError(null);
    setResults([]);
    setTotal(0);
    setNextOffset(null);
    searchSupplementProducts({ query: debouncedQuery, limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        setResults(page.items);
        setTotal(page.total);
        setNextOffset(page.nextOffset);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setSearchError(error instanceof Error ? error.message : '제품을 검색하지 못했어요.');
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, manualMode, open]);

  const selectedProduct =
    results.find((product) => product.productId === selectedProductId) ?? null;

  function reset() {
    setQuery('');
    setDebouncedQuery('');
    setResults([]);
    setTotal(0);
    setNextOffset(null);
    setSelectedProductId(null);
    setDailyCount(MIN_DAILY_COUNT);
    setSearchError(null);
    setManualMode(false);
    setManualName('');
    setSaving(false);
  }

  function changeOpen(nextOpen: boolean) {
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  }

  function selectProduct(product: SupplementProduct) {
    setManualMode(false);
    setSelectedProductId(product.productId);
    setDailyCount(product.recommendedDailyCount ?? MIN_DAILY_COUNT);
  }

  async function loadMore() {
    if (nextOffset === null || loadingMore || !debouncedQuery) return;
    setLoadingMore(true);
    try {
      const page = await searchSupplementProducts({
        query: debouncedQuery,
        offset: nextOffset,
        limit: PAGE_SIZE,
      });
      setResults((current) => [...current, ...page.items]);
      setNextOffset(page.nextOffset);
    } catch (error: unknown) {
      setSearchError(error instanceof Error ? error.message : '다음 제품을 불러오지 못했어요.');
    } finally {
      setLoadingMore(false);
    }
  }

  function handleResultsScroll(event: UIEvent<HTMLUListElement>) {
    const list = event.currentTarget;
    const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight <= 80;
    if (nearBottom) void loadMore();
  }

  async function addStandardProduct() {
    if (!selectedProduct || saving) return;
    setSaving(true);
    try {
      await onSave({
        source: 'standard',
        productId: selectedProduct.productId,
        name: selectedProduct.productName,
        dailyCount,
        times: ['아침'],
      });
      changeOpen(false);
    } catch {
      // 저장 실패는 부모 화면의 ErrorDialog가 표시합니다.
    } finally {
      setSaving(false);
    }
  }

  async function addManualProduct() {
    const name = manualName.trim();
    if (!name || saving) return;
    setSaving(true);
    try {
      await onSave({
        source: 'manual',
        name,
        dailyCount: MIN_DAILY_COUNT,
        times: ['아침'],
      });
      changeOpen(false);
    } catch {
      // 저장 실패는 부모 화면의 ErrorDialog가 표시합니다.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent
        variant="sheet"
        aria-describedby="supplement-add-description"
        className="flex max-h-[88dvh] min-h-[70dvh] flex-col gap-4 overflow-hidden p-5 pb-0"
      >
        <span aria-hidden className="mx-auto h-1 w-10 shrink-0 rounded-pill bg-border" />
        <div className="shrink-0 pr-10">
          <DialogTitle className="text-2xl">영양제 추가</DialogTitle>
          <DialogDescription id="supplement-add-description" className="sr-only">
            제품명이나 브랜드로 검색하고 1일 섭취 정수를 확인합니다.
          </DialogDescription>
        </div>

        {!manualMode && (
          <div className="relative shrink-0">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-disabled-foreground"
            />
            <Input
              type="search"
              aria-label="영양제 제품 검색"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setSelectedProductId(null);
                setManualMode(false);
              }}
              placeholder="제품명이나 브랜드를 입력해 주세요"
              className="[&_input]:pl-11"
            />
          </div>
        )}

        {manualMode ? (
          <section
            className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-2"
            aria-labelledby="manual-supplement-title"
          >
            <div>
              <h3 id="manual-supplement-title" className="text-lg font-bold text-foreground">
                제품명 직접 입력
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                성분 정보는 계산에 넣지 않고 목록에만 저장해요.
              </p>
            </div>
            <Input
              label="제품명"
              aria-label="직접 입력 제품명"
              value={manualName}
              onChange={(event) => setManualName(event.target.value)}
              placeholder="통 앞면의 제품명"
              autoFocus
            />
            <div className="rounded-card bg-muted-bg p-4 text-sm text-muted-foreground">
              직접 입력한 제품은 성분을 확인할 수 없어 성분 합계에서 제외합니다.
            </div>
            <div className="mt-auto flex flex-col gap-2">
              <Button disabled={!manualName.trim() || saving} onClick={() => void addManualProduct()}>
                {saving ? '추가 중...' : '추가하기'}
              </Button>
              <Button variant="secondary" onClick={() => setManualMode(false)}>
                검색으로 돌아가기
              </Button>
            </div>
          </section>
        ) : (
          <>
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
              {total > PAGE_SIZE && (
                <div className="flex shrink-0 items-start gap-2 rounded-card bg-primary-bg p-3 text-sm text-muted-foreground">
                  <Info aria-hidden className="mt-0.5 size-5 shrink-0 text-primary-strong" />
                  <p>
                    <strong className="font-bold text-foreground">{total}개가 찾아졌어요.</strong>{' '}
                    통 앞면의 브랜드를 함께 넣으면 빨리 찾아요 — 예: 센트룸 종합비타민
                  </p>
                </div>
              )}

              {searching ? (
                <p role="status" className="py-8 text-center text-sm text-muted-foreground">
                  제품을 찾는 중...
                </p>
              ) : searchError ? (
                <div className="rounded-card bg-muted-bg p-4 text-sm text-muted-foreground">
                  {searchError}
                </div>
              ) : debouncedQuery && results.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
                  <p className="text-lg font-bold text-foreground">찾지 못했어요</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    통 앞면의 제품명을 확인하거나 직접 입력해 주세요.
                  </p>
                </div>
              ) : results.length > 0 ? (
                <ul
                  aria-label="검색 결과"
                  className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-2"
                  onScroll={handleResultsScroll}
                >
                  {results.map((product) => {
                    const selected = product.productId === selectedProductId;
                    return (
                      <li key={product.productId}>
                        <article
                          className={cn(
                            'overflow-hidden rounded-card border bg-card shadow-card',
                            selected ? 'border-primary' : 'border-transparent',
                          )}
                        >
                          <button
                            type="button"
                            aria-expanded={selected}
                            className="flex min-h-touch w-full items-center gap-3 px-4 py-3 text-left"
                            onClick={() => selectProduct(product)}
                          >
                            <span className="min-w-0 flex-1">
                              <strong className="block text-base font-bold text-foreground">
                                {product.productName}
                              </strong>
                              <span className="mt-1 block text-sm text-muted-foreground">
                                {product.manufacturer} · {product.dosageForm} · {product.packageAmount}
                              </span>
                            </span>
                            {selected && (
                              <span
                                aria-label="선택됨"
                                className="flex size-8 shrink-0 items-center justify-center rounded-pill bg-primary text-card"
                              >
                                <Check aria-hidden className="size-5" />
                              </span>
                            )}
                          </button>

                          {selected && (
                            <div className="mx-4 flex flex-col gap-3 border-t border-border py-4">
                              <div className="flex items-center justify-between gap-3">
                                <span className="text-base text-muted-foreground">하루에</span>
                                <div className="flex items-center gap-3">
                                  <button
                                    type="button"
                                    aria-label="하루 섭취량 줄이기"
                                    disabled={dailyCount <= MIN_DAILY_COUNT}
                                    onClick={() =>
                                      setDailyCount((count) =>
                                        Math.max(MIN_DAILY_COUNT, count - 1),
                                      )
                                    }
                                    className="flex size-touch items-center justify-center rounded-pill border border-border text-foreground disabled:text-disabled-foreground"
                                  >
                                    <Minus aria-hidden className="size-5" />
                                  </button>
                                  <strong className="min-w-12 text-center text-xl font-bold text-foreground tnum">
                                    {dailyCount} 정
                                  </strong>
                                  <button
                                    type="button"
                                    aria-label="하루 섭취량 늘리기"
                                    disabled={dailyCount >= MAX_DAILY_COUNT}
                                    onClick={() =>
                                      setDailyCount((count) =>
                                        Math.min(MAX_DAILY_COUNT, count + 1),
                                      )
                                    }
                                    className="flex size-touch items-center justify-center rounded-pill border border-border text-foreground disabled:text-disabled-foreground"
                                  >
                                    <Plus aria-hidden className="size-5" />
                                  </button>
                                </div>
                              </div>
                              {product.recommendedDailyCount !== null && (
                                <p className="text-sm text-muted-foreground">
                                  제품 표시사항의 섭취방법을 채워놨어요.
                                </p>
                              )}
                              <Button disabled={saving} onClick={() => void addStandardProduct()}>
                                {saving ? '추가 중...' : '추가하기'}
                              </Button>
                            </div>
                          )}
                        </article>
                      </li>
                    );
                  })}
                  {loadingMore && (
                    <li role="status" className="py-3 text-center text-sm text-muted-foreground">
                      더 불러오는 중...
                    </li>
                  )}
                </ul>
              ) : (
                <div className="flex flex-1 items-center justify-center text-center text-sm text-muted-foreground">
                  제품명이나 통 앞면의 브랜드를 검색해 주세요.
                </div>
              )}
            </div>

            <div className="-mx-5 flex shrink-0 items-center justify-center gap-2 border-t border-border px-5 py-4 text-sm text-muted-foreground">
              <span>찾는 제품이 없나요?</span>
              <button
                type="button"
                className="min-h-touch font-bold text-primary-strong"
                onClick={() => {
                  setSelectedProductId(null);
                  setManualName('');
                  setManualMode(true);
                }}
              >
                직접 입력
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
