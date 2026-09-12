import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { useSession } from '@/app/SessionContext';
import { getChallengeCatalog, getChallengeParticipations } from '@/entities/challenge';
import { getCustomChallengeRecommendations } from '@/entities/custom-challenge';
import { Button } from '@/shared/ui/Button';
import { LoadingState } from '@/shared/ui/LoadingState';
import { ChallengeAccordion } from './ChallengeAccordion';
import { ChallengePageHeading } from './ChallengePageHeading';
import { koreanChallengeDate } from './officialChallengeDates';
import { ChallengeTypeBadge } from './ChallengeTypeBadge';

interface BrowseEntry {
  key: string;
  name: string;
  type: 'official' | 'custom';
  recruitment: string;
  participating: boolean;
  destination: string;
}

export function OfficialChallengeBrowsePage() {
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const [official, setOfficial] = useState<BrowseEntry[] | null>(null);
  const [custom, setCustom] = useState<BrowseEntry[] | null>(null);
  const [officialError, setOfficialError] = useState<string | null>(null);
  const [customError, setCustomError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setOfficial(null);
    setCustom(null);
  }, [principalKey]);

  useEffect(() => {
    let active = true;
    setOfficialError(null);
    setCustomError(null);
    Promise.all([getChallengeCatalog(), getChallengeParticipations()])
      .then(([catalog, participations]) => {
        if (!active) return;
        const activeIds = new Set(participations.items.filter(item => item.status === 'ACTIVE').map(item => item.challenge_id));
        setOfficial(catalog.items.map(item => ({
          key: `official-${item.id}`,
          name: item.name,
          type: 'official',
          recruitment: `${koreanChallengeDate(item.recruit_start_at)} ~ ${koreanChallengeDate(item.recruit_end_at)}`,
          participating: activeIds.has(item.id),
          destination: !item.can_join && item.participation_id
            ? `/challenges/participations/${item.participation_id}`
            : `/challenges/official/${item.id}`,
        })));
      })
      .catch((reason: unknown) => {
        if (active) setOfficialError(reason instanceof Error ? reason.message : '공식 챌린지를 불러오지 못했어요.');
      });
    getCustomChallengeRecommendations()
      .then(result => {
        if (!active) return;
        setCustom(result.items.filter(item => item.challengeType === 'MEDICATION' || item.challengeType === 'SUPPLEMENT').map(item => ({
          key: `custom-${item.templateId}`,
          name: item.challengeName,
          type: 'custom',
          recruitment: '상시',
          participating: item.targets.length > 0
            && item.targets.every(target => target.existingParticipationId !== null),
          destination: `/challenges/tailored/${item.challengeType === 'MEDICATION' ? 'medication' : 'supplement'}?templateId=${item.templateId}`,
        })));
      })
      .catch((reason: unknown) => {
        if (active) setCustomError(reason instanceof Error ? reason.message : '맞춤 챌린지를 불러오지 못했어요.');
      });
    return () => { active = false; };
  }, [principalKey, reloadKey]);

  const groups = [
    { type: 'official', title: '공식 챌린지', items: official, error: officialError },
    { type: 'custom', title: '맞춤 챌린지', items: custom, error: customError },
  ];

  return (
    <>
      <ChallengePageHeading />
      <main className="flex flex-col gap-4 px-page-x py-5">
        <nav aria-label="챌린지 보기" className="grid h-11 grid-cols-2 rounded-input bg-muted-bg p-1">
          <Link to="/challenges" className="flex items-center justify-center rounded-[9px] text-sm font-medium text-muted-foreground">마이</Link>
          <Link aria-current="page" to="/challenges/browse" className="flex items-center justify-center rounded-[9px] bg-card text-sm font-bold text-primary shadow-card">둘러보기</Link>
        </nav>

        <section aria-label="챌린지 목록" className="flex flex-col gap-3">
          {groups.map(group => (
            <ChallengeAccordion key={`${principalKey}-${group.type}`} title={group.title} count={group.items?.length}>
              {group.items === null && !group.error ? <LoadingState label={`${group.title} 불러오는 중`}>{`${group.title}를 불러오고 있어요.`}</LoadingState> : null}
              {group.error ? (
                <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
                  <p className="text-sm text-muted-foreground">{group.error}</p>
                  <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
                </div>
              ) : null}
              {group.items?.length === 0 && !group.error ? (
                <div className="rounded-card bg-card p-5 text-sm text-muted-foreground shadow-card">지금 참여할 수 있는 {group.title}가 없어요.</div>
              ) : null}
              {[...(group.items ?? [])].sort((left, right) => Number(left.participating) - Number(right.participating)).map(item => (
                <button
                  key={item.key}
                  type="button"
                  disabled={item.participating}
                  aria-label={`${item.name} ${item.participating ? '참여중' : item.type === 'custom' ? '대상 선택' : '자세히 보기'}`}
                  onClick={() => navigate(item.destination)}
                  className="flex w-full items-center gap-3 rounded-card bg-card p-4 text-left shadow-card disabled:cursor-default disabled:bg-muted-bg disabled:text-disabled-foreground disabled:shadow-none"
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-base font-bold">
                      <span className="break-words [overflow-wrap:anywhere]">{item.name}</span>
                      {item.participating ? <span className="text-caption font-medium">참여중</span> : null}
                    </span>
                    <span className={`text-caption leading-5 ${item.participating ? 'text-disabled-foreground' : 'text-muted-foreground'}`}>모집기간 : {item.recruitment}</span>
                  </span>
                  <ChallengeTypeBadge official={item.type === 'official'} />
                  {!item.participating ? <DrawnChevron direction="right" className="size-5 shrink-0 text-primary" /> : null}
                </button>
              ))}
            </ChallengeAccordion>
          ))}
        </section>
      </main>
    </>
  );
}
