import { useEffect, useRef, useState, type UIEvent } from 'react';
import { Check, Info, Search } from 'lucide-react';
import {
  getSupplementProduct,
  searchSupplementProducts,
  type AddSupplementPayload,
  type SupplementProduct,
} from '@/entities/supplement';
import { USE_MOCK } from '@/shared/config/env';
import type { MealSlot } from '@/shared/model/mealSlot';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DoseSlotFields,
  Input,
} from '@/shared/ui';
import { cn } from '@/shared/lib/cn';

interface AddSupplementSheetProps {
  open: boolean;
  presetProductId?: string | null;
  onOpenChange: (open: boolean) => void;
  onSave: (payload: AddSupplementPayload) => Promise<void>;
}

const PAGE_SIZE = 20;
const DEFAULT_DOSE_AMOUNT = 1;

export function AddSupplementSheet({
  open,
  presetProductId = null,
  onOpenChange,
  onSave,
}: AddSupplementSheetProps) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [results, setResults] = useState<SupplementProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [doseAmount, setDoseAmount] = useState(DEFAULT_DOSE_AMOUNT);
  const [slots, setSlots] = useState<MealSlot[]>(['morning']);
  const [searching, setSearching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [manualMode, setManualMode] = useState(false);
  const [manualName, setManualName] = useState('');
  const [saving, setSaving] = useState(false);
  const [presetMode, setPresetMode] = useState(false);
  const searchGenerationRef = useRef(0);

  useEffect(() => {
    if (!open || manualMode || presetMode) return;
    setDebouncedQuery('');
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;
    const timer = window.setTimeout(() => setDebouncedQuery(trimmedQuery), 300);
    return () => window.clearTimeout(timer);
  }, [manualMode, open, presetMode, query]);

  useEffect(() => {
    if (!open || !presetProductId) return;
    const generation = ++searchGenerationRef.current;
    setPresetMode(true);
    setManualMode(false);
    setQuery('');
    setDebouncedQuery('');
    setResults([]);
    setTotal(0);
    setNextOffset(null);
    setSelectedProductId(null);
    setSearching(true);
    setSearchError(null);
    getSupplementProduct(presetProductId)
      .then((product) => {
        if (generation !== searchGenerationRef.current) return;
        setResults([product]);
        setTotal(1);
        setSelectedProductId(product.productId);
        setDoseAmount(product.recommendedDoseAmount ?? DEFAULT_DOSE_AMOUNT);
        setSlots(product.recommendedSlots);
      })
      .catch((error: unknown) => {
        if (generation !== searchGenerationRef.current) return;
        setSearchError(
          error instanceof Error ? error.message : '제품 정보를 불러오지 못했어요.',
        );
      })
      .finally(() => {
        if (generation === searchGenerationRef.current) setSearching(false);
      });
    return () => {
      if (generation === searchGenerationRef.current) searchGenerationRef.current += 1;
    };
  }, [open, presetProductId]);

  useEffect(() => {
    if (presetMode || (presetProductId && !query.trim())) return;
    const generation = ++searchGenerationRef.current;
    setLoadingMore(false);
    if (!open || !debouncedQuery || manualMode) {
      setResults([]);
      setTotal(0);
      setNextOffset(null);
      setSearching(false);
      setSearchError(null);
      return;
    }

    setSearching(true);
    setSearchError(null);
    setResults([]);
    setTotal(0);
    setNextOffset(null);
    searchSupplementProducts({ query: debouncedQuery, limit: PAGE_SIZE })
      .then((page) => {
        if (generation !== searchGenerationRef.current) return;
        setResults(page.items);
        setTotal(page.total);
        setNextOffset(page.nextOffset);
      })
      .catch((error: unknown) => {
        if (generation !== searchGenerationRef.current) return;
        setSearchError(error instanceof Error ? error.message : '제품을 검색하지 못했어요.');
      })
      .finally(() => {
        if (generation === searchGenerationRef.current) setSearching(false);
      });
    return () => {
      if (generation === searchGenerationRef.current) searchGenerationRef.current += 1;
    };
  }, [debouncedQuery, manualMode, open, presetMode, presetProductId, query]);

  const selectedProduct =
    results.find((product) => product.productId === selectedProductId) ?? null;

  function reset() {
    searchGenerationRef.current += 1;
    setQuery('');
    setDebouncedQuery('');
    setResults([]);
    setTotal(0);
    setNextOffset(null);
    setSelectedProductId(null);
    setDoseAmount(DEFAULT_DOSE_AMOUNT);
    setSlots(['morning']);
    setSearchError(null);
    setManualMode(false);
    setManualName('');
    setSaving(false);
    setPresetMode(false);
  }

  function changeOpen(nextOpen: boolean) {
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  }

  function selectProduct(product: SupplementProduct) {
    setManualMode(false);
    setSelectedProductId(product.productId);
    setDoseAmount(product.recommendedDoseAmount ?? DEFAULT_DOSE_AMOUNT);
    setSlots(product.recommendedSlots);
  }

  async function loadMore() {
    if (nextOffset === null || loadingMore || !debouncedQuery) return;
    const generation = searchGenerationRef.current;
    const requestedQuery = debouncedQuery;
    setLoadingMore(true);
    try {
      const page = await searchSupplementProducts({
        query: requestedQuery,
        offset: nextOffset,
        limit: PAGE_SIZE,
      });
      if (generation !== searchGenerationRef.current) return;
      setResults((current) => appendUniqueProducts(current, page.items));
      setNextOffset(page.nextOffset);
    } catch (error: unknown) {
      if (generation !== searchGenerationRef.current) return;
      setSearchError(error instanceof Error ? error.message : '다음 제품을 불러오지 못했어요.');
    } finally {
      if (generation === searchGenerationRef.current) setLoadingMore(false);
    }
  }

  function handleResultsScroll(event: UIEvent<HTMLUListElement>) {
    const list = event.currentTarget;
    const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight <= 80;
    if (nearBottom) void loadMore();
  }

  async function addStandardProduct() {
    if (!selectedProduct || slots.length === 0 || saving) return;
    setSaving(true);
    try {
      await onSave({
        source: 'standard',
        productId: selectedProduct.productId,
        name: selectedProduct.productName,
        doseAmount,
        doseUnit: selectedProduct.doseUnit,
        slots,
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
    if (!name || slots.length === 0 || saving) return;
    setSaving(true);
    try {
      await onSave({
        source: 'manual',
        name,
        doseAmount,
        doseUnit: '정',
        slots,
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
            제품명으로 검색하고 1회 섭취량과 복용 시간대를 확인합니다.
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
                searchGenerationRef.current += 1;
                setLoadingMore(false);
                setPresetMode(false);
                setQuery(event.target.value);
                setSelectedProductId(null);
                setManualMode(false);
              }}
              placeholder={USE_MOCK ? '제품명이나 브랜드를 입력해 주세요' : '제품명을 입력해 주세요'}
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
            <DoseSlotFields
              doseAmount={doseAmount}
              doseUnit="정"
              slots={slots}
              onDoseAmountChange={setDoseAmount}
              onSlotsChange={setSlots}
            />
            <div className="rounded-card bg-muted-bg p-4 text-sm text-muted-foreground">
              직접 입력한 제품은 성분을 확인할 수 없어 성분 합계에서 제외합니다.
            </div>
            <div className="mt-auto flex flex-col gap-2">
              <Button
                disabled={!manualName.trim() || slots.length === 0 || saving}
                onClick={() => void addManualProduct()}
              >
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
                    {USE_MOCK
                      ? '통 앞면의 브랜드를 함께 넣으면 빨리 찾아요 — 예: 센트룸 종합비타민'
                      : '제품명 일부를 더 입력하면 결과를 좁힐 수 있어요.'}
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
                    {USE_MOCK
                      ? '통 앞면의 제품명을 확인하거나 직접 입력해 주세요.'
                      : '제품명을 다시 확인해 주세요.'}
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
                                {USE_MOCK
                                  ? `${product.manufacturer} · ${product.dosageForm} · ${product.packageAmount}`
                                  : `${product.servingDescription} · ${product.servingSize} · 1일 ${product.dailyFrequency}`}
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
                              <DoseSlotFields
                                doseAmount={doseAmount}
                                doseUnit={product.doseUnit}
                                doseStep={doseStepFor(product.recommendedDoseAmount)}
                                slots={slots}
                                onDoseAmountChange={setDoseAmount}
                                onSlotsChange={setSlots}
                              />
                              {product.recommendedDoseAmount !== null && (
                                <p className="text-sm text-muted-foreground">
                                  제품 표시사항의 섭취방법을 채워놨어요.
                                </p>
                              )}
                              <Button
                                disabled={slots.length === 0 || saving}
                                onClick={() => void addStandardProduct()}
                              >
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
                  {USE_MOCK ? '제품명이나 통 앞면의 브랜드를 검색해 주세요.' : '제품명을 검색해 주세요.'}
                </div>
              )}
            </div>

            {USE_MOCK && <div className="-mx-5 flex shrink-0 items-center justify-center gap-2 border-t border-border px-5 py-4 text-sm text-muted-foreground">
              <span>찾는 제품이 없나요?</span>
              <button
                type="button"
                className="min-h-touch font-bold text-primary-strong"
                onClick={() => {
                  setSelectedProductId(null);
                  setManualName('');
                  setDoseAmount(DEFAULT_DOSE_AMOUNT);
                  setSlots(['morning']);
                  setManualMode(true);
                }}
              >
                직접 입력
              </button>
            </div>}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function doseStepFor(recommendedAmount: number | null): number {
  if (recommendedAmount === null || !Number.isFinite(recommendedAmount)) return 1;
  const fraction = Math.round((recommendedAmount % 1) * 1_000) / 1_000;
  return fraction > 0 ? fraction : 1;
}

function appendUniqueProducts(
  current: SupplementProduct[],
  incoming: SupplementProduct[],
): SupplementProduct[] {
  const productIds = new Set(current.map(({ productId }) => productId));
  return [...current, ...incoming.filter(({ productId }) => !productIds.has(productId))];
}
