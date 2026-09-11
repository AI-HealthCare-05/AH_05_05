import type { CustomChallengeParticipation } from './types';

/** A day is achieved only when every actual goal for that date is complete. */
export function customChallengeDayProgress(item: CustomChallengeParticipation) {
  if (item.targetDayCount !== undefined && item.completedDayCount !== undefined && item.dayProgressRate !== undefined) {
    return { target: item.targetDayCount, completed: item.completedDayCount,
      rate: item.targetDayCount > 0 ? Number(item.dayProgressRate) : 0 };
  }
  // Older API responses still include all live/frozen occurrence snapshots.
  const days = new Map<string, boolean>();
  for (const goal of item.occurrences) {
    days.set(goal.scheduledDate, (days.get(goal.scheduledDate) ?? true) && goal.isCompleted);
  }
  const target = days.size;
  const completed = [...days.values()].filter(Boolean).length;
  return { target, completed, rate: target ? Number((completed * 100 / target).toFixed(2)) : 0 };
}
