/**
 * 생활관리 가이드 API. 화면은 이 함수만 부릅니다.
 * 목업 ↔ 실서버 전환 규칙은 entities/document/api.ts 와 같습니다.
 */
import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockLifeGuide } from './api.mock';
import type { LifeGuide } from './types';

/** REQ-CARE-004 — GET /life-guide · 명세 13번. 쿼리 파라미터 없습니다. */
export async function getLifeGuide(): Promise<LifeGuide> {
  if (USE_MOCK) {
    await mockDelay();
    return mockLifeGuide();
  }
  return http.get<LifeGuide>('/life-guide');
}
