import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import type { SupplementRanking } from '@/entities/supplement';
import { Card, StatusBadge } from '@/shared/ui';

interface SupplementRankingCardProps {
  ranking: SupplementRanking;
  registrationPending: boolean;
  onSelect?: (productId: string) => void;
  maxItems?: number;
  onMore?: () => void;
  title?: string;
  subtitle?: string;
}

export function SupplementRankingCard({
  ranking,
  registrationPending,
  onSelect,
  maxItems,
  onMore,
  title,
  subtitle,
}: SupplementRankingCardProps) {
  const items = maxItems === undefined ? ranking.items : ranking.items.slice(0, maxItems);
  if (items.length === 0) return null;

  return (
    <section aria-label="영양제 랭킹" className="flex flex-col gap-3 motion-safe:animate-[rx-overlay-in_200ms_ease-out]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-foreground">{title ?? ranking.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {subtitle ?? 'RxVita가 골랐어요'}
          </p>
        </div>
        {onMore && (
          <button
            type="button"
            className="min-h-touch shrink-0 px-1 text-caption font-bold text-primary-strong"
            onClick={onMore}
          >
            전체 보기 <DrawnChevron direction="right" className="inline size-3.5 align-middle" />
          </button>
        )}
      </div>

      <Card className="gap-0 overflow-hidden p-0">
        <ol>
          {items.map((item) => (
            <li
              key={item.productId}
              className="min-h-touch border-t border-border first:border-t-0"
            >
              {onSelect ? (
                <button
                  type="button"
                  aria-label={`${item.rank}위 ${item.name} 제품 정보`}
                  className="flex min-h-touch w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-muted-bg"
                  onClick={() => onSelect(item.productId)}
                >
                  <RankNumber rank={item.rank} />
                  <strong className="min-w-0 flex-1 [overflow-wrap:anywhere] text-base text-foreground">
                    {item.name}
                  </strong>
                  {!registrationPending && item.alreadyRegistered && (
                    <StatusBadge type="done" className="px-2.5 py-1 text-xs">등록됨</StatusBadge>
                  )}
                  <DrawnChevron direction="right" className="size-5 shrink-0 text-disabled-foreground" />
                </button>
              ) : (
                <div className="flex min-h-touch items-center gap-3 px-4 py-2">
                  <RankNumber rank={item.rank} />
                  <strong className="min-w-0 flex-1 [overflow-wrap:anywhere] text-base text-foreground">
                    {item.name}
                  </strong>
                </div>
              )}
            </li>
          ))}
        </ol>
      </Card>
    </section>
  );
}

function RankNumber({ rank }: { rank: number }) {
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-pill bg-muted-bg text-sm font-bold text-foreground tnum">
      {rank}
    </span>
  );
}
