import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { getChallengeParticipations, type ChallengeParticipation } from '@/entities/challenge';
import { getCustomChallengeParticipations, customChallengeDayProgress, subscribeCustomChallengeProgressInvalidation, type CustomChallengeParticipation } from '@/entities/custom-challenge';
import { useChallengeMock } from '@/features/challenges';
import { getAuthGeneration } from '@/shared/api/client';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { Button } from '@/shared/ui/Button';
import { TodayChallengeCarousel, type TodayChallengeCard } from './TodayChallengeCarousel';
import '@/shared/ui/home-clay.css';

const koreaDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' });
const loadOfficial = () => getChallengeParticipations().then(result => result.items);
const loadCustom = () => getCustomChallengeParticipations().then(result => result.items);
function rate(value: number | string, target: number) {
  const parsed = Number(value);
  return target > 0 && Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 0;
}

/** Keep the last successful list while refreshing; the parent key isolates accounts. */
function useSummaryList<T>(load: () => Promise<T[]>, principal: string | null, fallback: string) {
  const [items, setItems] = useState<T[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const requestGeneration = ++generation.current;
    const auth = getAuthGeneration();
    let active = true;
    const current = () => active && generation.current === requestGeneration && auth === getAuthGeneration();
    setError(null);
    load().then(result => { if (current()) setItems(result); })
      .catch((reason: unknown) => { if (current()) setError(reason instanceof Error ? reason.message : fallback); });
    return () => { active = false; };
  }, [load, principal, fallback, reloadKey]);
  return { items, error, reload: () => setReloadKey(key => key + 1) };
}

export function HomeChallengeSummary({ empty = false }: { empty?: boolean }) {
  const location = useLocation();
  const { principalKey } = useSession();
  return location.pathname.startsWith('/dev/')
    ? <MockHomeChallengeSummary empty={empty} />
    : <OfficialHomeChallengeSummary key={principalKey ?? 'guest'} principal={principalKey} />;
}

function SummaryFrame({ children, base = '/challenges', mock = false }: { children: ReactNode; base?: string; mock?: boolean }) {
  return <section aria-labelledby="home-challenge-title" className="rx-home-challenges flex min-w-0 flex-col gap-3">
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h2 id="home-challenge-title" className="text-lg font-bold text-foreground">챌린지</h2>
        {mock && <span className="rounded-pill bg-muted-bg px-2 py-1 text-micro text-muted-foreground">예시 데이터</span>}
      </div>
      <Link to={base} className="min-h-touch py-3 text-caption font-bold text-primary">전체 보기</Link>
    </div>
    <div className="rx-challenge-card min-w-0 rounded-card bg-card p-4 shadow-card">{children}</div>
  </section>;
}

function MockHomeChallengeSummary({ empty }: { empty: boolean }) {
  const { participations, medicationEpisodes, badges, demoToday } = useChallengeMock();
  const items: TodayChallengeCard[] = (empty ? [] : participations).filter(item =>
    item.status === 'active' && !item.todayCompleted && item.startDate <= demoToday && item.endDate >= demoToday
    && (item.kind !== 'medication' || medicationEpisodes.some(episode => episode.id === item.episodeId)),
  ).map(item => {
    const badge = badges.find(b => b.id === item.badgeId);
    return { id: item.id, title: item.title, href: '/dev/challenges/participations/' + item.id, official: item.kind === 'official',
      image: badge?.imageUrl ?? '/images/challenges/badge-medication.png', badgeName: badge?.name ?? '챌린지 배지',
      progress: item.percent + '% 진행 중', rate: rate(item.percent, item.target) };
  });
  return <SummaryFrame base="/dev/challenges" mock>{items.length ? <TodayChallengeCarousel items={items} /> : <p className="py-4 text-sm text-muted-foreground">오늘 남은 챌린지가 없어요</p>}</SummaryFrame>;
}

function OfficialHomeChallengeSummary({ principal }: { principal: string | null }) {
  const official = useSummaryList<ChallengeParticipation>(loadOfficial, principal, '공식 챌린지를 불러오지 못했어요.');
  const custom = useSummaryList<CustomChallengeParticipation>(loadCustom, principal, '맞춤 챌린지를 불러오지 못했어요.');
  const [today, setToday] = useState(() => koreaDate.format(new Date()));
  const reloadCustom = useRef(custom.reload);
  const reloadOfficial = useRef(official.reload);
  const dateRef = useRef(today);
  reloadCustom.current = custom.reload;
  reloadOfficial.current = official.reload;
  useEffect(() => subscribeCustomChallengeProgressInvalidation(() => reloadCustom.current()), []);
  useEffect(() => {
    const update = () => {
      const next = koreaDate.format(new Date());
      if (next === dateRef.current) return;
      dateRef.current = next;
      setToday(next);
      reloadOfficial.current();
      reloadCustom.current();
    };
    const timer = window.setInterval(update, 60_000);
    document.addEventListener('visibilitychange', update);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, []);

  const officialCards: TodayChallengeCard[] = (official.items ?? []).filter(item =>
    item.status === 'ACTIVE' && item.can_verify && !item.verified_dates.includes(today)
    && item.started_at.slice(0, 10) <= today && Date.parse(item.end_at) > Date.now(),
  ).map(item => ({ id: 'official-' + item.id, title: item.challenge_name, href: '/challenges/participations/' + item.id, official: true,
    image: item.challenge.reward_badge?.image_path ? apiAssetUrl(item.challenge.reward_badge.image_path) : '/images/challenges/badge-walk.png',
    badgeName: item.challenge.reward_badge?.name ?? '공식 챌린지 배지',
    progress: rate(item.progress_rate, item.target_count) + '% 진행 중', rate: rate(item.progress_rate, item.target_count) }));
  const customCards: TodayChallengeCard[] = (custom.items ?? []).filter(item =>
    item.status === 'ACTIVE' && item.occurrences.some(occurrence => occurrence.scheduledDate === today && !occurrence.isCompleted),
  ).map(item => {
    const days = customChallengeDayProgress(item);
    const fallback = item.challengeType === 'SUPPLEMENT' ? 'supplement' : item.challengeType === 'VISIT' ? 'review' : 'medication';
    return { id: 'custom-' + item.id, title: item.challengeName, href: '/challenges/custom-participations/' + item.id, official: false,
      image: item.rewardBadge?.imagePath ? apiAssetUrl(item.rewardBadge.imagePath) : '/images/challenges/badge-' + fallback + '.png', badgeName: item.rewardBadge?.name ?? '맞춤 챌린지 배지',
      progress: days.completed + ' / ' + days.target + '일', rate: rate(days.rate, days.target) };
  });
  const items = [...officialCards, ...customCards];
  const loading = (official.items === null && !official.error) || (custom.items === null && !custom.error);
  return <SummaryFrame>
    {items.length > 0 && <TodayChallengeCarousel items={items} />}
    {loading && items.length === 0 && <div role="status" aria-label="오늘 챌린지 불러오는 중" className="flex min-h-[222px] items-center justify-center gap-2 text-caption text-muted-foreground"><span aria-hidden className="size-4 rounded-full border-2 border-primary-bg border-t-primary motion-safe:animate-spin" />오늘 챌린지를 확인하고 있어요</div>}
    {!loading && !official.error && !custom.error && items.length === 0 && <p className="py-4 text-sm text-muted-foreground">오늘 남은 챌린지가 없어요</p>}
    {([['공식 챌린지', official], ['맞춤 챌린지', custom]] as const).map(([label, state]) => state.error && <section key={label} aria-label={label} className="flex flex-col gap-2 py-2">
      <p role="alert" className="text-sm text-muted-foreground">{state.error}</p>
      <Button variant="secondary" className="h-11 min-h-11" onClick={state.reload}>다시 불러오기</Button>
    </section>)}
  </SummaryFrame>;
}
