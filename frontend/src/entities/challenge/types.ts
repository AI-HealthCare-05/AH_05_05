export type ChallengeCheckType = 'SELF' | 'MANUAL' | string;
export type ChallengeFrequencyCode = 'DAILY' | 'WEEKLY_3' | 'TOTAL_10' | string;

export interface ChallengeRewardBadge {
  id: number;
  name: string;
  description: string | null;
  image_path: string;
}

export interface ChallengeCatalogItem {
  id: number;
  name: string;
  phrase: string;
  description: string | null;
  challenge_type_code: string;
  period_code: string;
  duration_days: number;
  check_type_code: ChallengeCheckType;
  frequency_code: ChallengeFrequencyCode;
  recruit_start_at: string;
  recruit_end_at: string;
  reward_badge: ChallengeRewardBadge | null;
  can_join: boolean;
  participation_id: number | null;
}

export interface ChallengeCatalogResponse {
  items: ChallengeCatalogItem[];
  total_count: number;
  offset: number;
  limit: number;
}

export interface ChallengeProgressPeriod {
  id: number;
  period_start: string;
  period_end: string;
  target_count: number;
  completed_count: number;
  progress_rate: number | string;
  is_completed: boolean;
  completed_at: string | null;
}

export interface ChallengeVerification {
  id: number;
  user_challenge_id: number;
  progress_id: number;
  verification_date: string;
  content: string | null;
  image_path: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  rejection_reason: string | null;
  reviewed_by_admin_id: number | null;
  reviewed_at: string | null;
  submitted_at: string;
}

export interface ChallengeParticipation {
  id: number;
  user_id: number;
  challenge_id: number;
  challenge_name: string;
  status: 'ACTIVE' | 'COMPLETED' | 'CANCELLED' | 'EXPIRED';
  joined_at: string;
  started_at: string;
  end_at: string;
  target_count: number;
  completed_count: number;
  progress_rate: number | string;
  completed_at: string | null;
  cancelled_at: string | null;
  progress_periods: ChallengeProgressPeriod[];
  challenge: ChallengeCatalogItem;
  today: string;
  today_verification: ChallengeVerification | null;
  can_verify: boolean;
  verified_dates: string[];
}

export interface ChallengeParticipationListResponse {
  items: ChallengeParticipation[];
  total_count: number;
}

export interface UserChallengeBadge {
  id: number;
  user_id: number;
  badge_id: number;
  challenge_id: number;
  user_challenge_id: number;
  status: 'AWARDED' | 'REVOKED';
  badge_name: string;
  badge_image_path: string;
  awarded_at: string;
  revoked_at: string | null;
  revoke_reason: string | null;
}

export interface UserChallengeBadgeListResponse {
  items: UserChallengeBadge[];
  total_count: number;
}
