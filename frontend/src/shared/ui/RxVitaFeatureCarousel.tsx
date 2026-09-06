import { useEffect, useRef, useState } from 'react';
import { MessageCircle, ShoppingBag, Sprout } from 'lucide-react';

const BANNERS = [
  {
    title: '약봉투를 찍으면\n먹을 시간을 알려드려요',
    description: '약 이름을 몰라도 돼요. 사진 한 장으로 등록해요.',
    icon: ShoppingBag,
    tone: 'bg-primary-bg text-primary',
  },
  {
    title: '영양제 성분을\n한눈에 더해드려요',
    description: '등록한 제품끼리 성분 합계와 상한을 비교해요.',
    icon: Sprout,
    tone: 'bg-warning-bg text-warning',
  },
  {
    title: '내 약을 바탕으로\n차분하게 답해드려요',
    description: '확인할 수 있는 근거가 있을 때 함께 보여드려요.',
    icon: MessageCircle,
    tone: 'bg-muted-bg text-primary-strong',
  },
] as const;

interface RxVitaFeatureCarouselProps {
  autoAdvanceMs?: number;
  size?: 'full' | 'compact';
}

/** 비로그인 홈과 기다림 화면이 함께 쓰는 RxVita 기능 소개 배너. */
export function RxVitaFeatureCarousel({
  autoAdvanceMs,
  size = 'full',
}: RxVitaFeatureCarouselProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [activeBannerIndex, setActiveBannerIndex] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [documentHidden, setDocumentHidden] = useState(false);
  const isCompact = size === 'compact';

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncPreference = () => setReducedMotion(query.matches);
    syncPreference();
    query.addEventListener('change', syncPreference);
    return () => query.removeEventListener('change', syncPreference);
  }, []);

  useEffect(() => {
    const syncVisibility = () => setDocumentHidden(document.hidden);
    syncVisibility();
    document.addEventListener('visibilitychange', syncVisibility);
    return () => document.removeEventListener('visibilitychange', syncVisibility);
  }, []);

  useEffect(() => {
    if (!autoAdvanceMs || reducedMotion || documentHidden) {
      return;
    }
    const intervalId = window.setInterval(() => {
      const scroller = scrollerRef.current;
      if (!scroller) return;
      const children = Array.from(scroller.children) as HTMLElement[];
      const nextIndex =
        activeBannerIndex === BANNERS.length - 1 ? BANNERS.length : activeBannerIndex + 1;
      const firstOffset = children[0]?.offsetLeft ?? 0;
      const nextBanner = children[nextIndex];
      if (!nextBanner) return;
      scroller.scrollTo({ left: nextBanner.offsetLeft - firstOffset, behavior: 'smooth' });
    }, autoAdvanceMs);
    return () => window.clearInterval(intervalId);
  }, [
    activeBannerIndex,
    autoAdvanceMs,
    documentHidden,
    reducedMotion,
  ]);

  return (
    <section
      aria-label="RxVita 기능 소개"
      className={`flex flex-col ${isCompact ? 'min-h-42 gap-2' : 'min-h-84 gap-3'}`}
    >
      <div
        ref={scrollerRef}
        className="-mr-page-x flex flex-1 snap-x snap-mandatory gap-3 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        onScroll={(event) => {
          const children = Array.from(event.currentTarget.children) as HTMLElement[];
          const firstOffset = children[0]?.offsetLeft ?? 0;
          const nextIndex = children.reduce((closestIndex, child, index) => {
            const closestDistance = Math.abs(
              children[closestIndex].offsetLeft - firstOffset - event.currentTarget.scrollLeft,
            );
            const childDistance = Math.abs(
              child.offsetLeft - firstOffset - event.currentTarget.scrollLeft,
            );
            return childDistance < closestDistance ? index : closestIndex;
          }, 0);
          setActiveBannerIndex(nextIndex % BANNERS.length);
        }}
        onScrollEnd={(event) => {
          const children = Array.from(event.currentTarget.children) as HTMLElement[];
          const firstOffset = children[0]?.offsetLeft ?? 0;
          const closestIndex = children.reduce((closest, child, index) => {
            const closestDistance = Math.abs(
              children[closest].offsetLeft - firstOffset - event.currentTarget.scrollLeft,
            );
            const childDistance = Math.abs(
              child.offsetLeft - firstOffset - event.currentTarget.scrollLeft,
            );
            return childDistance < closestDistance ? index : closest;
          }, 0);
          if (closestIndex === BANNERS.length) {
            event.currentTarget.scrollTo({
              left: children[0].offsetLeft - firstOffset,
              behavior: 'auto',
            });
          }
        }}
      >
        {[...BANNERS, BANNERS[0]].map(({ title, description, icon: Icon, tone }, index) => (
          <article
            aria-hidden={index === BANNERS.length || undefined}
            key={`${title}-${index}`}
            className={`flex min-w-[88%] flex-1 snap-start rounded-card shadow-card ${tone} ${
              isCompact
                ? 'min-h-32 flex-row items-center gap-4 p-4'
                : 'min-h-64 flex-col p-5'
            }`}
          >
            <span
              className={`flex shrink-0 items-center justify-center rounded-pill bg-card/80 ${
                isCompact ? 'size-10' : 'size-12'
              }`}
            >
              <Icon aria-hidden className={isCompact ? 'size-5' : 'size-6'} />
            </span>
            <div className={isCompact ? 'min-w-0 flex-1' : 'flex flex-1 flex-col'}>
              <h2
                className={
                  isCompact
                    ? 'line-clamp-2 text-lg font-bold text-foreground'
                    : 'mt-6 whitespace-pre-line text-2xl font-bold text-foreground'
                }
              >
                {isCompact ? title.replace('\n', ' ') : title}
              </h2>
              <p
                className={
                  isCompact
                    ? 'mt-1 line-clamp-1 text-sm text-muted-foreground'
                    : 'mt-auto text-base text-muted-foreground'
                }
              >
                {description}
              </p>
            </div>
          </article>
        ))}
      </div>
      <div
        aria-label={`현재 배너 ${activeBannerIndex + 1} / ${BANNERS.length}`}
        className="flex justify-center gap-2"
      >
        {BANNERS.map((banner, index) => (
          <span
            aria-hidden
            key={banner.title}
            className={
              index === activeBannerIndex
                ? 'h-1.5 w-5 rounded-pill bg-primary'
                : 'size-1.5 rounded-pill bg-border'
            }
          />
        ))}
      </div>
    </section>
  );
}
