import { ChevronDown } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';

/** Watermelon accordion-2: independent card panels, stronger shadow when open. */
export function ChallengeAccordion({ title, count, children }: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`} className={`rounded-card bg-card transition-shadow motion-reduce:transition-none ${expanded ? 'shadow-card' : 'shadow-sm'}`}>
      <h2 aria-label={title}>
        <button
          type="button"
          aria-label={`${title} ${expanded ? '접기' : '펼치기'}`}
          aria-expanded={expanded}
          aria-controls={`${id}-panel`}
          onClick={() => setExpanded(value => !value)}
          className="flex min-h-14 w-full items-center gap-3 rounded-card px-5 py-3 text-left text-base font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span id={`${id}-title`} className="min-w-0 flex-1">{title}</span>
          {count !== undefined && <span className="text-sm font-medium text-muted-foreground tnum">{count}개</span>}
          <ChevronDown aria-hidden className={`size-5 shrink-0 text-primary transition-transform motion-reduce:transition-none ${expanded ? 'rotate-180' : ''}`} />
        </button>
      </h2>
      <div id={`${id}-panel`} hidden={!expanded}>
        {expanded && <div className="flex flex-col gap-3 px-3 pb-3">{children}</div>}
      </div>
    </section>
  );
}
