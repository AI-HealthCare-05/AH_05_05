import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { ChallengeTypeBadge } from './ChallengeTypeBadge';
import './today-challenges.css';

export interface TodayChallengeCard {
  id: string;
  title: string;
  href: string;
  official: boolean;
  image: string;
  badgeName: string;
  progress: string;
  rate: number;
  completed: boolean;
  onCheckIn?: () => void;
  pending?: boolean;
  error?: string;
}

export function TodayChallengeCarousel({ items }: { items: TodayChallengeCard[] }) {
  const viewport = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const update = () => setEdges({ left: element.scrollLeft > 2, right: element.scrollLeft + element.clientWidth < element.scrollWidth - 2 });
    const observer = new ResizeObserver(update);
    observer.observe(element);
    element.addEventListener('scroll', update, { passive: true });
    update();
    return () => { observer.disconnect(); element.removeEventListener('scroll', update); };
  }, [items]);

  function move(direction: number) {
    const element = viewport.current;
    if (!element) return;
    element.scrollBy({ left: direction * 156, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }

  return <div className="relative min-w-0">
    <div ref={viewport} aria-label="오늘 할 챌린지" tabIndex={0} className="rx-today-challenge-scroll">
      {items.map(item => <article key={item.id} aria-label={item.title} className="rx-today-challenge-item">
        <Link to={item.href} aria-label={`${item.title}, ${item.progress}, 상세 보기`} className="rx-today-challenge-detail">
        <ChallengeTypeBadge official={item.official} />
        <img src={item.image} alt={item.badgeName} width={56} height={56} className="size-14 self-center rounded-pill object-contain" />
        <span className="rx-challenge-title text-center text-sm font-bold [overflow-wrap:anywhere]">{item.title}</span>
        <span className="mt-auto text-center text-caption text-muted-foreground">{item.progress}</span>
        <span role="progressbar" aria-label={`${item.title} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.rate} className="rx-challenge-track h-1 w-full overflow-hidden rounded-pill bg-border">
          <span className="block h-full rounded-pill bg-primary" style={{ width: `${item.rate}%` }} />
        </span>
        </Link>
        {item.completed ? <p className="rx-today-challenge-state text-primary" aria-live="polite"><svg aria-hidden="true" className="rx-drawn-icon size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 4 4L19 6" pathLength="1" /></svg>완료</p>
          : item.onCheckIn ? <div className="flex items-center gap-2">{!item.official && <span className="text-micro text-muted-foreground">미완료</span>}<button type="button" aria-label={`${item.title} 했어요`} disabled={item.pending} onClick={item.onCheckIn} className="rx-today-challenge-checkin min-w-0 flex-1">{item.pending ? '저장 중…' : '했어요'}</button></div>
          : !item.official && <p className="rx-today-challenge-state text-muted-foreground" aria-live="polite">미완료</p>}
        {item.error && <p role="alert" className="text-center text-caption text-destructive">{item.error}</p>}
      </article>)}
    </div>
    {(edges.left || edges.right) && <div className="mt-2 flex justify-end gap-2">
      <button type="button" aria-label="이전 챌린지" disabled={!edges.left} className="rx-today-challenge-arrow" onClick={() => move(-1)}><DrawnChevron direction="left" className="size-5" /></button>
      <button type="button" aria-label="다음 챌린지" disabled={!edges.right} className="rx-today-challenge-arrow" onClick={() => move(1)}><DrawnChevron direction="right" className="size-5" /></button>
    </div>}
  </div>;
}
