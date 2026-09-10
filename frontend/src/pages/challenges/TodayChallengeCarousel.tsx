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
      {items.map(item => <Link key={item.id} to={item.href} aria-label={`${item.title}, ${item.progress}, 상세 보기`} className="rx-today-challenge-item">
        <span className="self-start rounded-pill bg-primary-bg px-2 py-0.5 text-micro font-bold text-primary">{item.official ? '공식' : '맞춤'}</span>
        <img src={item.image} alt={item.badgeName} width={64} height={64} className="size-16 self-center rounded-pill object-contain" />
        <span className="rx-challenge-title text-center text-sm font-bold [overflow-wrap:anywhere]">{item.title}</span>
        <span className="mt-auto text-center text-caption text-muted-foreground">{item.progress}</span>
        <span role="progressbar" aria-label={`${item.title} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.rate} className="rx-challenge-track h-1 w-full overflow-hidden rounded-pill bg-border">
          <span className="block h-full rounded-pill bg-primary" style={{ width: `${item.rate}%` }} />
        </span>
      </Link>)}
    </div>
    {edges.left && <button type="button" aria-label="이전 챌린지" className="rx-today-challenge-arrow -left-3" onClick={() => move(-1)}><DrawnChevron direction="left" className="size-5" /></button>}
    {edges.right && <button type="button" aria-label="다음 챌린지" className="rx-today-challenge-arrow -right-3" onClick={() => move(1)}><DrawnChevron direction="right" className="size-5" /></button>}
  </div>;
}
