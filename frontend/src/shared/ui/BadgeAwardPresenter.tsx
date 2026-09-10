import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useSession } from '@/app/SessionContext';
import { badgeAwardRevision, captureBadgeAwardScope, dismissBadgeAward, nextBadgeAward, subscribeBadgeAwards, type BadgeAward } from '@/shared/lib/badgeAwards';
import { prepareBadgeArt } from '@/shared/lib/badgeArt';
import { Button } from './Button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from './dialog';
import './badge-award.css';

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return reduced;
}

function AwardDialog({ award, onClose }: { award: BadgeAward; onClose: () => void }) {
  const reduced = useReducedMotion();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<'loading' | 'tilt' | 'gloss' | 'ready' | 'error'>('loading');
  const [retry, setRetry] = useState(0);
  const badgeRef = useRef<HTMLDivElement>(null);
  const glossRef = useRef<HTMLSpanElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    let url: string | null = null;
    setImageUrl(null);
    setPhase('loading');
    prepareBadgeArt(award.imageUrl).then(async blob => {
      if (!active) return;
      url = URL.createObjectURL(blob);
      const image = new Image();
      image.src = url;
      await image.decode();
      if (active) setImageUrl(url);
    }).catch(() => { if (active) setPhase('error'); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [award.imageUrl, retry]);

  useEffect(() => {
    if (!imageUrl) return;
    if (reduced) { setPhase('ready'); return; }
    const badge = badgeRef.current;
    const gloss = glossRef.current;
    if (!badge || !gloss) return;
    let active = true;
    const animations: Animation[] = [];
    async function play() {
      setPhase('tilt');
      const entry = badge!.animate([
        { opacity: 0, transform: 'translateY(20px) rotateY(-110deg) scale(.8)' },
        { opacity: 1, transform: 'translateY(-3px) rotateY(12deg) scale(1.03)', offset: .68 },
        { opacity: 1, transform: 'translateY(0) rotateY(0deg) scale(1)' },
      ], { duration: 900, easing: 'cubic-bezier(.2,.8,.25,1)', fill: 'both' });
      animations.push(entry);
      await entry.finished;
      if (!active) return;
      setPhase('gloss');
      const sweep = gloss!.animate([
        { opacity: 0, transform: 'translateX(-130%) skewX(-18deg)' },
        { opacity: .85, offset: .2 },
        { opacity: .85, offset: .8 },
        { opacity: 0, transform: 'translateX(130%) skewX(-18deg)' },
      ], { duration: 450, easing: 'ease-out', fill: 'both' });
      animations.push(sweep);
      await sweep.finished;
      if (active) setPhase('ready');
    }
    void play().catch(() => { if (active) setPhase('ready'); });
    return () => { active = false; animations.forEach(animation => animation.cancel()); };
  }, [imageUrl, reduced]);

  const showCopy = reduced || phase === 'ready' || phase === 'error';
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent ref={contentRef} data-badge-award-dialog data-phase={phase} className="badge-award-dialog"
      onOpenAutoFocus={event => { event.preventDefault(); contentRef.current?.focus(); }} tabIndex={-1}>
      <div className="badge-award-stage" aria-busy={!imageUrl && phase !== 'error'}>
        {imageUrl ? <div ref={badgeRef} className="badge-award-art">
          <img src={imageUrl} alt={award.name} draggable={false} />
          {!reduced && <span className="badge-award-mask" style={{ maskImage: `url(${imageUrl})`, WebkitMaskImage: `url(${imageUrl})` }} aria-hidden="true"><span ref={glossRef} className="badge-award-gloss" /></span>}
        </div> : <p className="text-caption text-muted-foreground">{phase === 'error' ? '배지 이미지를 불러오지 못했어요.' : '배지를 준비하고 있어요…'}</p>}
      </div>
      <div className={showCopy ? 'badge-award-copy' : 'badge-award-copy badge-award-copy-pending'}>
        <DialogTitle className="text-center text-2xl font-bold">배지를 획득했어요!</DialogTitle>
        <DialogDescription className="mt-2 break-words text-center [overflow-wrap:anywhere]">{award.name}</DialogDescription>
      </div>
      {phase === 'error' && <div role="alert" className="text-center text-caption text-muted-foreground">
        <p>이미지를 다시 불러오거나 확인을 눌러 계속할 수 있어요.</p>
        <Button variant="secondary" onClick={() => setRetry(value => value + 1)} className="mt-3">이미지 다시 불러오기</Button>
      </div>}
      {showCopy ? <Button onClick={onClose}>확인</Button> : <div className="h-control" aria-hidden="true" />}
    </DialogContent>
  </Dialog>;
}

/** Mounted once under SessionProvider. Other open dialogs finish before this queue presents. */
export function BadgeAwardPresenter() {
  const { principalKey, authenticated } = useSession();
  useSyncExternalStore(subscribeBadgeAwards, badgeAwardRevision, badgeAwardRevision);
  const scope = captureBadgeAwardScope(authenticated ? principalKey : null);
  const award = nextBadgeAward(scope);
  const [otherDialogOpen, setOtherDialogOpen] = useState(false);
  useEffect(() => {
    const update = () => setOtherDialogOpen([...document.querySelectorAll('[role="dialog"], dialog[open]')]
      .some(element => !element.hasAttribute('data-badge-award-dialog') && element.getAttribute('data-state') !== 'closed' && element.getClientRects().length > 0));
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-state', 'open', 'hidden'] });
    update();
    return () => observer.disconnect();
  }, []);
  if (!award || otherDialogOpen || !scope) return null;
  return <AwardDialog key={JSON.stringify([scope.principalKey, scope.authGeneration, award.source, award.awardId, award.participationId])}
    award={award} onClose={() => dismissBadgeAward(scope, award)} />;
}
