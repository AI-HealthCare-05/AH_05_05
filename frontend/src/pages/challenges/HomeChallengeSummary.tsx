import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { getChallengeParticipations, type ChallengeParticipation } from '@/entities/challenge';
import {
  getCustomChallengeParticipations,
  subscribeCustomChallengeProgressInvalidation,
  type CustomChallengeParticipation,
} from '@/entities/custom-challenge';
import { useChallengeMock } from '@/features/challenges';
import { getAuthGeneration } from '@/shared/api/client';
import { Button } from '@/shared/ui/Button';
import { inclusiveChallengeEndDate } from './officialChallengeDates';

function compactDate(value: string) {
  const [, month, day] = value.split('-');
  return `${Number(month)}.${Number(day)}`;
}

function ChallengeRowTitle({ title, official }: { title: string; official: boolean }) {
  return (
    <span className="flex items-start gap-2 text-xs font-bold text-foreground">
      <span className="min-w-0 [overflow-wrap:anywhere]">{title}</span>
      <span className="shrink-0 rounded-pill bg-primary-bg px-2 py-0.5 text-micro text-primary">
        {official ? '공식' : '맞춤'}
      </span>
      <span aria-hidden className="ml-auto shrink-0 text-base leading-none text-tertiary-foreground">›</span>
    </span>
  );
}

export function HomeChallengeSummary({ empty = false }: { empty?: boolean }) {
  const location = useLocation();
  return location.pathname.startsWith('/dev/')
    ? <MockHomeChallengeSummary empty={empty} />
    : <OfficialHomeChallengeSummary />;
}

function MockHomeChallengeSummary({ empty = false }: { empty?: boolean }) {
  const { participations, medicationEpisodes } = useChallengeMock();
  const location = useLocation();
  const base = location.pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const allActive = empty ? [] : participations.filter((item) => item.status === 'active');
  const medication = empty ? [] : participations.filter((item) =>
    item.kind === 'medication' && medicationEpisodes.some((episode) => episode.id === item.episodeId),
  );
  const active = allActive.filter((item) =>
    item.kind !== 'medication' || medicationEpisodes.some((episode) => episode.id === item.episodeId),
  );

  return (
    <section aria-labelledby="home-challenge-title" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 id="home-challenge-title" className="text-lg font-bold text-foreground">
            챌린지
          </h2>
          <span className="rounded-pill bg-muted-bg px-2 py-1 text-micro text-muted-foreground">
            예시 데이터
          </span>
        </div>
        <Link to={base} className="min-h-touch py-3 text-caption font-bold text-primary">
          전체 보기
        </Link>
      </div>
      <div className="flex flex-col gap-3 rounded-card bg-card px-4 py-3 shadow-card">
        {medication.length ? (
          <div className="space-y-1 border-b border-border pb-3">
            <h3 className="text-sm font-bold">복약 챌린지 · 처방별 진행</h3>
            <p className="text-xs text-muted-foreground">진행 중 {medication.filter((item) => item.status === 'active').length}개 · 달성 {medication.filter((item) => item.status === 'achieved').length}개</p>
          </div>
        ) : null}
        {active.length === 0 ? (
          <>
            <p className="text-sm font-bold text-foreground">참여 중인 챌린지가 없어요</p>
            <Link
              to={`${base}/tailored`}
              className="flex min-h-touch items-center justify-center rounded-input bg-primary-bg text-sm font-bold text-primary"
            >
              맞춤 챌린지 보기 ›
            </Link>
          </>
        ) : (
          active.map((participation) => {
            const title =
              participation.kind === 'supplement'
                ? `${participation.title} 챌린지`
                : participation.title;
            return <Link
              key={participation.id}
              to={`${base}/participations/${participation.id}`}
              aria-label={`${title}, ${participation.percent}% 달성, 상세 보기`}
              className="group flex min-h-12 flex-col gap-1"
            >
              <ChallengeRowTitle title={title} official={participation.kind === 'official'} />
              <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="tnum">
                  {compactDate(participation.startDate)} ~ {compactDate(participation.endDate)}
                </span>
                <span>{participation.percent}% {participation.status === 'achieved' ? '달성 · 배지 획득' : '달성했어요'}</span>
              </span>
              <span className="h-2 overflow-hidden rounded-pill bg-border" aria-hidden>
                <span
                  className="block h-full rounded-pill bg-primary"
                  style={{ width: `${Math.max(0, Math.min(100, participation.percent))}%` }}
                />
              </span>
            </Link>;
          })
        )}
      </div>
    </section>
  );
}

function progressValue(value: number | string, targetCount?: number) {
  if (targetCount !== undefined && targetCount <= 0) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 0;
}

function progressLabel(value: number | string, targetCount?: number) {
  return String(progressValue(value, targetCount));
}

function OfficialHomeChallengeSummary() {
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const officialRequestGenerationRef = useRef(0);
  const customRequestGenerationRef = useRef(0);
  const [officialParticipations, setOfficialParticipations] = useState<
    ChallengeParticipation[] | null
  >(null);
  const [customParticipations, setCustomParticipations] = useState<
    CustomChallengeParticipation[] | null
  >(null);
  const [officialError, setOfficialError] = useState<string | null>(null);
  const [customError, setCustomError] = useState<string | null>(null);
  const [officialReloadKey, setOfficialReloadKey] = useState(0);
  const [customReloadKey, setCustomReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    const requestGeneration = officialRequestGenerationRef.current + 1;
    officialRequestGenerationRef.current = requestGeneration;
    const requestPrincipal = principalKey;
    const authGeneration = getAuthGeneration();
    let mounted = true;
    const isCurrentRequest = () => (
      mounted
      && officialRequestGenerationRef.current === requestGeneration
      && principalRef.current === requestPrincipal
      && getAuthGeneration() === authGeneration
    );
    setOfficialParticipations(null);
    setOfficialError(null);
    getChallengeParticipations()
      .then(result => {
        if (isCurrentRequest()) setOfficialParticipations(result.items);
      })
      .catch((reason: unknown) => {
        if (isCurrentRequest()) {
          setOfficialError(
            reason instanceof Error ? reason.message : '공식 챌린지를 불러오지 못했어요.',
          );
        }
      });
    return () => {
      mounted = false;
      if (officialRequestGenerationRef.current === requestGeneration) {
        officialRequestGenerationRef.current += 1;
      }
    };
  }, [officialReloadKey, principalKey]);

  useEffect(() => {
    const requestGeneration = customRequestGenerationRef.current + 1;
    customRequestGenerationRef.current = requestGeneration;
    const requestPrincipal = principalKey;
    const authGeneration = getAuthGeneration();
    let mounted = true;
    const isCurrentRequest = () => (
      mounted
      && customRequestGenerationRef.current === requestGeneration
      && principalRef.current === requestPrincipal
      && getAuthGeneration() === authGeneration
    );
    setCustomParticipations(null);
    setCustomError(null);
    getCustomChallengeParticipations()
      .then(result => {
        if (isCurrentRequest()) setCustomParticipations(result.items);
      })
      .catch((reason: unknown) => {
        if (isCurrentRequest()) {
          setCustomError(
            reason instanceof Error ? reason.message : '맞춤 챌린지를 불러오지 못했어요.',
          );
        }
      });
    return () => {
      mounted = false;
      if (customRequestGenerationRef.current === requestGeneration) {
        customRequestGenerationRef.current += 1;
      }
    };
  }, [customReloadKey, principalKey]);

  useEffect(
    () => subscribeCustomChallengeProgressInvalidation(
      () => setCustomReloadKey(key => key + 1),
    ),
    [],
  );

  const officialActive = officialParticipations?.filter(item => item.status === 'ACTIVE') ?? [];
  const customActive = customParticipations?.filter(item => item.status === 'ACTIVE') ?? [];
  const bothLoadedEmpty = (
    officialParticipations !== null
    && customParticipations !== null
    && !officialError
    && !customError
    && officialActive.length === 0
    && customActive.length === 0
  );
  const showOfficialSection = (
    officialParticipations === null
    || officialError !== null
    || officialActive.length > 0
  );
  const showCustomSection = (
    customParticipations === null
    || customError !== null
    || customActive.length > 0
  );

  return (
    <section aria-labelledby="home-challenge-title" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="home-challenge-title" className="text-lg font-bold text-foreground">챌린지</h2>
        <Link to="/challenges" className="min-h-touch py-3 text-caption font-bold text-primary">전체 보기</Link>
      </div>
      <div className="flex min-h-[132px] flex-col justify-center gap-3 rounded-card bg-card px-4 py-3 shadow-card">
        {bothLoadedEmpty ? (
          <><p className="text-sm font-bold text-foreground">참여 중인 챌린지가 없어요</p><Link to="/challenges/browse" className="flex min-h-touch items-center justify-center rounded-input bg-primary-bg text-sm font-bold text-primary">공식 챌린지 둘러보기 ›</Link></>
        ) : null}
        {!bothLoadedEmpty && showOfficialSection ? (
          <section role="region" aria-label="공식 챌린지" className="flex flex-col gap-3">
            {officialParticipations === null && !officialError ? (
              <div
                role="status"
                aria-label="공식 챌린지 요약 불러오는 중"
                className="min-h-20 animate-pulse rounded-input bg-muted-bg"
              />
            ) : null}
            {officialError ? (
              <div role="alert" className="flex flex-col gap-2">
                <p className="text-sm text-muted-foreground">{officialError}</p>
                <Button
                  variant="secondary"
                  className="h-11 min-h-11"
                  onClick={() => setOfficialReloadKey(key => key + 1)}
                >
                  다시 불러오기
                </Button>
              </div>
            ) : null}
            {officialActive.length > 0 ? (
              <>
                <h3 className="text-sm font-bold text-foreground">
                  공식 챌린지 · 진행 중 {officialActive.length}개
                </h3>
                {officialActive.map(item => {
                  const rate = progressLabel(item.progress_rate, item.target_count);
                  const endDate = inclusiveChallengeEndDate(item.end_at);
                  return (
                    <Link
                      key={item.id}
                      to={`/challenges/participations/${item.id}`}
                      aria-label={`${item.challenge_name}, ${rate}% 진행, 상세 보기`}
                      className="group flex min-h-12 min-w-0 flex-col gap-1"
                    >
                      <ChallengeRowTitle title={item.challenge_name} official />
                      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <span className="tnum">
                          {compactDate(item.started_at.slice(0, 10))} ~ {compactDate(endDate)}
                        </span>
                        <span>{rate}% 진행 중</span>
                      </span>
                      <span className="h-2 overflow-hidden rounded-pill bg-border" aria-hidden>
                        <span
                          className="block h-full rounded-pill bg-primary"
                          style={{ width: `${progressValue(item.progress_rate, item.target_count)}%` }}
                        />
                      </span>
                    </Link>
                  );
                })}
              </>
            ) : null}
          </section>
        ) : null}
        {!bothLoadedEmpty && showCustomSection ? (
          <section role="region" aria-label="맞춤 챌린지" className="flex flex-col gap-3">
            {customParticipations === null && !customError ? (
              <div
                role="status"
                aria-label="맞춤 챌린지 요약 불러오는 중"
                className="min-h-20 animate-pulse rounded-input bg-muted-bg"
              />
            ) : null}
            {customError ? (
              <div role="alert" className="flex flex-col gap-2">
                <p className="text-sm text-muted-foreground">{customError}</p>
                <Button
                  variant="secondary"
                  className="h-11 min-h-11"
                  onClick={() => setCustomReloadKey(key => key + 1)}
                >
                  다시 불러오기
                </Button>
              </div>
            ) : null}
            {customActive.length > 0 ? (
              <>
                <h3 className="text-sm font-bold text-foreground">
                  맞춤 챌린지 · 진행 중 {customActive.length}개
                </h3>
                {customActive.map(item => {
                  const rate = progressValue(item.progressRate, item.targetCount);
                  const progressText = item.targetCount <= 0
                    ? '예정된 목표 없음'
                    : `${rate}% 진행 중`;
                  return (
                    <Link
                      key={item.id}
                      to={`/challenges/custom-participations/${item.id}`}
                      aria-label={`${item.challengeName}, ${progressText}, 상세 보기`}
                      className="group flex min-h-12 min-w-0 flex-col gap-1"
                    >
                      <ChallengeRowTitle title={item.challengeName} official={false} />
                      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <span>{item.completedCount} / {item.targetCount}회</span>
                        <span>{progressText}</span>
                      </span>
                      <span
                        role="progressbar"
                        aria-label={`${item.challengeName} 진행률`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={rate}
                        className="h-2 overflow-hidden rounded-pill bg-border"
                      >
                        <span
                          className="block h-full rounded-pill bg-primary"
                          style={{ width: `${rate}%` }}
                        />
                      </span>
                    </Link>
                  );
                })}
              </>
            ) : null}
          </section>
        ) : null}
      </div>
    </section>
  );
}
