export type CustomChallengeType = 'MEDICATION' | 'SUPPLEMENT' | 'VISIT';
export type CustomChallengeParticipationStatus = 'ACTIVE' | 'COMPLETED' | 'CANCELLED' | 'EXPIRED';
export type CustomChallengeMealSlot = 'MORNING' | 'LUNCH' | 'EVENING' | 'BEDTIME';

export interface CustomChallengeRecommendationTarget {
  id: number;
  name: string;
  existingParticipationId: number | null;
}

export interface CustomChallengeRewardBadge {
  id: number;
  name: string;
  description: string | null;
  imagePath: string;
}

export interface CustomChallengeRecommendation {
  templateId: number;
  challengeType: CustomChallengeType;
  challengeName: string;
  rewardBadge: CustomChallengeRewardBadge | null;
  action: 'NONE';
  targets: CustomChallengeRecommendationTarget[];
}

export interface CustomChallengeRecommendationListResponse {
  items: CustomChallengeRecommendation[];
  totalCount: number;
}

export interface JoinCustomChallengePayload {
  targetIds: number[];
  idempotencyKey: string;
}

export interface CustomChallengeTarget {
  id: number;
  sourceId: number;
  name: string;
}

export interface CustomChallengeOccurrence {
  id: number;
  targetId: number;
  scheduledDate: string;
  slot: CustomChallengeMealSlot;
  scheduledAt: string;
  isCompleted: boolean;
}

export interface CustomChallengeParticipation {
  id: number;
  templateId: number;
  challengeType: CustomChallengeType;
  challengeName: string;
  rewardBadge: CustomChallengeRewardBadge | null;
  status: CustomChallengeParticipationStatus;
  joinedAt: string;
  endAt: string;
  actualEndDate: string | null;
  targetCount: number;
  completedCount: number;
  progressRate: number | string;
  action: 'NONE';
  targets: CustomChallengeTarget[];
  occurrences: CustomChallengeOccurrence[];
}

export interface CustomChallengeParticipationListResponse {
  items: CustomChallengeParticipation[];
  totalCount: number;
}

export interface CustomChallengeBadgeAward {
  id: number;
  participationId: number;
  badgeId: number;
  badgeName: string;
  badgeImagePath: string;
  awardedAt: string;
}

export interface CustomChallengeBadgeAwardListResponse {
  items: CustomChallengeBadgeAward[];
  totalCount: number;
}
