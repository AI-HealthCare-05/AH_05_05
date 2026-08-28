import { ChevronRight } from 'lucide-react';
import type { SupplementRanking } from '@/entities/supplement';
import { Card, StatusBadge } from '@/shared/ui';

interface SupplementRankingCardProps {
  ranking: SupplementRanking;
  onSelect: (productId: string) => void;
}

export function SupplementRankingCard({ ranking, onSelect }: SupplementRankingCardProps) {
  return (
    <section
      aria-label="영양제 랭킹"
      className="flex flex-col gap-3"
    >
      <div>
        <h2 className="text-xl font-bold text-foreground">{ranking.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">포케가 골랐어요</p>
      </div>

      <Card className="gap-0 overflow-hidden p-0">
        <ol>
          {ranking.items.map((item) => (
            <li
              key={item.productId}
              className="min-h-touch border-t border-border first:border-t-0"
            >
              {item.alreadyRegistered ? (
                <div className="flex min-h-touch items-center gap-3 px-4 py-2">
                  <RankNumber rank={item.rank} />
                  <strong className="min-w-0 flex-1 truncate text-base text-foreground">
                    {item.name}
                  </strong>
                  <StatusBadge type="done" className="px-2.5 py-1 text-xs">
                    등록됨
                  </StatusBadge>
                </div>
              ) : (
                <button
                  type="button"
                  aria-label={`${item.rank}위 ${item.name} 영양제 추가`}
                  className="flex min-h-touch w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-muted-bg"
                  onClick={() => onSelect(item.productId)}
                >
                  <RankNumber rank={item.rank} />
                  <strong className="min-w-0 flex-1 truncate text-base text-foreground">
                    {item.name}
                  </strong>
                  <ChevronRight aria-hidden className="size-5 shrink-0 text-disabled-foreground" />
                </button>
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
