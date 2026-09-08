import { http } from '@/shared/api/client';

import type {
  CustomChallengeParticipation,
  CustomChallengeParticipationListResponse,
  CustomChallengeRecommendationListResponse,
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
