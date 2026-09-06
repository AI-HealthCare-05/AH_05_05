import { cn } from '@/shared/lib/cn';
import type { ChatSource, SourceScope } from '@/entities/chat';

/**
 * 답변의 근거 목록.
 *
 * 이 컴포넌트가 화면 17의 핵심입니다. 복약 안내에서 출처를 빼기로 정했으므로(명세 11번)
 * 공공 근거가 화면에 드러나는 곳이 여기뿐입니다. 나중에 다른 화면에서도 쓸 수 있게
 * 페이지에서 분리해뒀습니다.
 *
 * `sources` 가 비어 있으면 이 컴포넌트를 그리지 마세요 — 호출부(ChatPage)에서
 * 근거 없음 안내로 갈라줍니다. 근거가 없는데 있는 것처럼 보이는 게 이 서비스에서
 * 가장 위험한 실패입니다.
 */
const SCOPE_LABEL: Record<SourceScope, string> = {
  personal: '내 문서',
  official: '공식 자료',
};

export interface SourceListProps {
  sources: ChatSource[];
  className?: string;
}

export function SourceList({ sources, className }: SourceListProps) {
  if (sources.length === 0) return null;

  return (
    <div className={cn('flex flex-col gap-1.5 border-t border-border pt-2', className)}>
      <h3 className="text-sm font-bold text-foreground">근거</h3>
      <ul className="flex flex-col gap-1.5">
        {sources.map((source, index) => (
          <li key={`${source.scope}-${source.title}-${index}`} className="flex flex-col gap-0.5">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span
                className={cn(
                  'shrink-0 rounded-pill px-2 py-0.5 text-sm',
                  source.scope === 'personal'
                    ? 'bg-primary-bg text-primary-strong'
                    : 'bg-info-bg text-info',
                )}
              >
                {SCOPE_LABEL[source.scope]}
              </span>
              <span className="text-sm text-foreground">{source.title}</span>
            </div>
            {source.organization && (
              <span className="text-sm text-muted-foreground">{source.organization}</span>
            )}
            {source.url && (
              // 원문을 확인할 수 있어야 근거가 의미를 갖습니다.
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-touch items-center text-sm text-primary underline"
              >
                새 창에서 열기
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
