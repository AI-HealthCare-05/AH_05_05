export const CUSTOM_CHALLENGE_PROGRESS_INVALIDATED_EVENT = 'rxvita:custom-challenge-progress-invalidated';

/** 복약·영양제 기록 저장/되돌리기 성공 뒤 맞춤 챌린지 GET 재조회를 요청합니다. */
export function invalidateCustomChallengeProgress(): void {
  window.dispatchEvent(new Event(CUSTOM_CHALLENGE_PROGRESS_INVALIDATED_EVENT));
}

/** Home 요약처럼 현재 화면에 남아 있는 조회 컴포넌트가 진행률 무효화를 구독합니다. */
export function subscribeCustomChallengeProgressInvalidation(listener: () => void): () => void {
  window.addEventListener(CUSTOM_CHALLENGE_PROGRESS_INVALIDATED_EVENT, listener);
  return () => window.removeEventListener(CUSTOM_CHALLENGE_PROGRESS_INVALIDATED_EVENT, listener);
}
