import type { MealSlot } from '@/shared/model/mealSlot';

export interface ChallengeMedicationEpisode {
  id: string;
  recordId: number;
  label: string;
  startDate: string;
  endDate: string;
  slots: MealSlot[];
  target: number;
  completed: number;
  todayTaken: boolean;
}

export type ChallengeKind =
  | 'official'
  | 'medication'
  | 'supplement'
  | 'review'
  | 'visit'
  | 'personal';

export type ChallengeFrequency =
  | { type: 'daily'; durationDays: number }
  | { type: 'weekly'; targetDaysPerWeek: number; durationWeeks: number };

export interface ChallengeBadge {
  id: string;
  name: string;
  description: string;
  icon: 'check' | 'pill' | 'sprout';
  imageUrl?: string;
  earnedAt?: string;
  awards?: ChallengeBadgeAward[];
}

export interface ChallengeBadgeAward {
  participationId: string;
  episodeId: string;
  title: string;
  earnedAt: string;
}

export interface ChallengeDefinition {
  id: string;
  kind: ChallengeKind;
  title: string;
  description: string;
  taskLabel: string;
  frequency: ChallengeFrequency;
  enrollmentStart?: string;
  enrollmentEnd?: string;
  badgeId?: string;
}

export interface ChallengeChecklistItem {
  id: string;
  label: string;
  checked: boolean;
  destination: 'medications' | 'supplements' | 'notes' | 'visit';
  available: boolean;
}

export interface ChallengeParticipation {
  id: string;
  challengeId: string;
  title: string;
  kind: ChallengeKind;
  startDate: string;
  endDate: string;
  status: 'active' | 'achieved' | 'missed';
  completed: number;
  target: number;
  percent: number;
  todayCompleted: boolean;
  checkInDates: string[];
  badgeId?: string;
  checklist?: ChallengeChecklistItem[];
  episodeId?: string;
  targetIds?: string[];
  targetSummary?: string;
}

export interface PersonalChallengeInput {
  title: string;
  description: string;
  taskLabel: string;
  frequency: ChallengeFrequency;
  startDate?: string;
}

export interface ChallengeMockValue {
  medicationEpisodes: ChallengeMedicationEpisode[];
  setMedicationDose: (recordIds: number[], taken: boolean) => void;
  definitions: ChallengeDefinition[];
  participations: ChallengeParticipation[];
  badges: ChallengeBadge[];
  demoToday: string;
  joinChallenge: (
    id: string,
    selection?: { targetIds: string[]; targetSummary: string },
  ) => string;
  checkIn: (participationId: string) => void;
  createPersonal: (input: PersonalChallengeInput) => string;
  completeChecklist: (participationId: string, itemId: string) => void;
  resetDemo: () => void;
}
