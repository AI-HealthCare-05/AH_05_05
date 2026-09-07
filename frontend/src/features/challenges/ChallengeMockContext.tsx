import { createContext, useContext, useRef, useState, type ReactNode } from 'react';

import {
  CHALLENGE_DEMO_TODAY,
  initialChallengeBadges,
  initialChallengeDefinitions,
  initialChallengeParticipations,
  initialMedicationEpisodes,
} from './mockData';
import type {
  ChallengeDefinition,
  ChallengeMockValue,
  ChallengeParticipation,
  PersonalChallengeInput,
} from './types';

const ChallengeMockContext = createContext<ChallengeMockValue | null>(null);

const copyDefinitions = () => initialChallengeDefinitions.map((definition) => ({ ...definition }));
const copyBadges = () => initialChallengeBadges.map((badge) => ({ ...badge }));
const copyParticipations = () =>
  initialChallengeParticipations.map((participation) => ({
    ...participation,
    checkInDates: [...participation.checkInDates],
    checklist: participation.checklist?.map((item) => ({ ...item })),
  }));

function addDays(dateText: string, days: number): string {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function targetFor(definition: ChallengeDefinition): number {
  return definition.frequency.type === 'daily'
    ? definition.frequency.durationDays
    : definition.frequency.targetDaysPerWeek * definition.frequency.durationWeeks;
}

function durationFor(definition: ChallengeDefinition): number {
  return definition.frequency.type === 'daily'
    ? definition.frequency.durationDays
    : definition.frequency.durationWeeks * 7;
}

export function ChallengeMockProvider({ children }: { children: ReactNode }) {
  const [medicationEpisodes, setMedicationEpisodes] = useState(() =>
    initialMedicationEpisodes.map((episode) => ({ ...episode })),
  );
  const [definitions, setDefinitions] = useState(copyDefinitions);
  const [participations, setParticipations] = useState<ChallengeParticipation[]>(copyParticipations);
  const [badges, setBadges] = useState(copyBadges);
  const sequence = useRef(1);

  // Preview-only: one fixed-date dinner record per care episode. Repeated writes are idempotent.
  function setMedicationDose(recordIds: number[], taken: boolean) {
    setMedicationEpisodes((current) => current.map((episode) => {
      if (!recordIds.includes(episode.recordId) || episode.todayTaken === taken) return episode;
      // Badge revocation is not an agreed policy. The demo leaves achieved records intact.
      if (!taken && episode.completed >= episode.target && participations.some((item) => item.episodeId === episode.id)) return episode;
      return { ...episode, todayTaken: taken, completed: episode.completed + (taken ? 1 : -1) };
    }));
  }

  const visibleParticipations = participations.map((participation) => {
    if (participation.kind !== 'medication') return participation;
    const episode = medicationEpisodes.find((item) => item.id === participation.episodeId);
    if (!episode) return participation; // Completed historical participation snapshot.
    const { target, completed } = episode;
    return {
      ...participation,
      target,
      completed,
      percent: target ? Math.round(completed / target * 100) : 0,
      targetSummary: episode.label,
      todayCompleted: episode.todayTaken,
      status: target > 0 && completed === target ? 'achieved' as const : 'active' as const,
    };
  });

  // One award per participation, not one badge definition per prescription.
  const visibleBadges = badges.map((badge) => {
    if (badge.id !== 'badge-pill') return badge;
    const awards = visibleParticipations
      .filter((item) => item.kind === 'medication' && item.badgeId === badge.id && item.status === 'achieved' && item.episodeId)
      .map((item) => ({
        participationId: item.id,
        episodeId: item.episodeId!,
        title: item.title,
        earnedAt: item.id === 'part-medication-previous' ? item.endDate : CHALLENGE_DEMO_TODAY,
      }))
      .sort((a, b) => b.earnedAt.localeCompare(a.earnedAt));
    return { ...badge, awards, earnedAt: awards[0]?.earnedAt };
  });

  function joinChallenge(
    challengeId: string,
    selection?: { targetIds: string[]; targetSummary: string },
  ): string {
    if (challengeId === 'medication-routine') {
      const selected = medicationEpisodes.filter((episode) => selection?.targetIds.includes(episode.id));
      if (!selected.length) throw new Error('참여할 처방을 선택해주세요.');
      const entries = selected.map((episode): ChallengeParticipation => {
        const existing = participations.find((item) => item.challengeId === challengeId && item.episodeId === episode.id);
        return existing ?? {
          id: `part-medication-${episode.id}`,
          episodeId: episode.id,
          challengeId,
          title: `${episode.label} 복약 챌린지`,
          targetSummary: episode.label,
          kind: 'medication',
          startDate: episode.startDate,
          endDate: episode.endDate,
          status: 'active',
          completed: episode.completed,
          target: episode.target,
          percent: Math.round(episode.completed / episode.target * 100),
          todayCompleted: episode.todayTaken,
          checkInDates: [],
          badgeId: 'badge-pill',
        };
      });
      setParticipations((current) => [
        ...current,
        ...entries.filter((entry) => !current.some((item) => item.challengeId === challengeId && item.episodeId === entry.episodeId)),
      ]);
      return entries[0].id;
    }
    const existing = participations.find((item) => item.challengeId === challengeId);
    if (existing) {
      if (selection) {
        setParticipations((current) => current.map((item) =>
          item.id === existing.id
            ? { ...item, targetIds: [...selection.targetIds], targetSummary: selection.targetSummary }
            : item,
        ));
      }
      return existing.id;
    }
    const definition = definitions.find((item) => item.id === challengeId);
    if (!definition) throw new Error(`알 수 없는 챌린지예요: ${challengeId}`);
    if (definition.enrollmentEnd && definition.enrollmentEnd < CHALLENGE_DEMO_TODAY) {
      throw new Error('모집이 끝난 챌린지예요.');
    }
    const fixedIds: Record<string, string> = {
      'official-water-7d': 'part-official-water',
      'official-stretch-weekly': 'part-official-stretch',
    };
    const id = fixedIds[challengeId] ?? `part-${challengeId}-${sequence.current++}`;
    const target = targetFor(definition);
    const participation: ChallengeParticipation = {
      id,
      challengeId,
      title: definition.title,
      kind: definition.kind,
      startDate: CHALLENGE_DEMO_TODAY,
      endDate: addDays(CHALLENGE_DEMO_TODAY, durationFor(definition) - 1),
      status: 'active',
      completed: 0,
      target,
      percent: 0,
      todayCompleted: false,
      checkInDates: [],
      badgeId: definition.badgeId,
      targetIds: selection ? [...selection.targetIds] : undefined,
      targetSummary: selection?.targetSummary,
    };
    setParticipations((current) => [...current, participation]);
    return id;
  }

  function checkIn(participationId: string) {
    const participation = participations.find((item) => item.id === participationId);
    const definition = definitions.find((item) => item.id === participation?.challengeId);
    if (
      !participation ||
      !definition ||
      !['official', 'personal'].includes(participation.kind) ||
      participation.status !== 'active' ||
      participation.startDate > CHALLENGE_DEMO_TODAY ||
      participation.endDate < CHALLENGE_DEMO_TODAY ||
      participation.todayCompleted ||
      participation.checkInDates.includes(CHALLENGE_DEMO_TODAY)
    ) return;
    if (definition.frequency.type === 'weekly') {
      const start = new Date(`${participation.startDate}T00:00:00Z`).getTime();
      const today = new Date(`${CHALLENGE_DEMO_TODAY}T00:00:00Z`).getTime();
      const weekIndex = Math.floor((today - start) / 604_800_000);
      const countThisWeek = participation.checkInDates.filter((date) => {
        const offset = new Date(`${date}T00:00:00Z`).getTime() - start;
        return Math.floor(offset / 604_800_000) === weekIndex;
      }).length;
      if (countThisWeek >= definition.frequency.targetDaysPerWeek) return;
    }
    const completed = Math.min(participation.target, participation.completed + 1);
    const achieved = completed === participation.target;
    setParticipations((current) => current.map((item) => item.id === participationId ? {
      ...item,
      completed,
      percent: Math.round((completed / participation.target) * 100),
      todayCompleted: true,
      checkInDates: [...participation.checkInDates, CHALLENGE_DEMO_TODAY],
      status: achieved ? 'achieved' : 'active',
    } : item));
    if (achieved && participation.badgeId) {
      setBadges((current) =>
        current.map((badge) =>
          badge.id === participation.badgeId && !badge.earnedAt
            ? { ...badge, earnedAt: CHALLENGE_DEMO_TODAY }
            : badge,
        ),
      );
    }
  }

  function createPersonal(input: PersonalChallengeInput): string {
    const suffix = sequence.current++;
    const challengeId = `personal-${suffix}`;
    const participationId = `part-personal-${suffix}`;
    const definition: ChallengeDefinition = {
      id: challengeId,
      kind: 'personal',
      title: input.title.trim(),
      description: input.description.trim(),
      taskLabel: input.taskLabel.trim(),
      frequency: input.frequency,
    };
    const target = targetFor(definition);
    const startDate = input.startDate ?? CHALLENGE_DEMO_TODAY;
    setDefinitions((current) => [...current, definition]);
    setParticipations((current) => [
      ...current,
      {
        id: participationId,
        challengeId,
        title: definition.title,
        kind: 'personal',
        startDate,
        endDate: addDays(startDate, durationFor(definition) - 1),
        status: 'active',
        completed: 0,
        target,
        percent: 0,
        todayCompleted: false,
        checkInDates: [],
      },
    ]);
    return participationId;
  }

  function completeChecklist(participationId: string, itemId: string) {
    setParticipations((current) =>
      current.map((participation) => {
        if (participation.id !== participationId || participation.status !== 'active') {
          return participation;
        }
        const item = participation.checklist?.find((entry) => entry.id === itemId);
        if (!item || !item.available || item.checked) return participation;
        const checklist = participation.checklist!.map((entry) =>
          entry.id === itemId ? { ...entry, checked: true } : entry,
        );
        const completed = checklist.filter((entry) => entry.available && entry.checked).length;
        const target = checklist.filter((entry) => entry.available).length;
        const achieved = completed === target;
        return {
          ...participation,
          checklist,
          completed,
          percent: Math.round((completed / target) * 100),
          status: achieved ? 'achieved' : 'active',
        };
      }),
    );
  }

  function resetDemo() {
    setMedicationEpisodes(initialMedicationEpisodes.map((episode) => ({ ...episode })));
    sequence.current = 1;
    setDefinitions(copyDefinitions());
    setParticipations(copyParticipations());
    setBadges(copyBadges());
  }

  return (
    <ChallengeMockContext.Provider
      value={{
        definitions,
        participations: visibleParticipations,
        medicationEpisodes,
        setMedicationDose,
        badges: visibleBadges,
        demoToday: CHALLENGE_DEMO_TODAY,
        joinChallenge,
        checkIn,
        createPersonal,
        completeChecklist,
        resetDemo,
      }}
    >
      {children}
    </ChallengeMockContext.Provider>
  );
}

export function useChallengeMock(): ChallengeMockValue {
  const value = useContext(ChallengeMockContext);
  if (!value) throw new Error('useChallengeMock은 ChallengeMockProvider 안에서 사용해야 해요.');
  return value;
}
