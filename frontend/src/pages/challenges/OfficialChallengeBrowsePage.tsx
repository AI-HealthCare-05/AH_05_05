import { ArrowRight } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getChallengeCatalog,
  type ChallengeCatalogItem,
} from '@/entities/challenge';
import { Button } from '@/shared/ui/Button';
import { ChallengePageHeading } from './ChallengePageHeading';

function shortDate(value: string) {
  const date = value.slice(0, 10);
  const [, month, day] = date.split('-');
  return `${month}.${day}`;
}

export function officialFrequencyLabel(item: ChallengeCatalogItem): string {
  const prefix = `참여일부터 ${item.duration_days}일`;
  if (item.frequency_code === 'DAILY') return `${prefix} · 매일 인증`;
  if (item.frequency_code === 'WEEKLY_3') return `${prefix} · 주 3회 인증`;
  if (item.frequency_code === 'TOTAL_10') return `${prefix} · 기간 동안 총 10회 인증`;
  return `${prefix} · 인증 주기는 상세 안내에서 확인`;
}

export function OfficialChallengeBrowsePage() {
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const [items, setItems] = useState<ChallengeCatalogItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setItems(null);
    setError(null);
    getChallengeCatalog()
      .then(result => {
        if (active) setItems(result.items);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '챌린지를 불러오지 못했어요.');
      });
    return () => {
      active = false;
    };
  }, [principalKey, reloadKey]);

  return (
    <>
      <ChallengePageHeading />
      <main className="flex flex-col gap-4 px-page-x py-5">
      <nav aria-label="챌린지 보기" className="grid h-11 grid-cols-2 rounded-input bg-muted-bg p-1">
        <Link to="/challenges" className="flex items-center justify-center rounded-[9px] text-sm font-medium text-muted-foreground">마이</Link>
        <Link aria-current="page" to="/challenges/browse" className="flex items-center justify-center rounded-[9px] bg-card text-sm font-bold text-primary shadow-card">둘러보기</Link>
      </nav>

      <Link to="/challenges/tailored" className="flex min-h-12 items-center justify-between rounded-button border border-primary bg-card px-4 text-sm font-bold text-primary">
        <span>맞춤 챌린지 · 내 기록으로 보기</span>
        <ArrowRight aria-hidden className="size-5" />
      </Link>

      <section aria-labelledby="official-challenges-title" className="flex flex-col gap-3">
        <h2 id="official-challenges-title" className="text-lg font-bold">공식 챌린지</h2>
        {items === null && !error ? (
          <div role="status" aria-label="공식 챌린지 불러오는 중" className="min-h-40 animate-pulse rounded-card bg-muted-bg" />
        ) : null}
        {error ? (
          <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
          </div>
        ) : null}
        {items?.length === 0 ? (
          <div className="rounded-card bg-card p-5 text-sm text-muted-foreground shadow-card">지금 참여할 수 있는 공식 챌린지가 없어요.</div>
        ) : null}
        {items?.map(item => (
          <button
            key={item.id}
            type="button"
            aria-label={`${item.name} 자세히 보기`}
            onClick={() => navigate(!item.can_join && item.participation_id
              ? `/challenges/participations/${item.participation_id}`
              : `/challenges/official/${item.id}`)}
            className="flex w-full flex-col gap-2 rounded-card bg-card p-5 text-left shadow-card"
          >
            <span className="text-base font-bold text-foreground">{item.name}</span>
            <span className="text-sm text-primary">{item.phrase}</span>
            <span className="text-caption text-muted-foreground">{officialFrequencyLabel(item)}</span>
            <span className="text-caption text-muted-foreground">공식 · 모집 {shortDate(item.recruit_start_at)} ~ {shortDate(item.recruit_end_at)}</span>
            <span className="text-caption font-bold text-primary">{item.can_join && item.participation_id ? '다시 참여하기 ›' : item.participation_id ? '참여 기록 보기 ›' : '자세히 보기 ›'}</span>
          </button>
        ))}
      </section>
      </main>
    </>
  );
}
