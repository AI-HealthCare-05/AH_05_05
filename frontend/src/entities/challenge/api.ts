import { http } from '@/shared/api/client';

import type {
  ChallengeCatalogItem,
  ChallengeCatalogResponse,
  ChallengeParticipation,
  ChallengeParticipationListResponse,
  ChallengeVerification,
  UserChallengeBadgeListResponse,
} from './types';

export function getChallengeCatalog(): Promise<ChallengeCatalogResponse> {
  return http.get<ChallengeCatalogResponse>('/v1/user/challenge-catalog?offset=0&limit=100');
}

export function getChallengeCatalogItem(challengeId: number): Promise<ChallengeCatalogItem> {
  return http.get<ChallengeCatalogItem>(`/v1/user/challenge-catalog/${challengeId}`);
}

export function joinOfficialChallenge(challengeId: number): Promise<ChallengeParticipation> {
  return http.post<ChallengeParticipation>(`/v1/user/challenges/${challengeId}/join`);
}

export function cancelOfficialChallenge(participationId: number): Promise<ChallengeParticipation> {
  return http.post<ChallengeParticipation>(`/v1/user/challenges/${participationId}/cancel`);
}

export function getChallengeParticipations(): Promise<ChallengeParticipationListResponse> {
  return http.get<ChallengeParticipationListResponse>('/v1/user/challenges');
}

export function getChallengeParticipation(participationId: number): Promise<ChallengeParticipation> {
  return http.get<ChallengeParticipation>(`/v1/user/challenges/${participationId}`);
}

export function submitChallengeVerification(
  participationId: number,
  payload: { verification_date: string; idempotency_key: string },
): Promise<ChallengeVerification> {
  return http.post<ChallengeVerification>(
    `/v1/user/challenges/${participationId}/verifications`,
    payload,
  );
}

export function getUserChallengeBadges(): Promise<UserChallengeBadgeListResponse> {
  return http.get<UserChallengeBadgeListResponse>('/v1/user/badges');
}
