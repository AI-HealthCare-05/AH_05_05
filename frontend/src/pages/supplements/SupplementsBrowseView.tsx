import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import {
  getSupplementRanking,
  searchSupplementProducts,
  type SupplementProduct,
  type SupplementSearchPage,
  type SupplementSortDirection,
  type SupplementSortKey,
} from '@/entities/supplement';
import { SupplementRankingCard } from '@/pages/home/SupplementRankingCard';
import { Button, Card, StatusBadge } from '@/shared/ui';

const SORT_OPTIONS: { key: SupplementSortKey; label: string }[] = [
  { key: 'name', label: '이름순' },
  { key: 'registered', label: '등록순' },
  { key: 'rating', label: '평점순' },
  { key: 'reviews', label: '후기순' },
];

const DEFAULT_SORT_DIRECTIONS: Record<SupplementSortKey, SupplementSortDirection> = {
  name: 'asc',
  registered: 'desc',
  rating: 'desc',
  reviews: 'desc',
};

const DIRECTION_OPTIONS: { key: SupplementSortDirection; label: string }[] = [
  { key: 'asc', label: '오름차순' },
  { key: 'desc', label: '내림차순' },
];

function searchRequestKey(
  query: string,
  sort: SupplementSortKey,
  direction: SupplementSortDirection,
): string {
  return JSON.stringify([query.trim(), sort, direction]);
}

interface SupplementsBrowseViewProps {
  registeredProductIds: ReadonlySet<string>;
  registrationPending: boolean;
  onSelectProduct: (productId: string) => void;
}

export function SupplementsBrowseView({
  registeredProductIds,
  registrationPending,
  onSelectProduct,
}: SupplementsBrowseViewProps) {
  const [ranking, setRanking] = useState<Awaited<ReturnType<typeof getSupplementRanking>>>(null);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SupplementSortKey>('name');
  const [direction, setDirection] = useState<SupplementSortDirection>('asc');
  const [results, setResults] = useState<SupplementSearchPage | null>(null);
  const [resultsSearchKey, setResultsSearchKey] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const searchGenerationRef = useRef(0);
  const currentSearchKey = searchRequestKey(query, sort, direction);
  const currentSearchKeyRef = useRef(currentSearchKey);

  function invalidateSearchRequests(nextSearchKey: string) {
    currentSearchKeyRef.current = nextSearchKey;
    searchGenerationRef.current += 1;
    setLoadingMore(false);
  }

  useEffect(() => {
    let cancelled = false;
    getSupplementRanking()
      .then((value) => {
        if (!cancelled) setRanking(value);
      })
      .catch(() => {
        if (!cancelled) setRanking(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    currentSearchKeyRef.current = currentSearchKey;
    const generation = ++searchGenerationRef.current;
    const trimmedQuery = query.trim();
    setLoadingMore(false);
    if (!trimmedQuery) {
      setResults(null);
      setResultsSearchKey(null);
      setSearchError(null);
      setSearching(false);
      return;
    }

    let cancelled = false;
    setSearching(true);
    setSearchError(null);
    const timer = window.setTimeout(() => {
      searchSupplementProducts({ query: trimmedQuery, sort, direction, offset: 0, limit: 20 })
        .then((page) => {
          if (
            !cancelled &&
            searchGenerationRef.current === generation &&
            currentSearchKeyRef.current === currentSearchKey
          ) {
            setResults(page);
            setResultsSearchKey(currentSearchKey);
          }
        })
        .catch((error: unknown) => {
          if (
            !cancelled &&
            searchGenerationRef.current === generation &&
            currentSearchKeyRef.current === currentSearchKey
          ) {
            setResults(null);
            setResultsSearchKey(null);
            setSearchError(
              error instanceof Error ? error.message : '검색 결과를 불러오지 못했어요.',
            );
          }
        })
        .finally(() => {
          if (
            !cancelled &&
            searchGenerationRef.current === generation &&
            currentSearchKeyRef.current === currentSearchKey
          ) {
            setSearching(false);
          }
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [currentSearchKey, direction, query, sort]);

  const visibleRanking = ranking
    ? {
        ...ranking,
        items: ranking.items.map((item) => ({
          ...item,
          alreadyRegistered: registeredProductIds.has(item.productId),
        })),
      }
    : null;

  async function loadMore() {
    const nextOffset = results?.nextOffset;
    const trimmedQuery = query.trim();
    if (
      nextOffset === null ||
      nextOffset === undefined ||
      !trimmedQuery ||
      loadingMore ||
      searching ||
      resultsSearchKey !== currentSearchKey
    ) {
      return;
    }
    const generation = searchGenerationRef.current;
    const requestSearchKey = currentSearchKey;
    setLoadingMore(true);
    setSearchError(null);
    try {
      const next = await searchSupplementProducts({
        query: trimmedQuery,
        sort,
        direction,
        offset: nextOffset,
        limit: 20,
      });
      if (
        searchGenerationRef.current !== generation ||
        currentSearchKeyRef.current !== requestSearchKey
      ) {
        return;
      }
      setResults((current) => {
        if (
          searchGenerationRef.current !== generation ||
          currentSearchKeyRef.current !== requestSearchKey
        ) {
          return current;
        }
        return current
          ? { ...next, items: [...current.items, ...next.items], total: next.total }
          : next;
      });
    } catch (error: unknown) {
      if (
        searchGenerationRef.current === generation &&
        currentSearchKeyRef.current === requestSearchKey
      ) {
        setSearchError(error instanceof Error ? error.message : '검색 결과를 더 불러오지 못했어요.');
      }
    } finally {
      if (
        searchGenerationRef.current === generation &&
        currentSearchKeyRef.current === requestSearchKey
      ) {
        setLoadingMore(false);
      }
    }
  }

  return (
    <>
      <label className="relative block">
        <span className="sr-only">영양제 제품 검색</span>
        <Search
          aria-hidden
          className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground"
        />
        <input
          type="search"
          value={query}
          placeholder="제품명 또는 성분 검색"
          className="h-12 w-full rounded-input border border-border bg-card pl-11 pr-4 text-base text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
          onChange={(event) => {
            const nextQuery = event.target.value;
            invalidateSearchRequests(searchRequestKey(nextQuery, sort, direction));
            setQuery(nextQuery);
          }}
        />
      </label>

      {results && results.items.length > 0 ? (
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-4 gap-2" role="group" aria-label="검색 결과 정렬">
            {SORT_OPTIONS.map((option) => {
              const selected = sort === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={selected}
                  className={`min-h-touch rounded-pill px-2 text-sm font-bold ${
                    selected ? 'bg-primary text-card' : 'bg-muted-bg text-muted-foreground'
                  }`}
                  onClick={() => {
                    if (selected) return;
                    const nextDirection = DEFAULT_SORT_DIRECTIONS[option.key];
                    invalidateSearchRequests(searchRequestKey(query, option.key, nextDirection));
                    setSort(option.key);
                    setDirection(nextDirection);
                  }}
                >
                  {option.label}
                  {selected ? (direction === 'asc' ? ' ▲' : ' ▼') : null}
                </button>
              );
            })}
          </div>
          <div className="grid grid-cols-2 gap-2" role="group" aria-label="정렬 방향">
            {DIRECTION_OPTIONS.map((option) => {
              const selected = direction === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={selected}
                  className={`min-h-touch rounded-pill px-3 text-sm font-bold ${
                    selected ? 'bg-primary text-card' : 'bg-muted-bg text-muted-foreground'
                  }`}
                  onClick={() => {
                    if (selected) return;
                    invalidateSearchRequests(searchRequestKey(query, sort, option.key));
                    setDirection(option.key);
                  }}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {query.trim() ? (
        <SearchResults
          results={results}
          registeredProductIds={registeredProductIds}
          searching={searching}
          loadingMore={loadingMore}
          loadMoreDisabled={
            loadingMore || searching || resultsSearchKey !== currentSearchKey
          }
          error={searchError}
          onSelectProduct={onSelectProduct}
          onLoadMore={loadMore}
        />
      ) : visibleRanking ? (
        <SupplementRankingCard
          ranking={visibleRanking}
          registrationPending={registrationPending}
          onSelect={onSelectProduct}
        />
      ) : null}
    </>
  );
}

function SearchResults({
  results,
  registeredProductIds,
  searching,
  loadingMore,
  loadMoreDisabled,
  error,
  onSelectProduct,
  onLoadMore,
}: {
  results: SupplementSearchPage | null;
  registeredProductIds: ReadonlySet<string>;
  searching: boolean;
  loadingMore: boolean;
  loadMoreDisabled: boolean;
  error: string | null;
  onSelectProduct: (productId: string) => void;
  onLoadMore: () => void;
}) {
  if (searching && results === null) {
    return <p className="text-sm text-muted-foreground">검색 중...</p>;
  }
  if (error && results === null) {
    return <Card title="검색 결과를 불러오지 못했어요">{error}</Card>;
  }
  if (!results || results.items.length === 0) {
    return <p className="text-sm text-muted-foreground">검색 결과가 없어요.</p>;
  }

  return (
    <section className="flex flex-col gap-3" aria-label="영양제 검색 결과">
      <p className="text-sm text-muted-foreground">검색 결과 {results.total}개</p>
      <Card className="gap-0 overflow-hidden p-0">
        <ul>
          {results.items.map((product) => (
            <SearchResultItem
              key={product.productId}
              product={product}
              alreadyRegistered={registeredProductIds.has(product.productId)}
              onSelect={() => onSelectProduct(product.productId)}
            />
          ))}
        </ul>
      </Card>
      {error && <p className="text-sm text-danger-strong">{error}</p>}
      {results.nextOffset !== null && (
        <Button variant="secondary" disabled={loadMoreDisabled} onClick={onLoadMore}>
          {loadingMore ? '불러오는 중...' : '더 보기'}
        </Button>
      )}
    </section>
  );
}

function SearchResultItem({
  product,
  alreadyRegistered,
  onSelect,
}: {
  product: SupplementProduct;
  alreadyRegistered: boolean;
  onSelect: () => void;
}) {
  return (
    <li className="border-t border-border first:border-t-0">
      <button
        type="button"
        className="flex min-h-touch w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted-bg"
        onClick={onSelect}
      >
        <span className="min-w-0 flex-1">
          <strong className="block [overflow-wrap:anywhere] text-base text-foreground">{product.productName}</strong>
          {product.ratingAverage !== null && product.reviewCount > 0 && (
            <span className="mt-1 block text-sm font-bold text-warning-strong">
              ★{product.ratingAverage.toFixed(1)} · 후기: {product.reviewCount}개
            </span>
          )}
        </span>
        {alreadyRegistered && (
          <StatusBadge type="active" className="shrink-0 px-2.5 py-1 text-xs">
            복용 중
          </StatusBadge>
        )}
        <DrawnChevron direction="right" className="size-5 shrink-0 text-disabled-foreground" />
      </button>
    </li>
  );
}
