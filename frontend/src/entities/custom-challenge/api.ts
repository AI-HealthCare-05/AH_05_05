import { http } from '@/shared/api/client';

import type {
  CustomChallengeBadgeAwardListResponse,
  CustomChallengeParticipation,
  CustomChallengeParticipationListResponse,
  CustomChallengeRecommendationListResponse,
  CustomChallengeRewardClaimResponse,
  JoinCustomChallengePayload,
} from './types';

export function getCustomChallengeRecommendations(): Promise<CustomChallengeRecommendationListResponse> {
  return http.get<CustomChallengeRecommendationListResponse>('/v1/user/custom-challenge-recommendations');
}

export function joinCustomChallenge(
  templateId: number,
  payload: JoinCustomChallengePayload,
): Promise<CustomChallengeParticipation> {
  return http.post<CustomChallengeParticipation>(
    `/v1/user/custom-challenge-recommendations/${templateId}/participations`,
    payload,
  );
}

export function getCustomChallengeParticipations(): Promise<CustomChallengeParticipationListResponse> {
  return http.get<CustomChallengeParticipationListResponse>('/v1/user/custom-challenge-participations');
}

export function getCustomChallengeParticipation(
  participationId: number,
): Promise<CustomChallengeParticipation> {
  return http.get<CustomChallengeParticipation>(
    `/v1/user/custom-challenge-participations/${participationId}`,
  );
}

export function getCustomChallengeBadges(): Promise<CustomChallengeBadgeAwardListResponse> {
  return http.get<CustomChallengeBadgeAwardListResponse>('/v1/user/custom-challenges/badges');
}

export function cancelCustomChallenge(participationId: number): Promise<CustomChallengeParticipation> {
  return http.post<CustomChallengeParticipation>(`/v1/user/custom-challenge-participations/${participationId}/cancel`);
}

export function claimCustomChallengeReward(participationId: number): Promise<CustomChallengeRewardClaimResponse> {
  return http.post<CustomChallengeRewardClaimResponse>(`/v1/user/custom-challenge-participations/${participationId}/claim-reward`);
}
