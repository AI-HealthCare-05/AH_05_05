import type { ChallengeParticipation } from '@/entities/challenge';

/** The server counts approved days (daily) or certifications (weekly/total). */
export function officialChallengeProgress(item: ChallengeParticipation) {
  const value = Number(item.progress_rate);
  return {
    rate: item.target_count > 0 && Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0,
    label: `${item.completed_count} / ${item.target_count}${item.challenge.frequency_code === 'DAILY' ? '일' : '회'}`,
  };
}
