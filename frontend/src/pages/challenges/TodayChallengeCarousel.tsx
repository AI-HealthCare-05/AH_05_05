import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
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
        <span className="self-start rounded-pill bg-primary-bg px-2 py-0.5 text-micro font-bold text-primary">{item.official ? '공식' : '맞춤'}</span>
        <img src={item.image} alt={item.badgeName} width={56} height={56} className="size-14 self-center rounded-pill object-contain" />
        <span className="rx-challenge-title text-center text-sm font-bold [overflow-wrap:anywhere]">{item.title}</span>
        <span className="mt-auto text-center text-caption text-muted-foreground">{item.progress}</span>
        <span role="progressbar" aria-label={`${item.title} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.rate} className="rx-challenge-track h-1 w-full overflow-hidden rounded-pill bg-border">
          <span className="block h-full rounded-pill bg-primary" style={{ width: `${item.rate}%` }} />
        </span>
        </Link>
        {item.completed ? <p className="rx-today-challenge-state text-primary" aria-live="polite"><svg aria-hidden="true" className="rx-drawn-icon size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 4 4L19 6" pathLength="1" /></svg>달성</p>
          : item.onCheckIn ? <button type="button" aria-label={`${item.title} 했어요`} disabled={item.pending} onClick={item.onCheckIn} className="rx-today-challenge-checkin">{item.pending ? '저장 중…' : '했어요'}</button>
          : <p className="rx-today-challenge-state text-muted-foreground" aria-live="polite">미달성</p>}
        {item.error && <p role="alert" className="text-center text-caption text-destructive">{item.error}</p>}
      </article>)}
    </div>
    {edges.left && <button type="button" aria-label="이전 챌린지" className="rx-today-challenge-arrow -left-3" onClick={() => move(-1)}><DrawnChevron direction="left" className="size-5" /></button>}
    {edges.right && <button type="button" aria-label="다음 챌린지" className="rx-today-challenge-arrow -right-3" onClick={() => move(1)}><DrawnChevron direction="right" className="size-5" /></button>}
  </div>;
}
