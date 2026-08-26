/**
 * 챗봇 API. 화면은 이 함수만 부릅니다.
 *
 * 명세 15번은 SSE(text/event-stream)로 적혀 있지만 **일반 JSON 응답으로 먼저 붙입니다.**
 * 명세 비고의 폴백을 따른 것입니다 — SSE를 먼저 하면 백엔드가 text/event-stream을
 * 내놓을 때까지 화면이 대기하게 됩니다. 나중에 스트리밍으로 바꿀 때 이 파일 안만
 * 바뀌고 화면 코드는 그대로입니다.
 */
import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockDeleteChatSessions,
  mockGetChatMessages,
  mockListChatSessions,
  mockSendChat,
} from './api.mock';
import type {
  ChatMessage,
  ChatSessionSummary,
  SendChatPayload,
  SendChatResult,
} from './types';

/** REQ-CHAT-001 — POST /chat · 명세 15번 */
export async function sendChat(payload: SendChatPayload): Promise<SendChatResult> {
  if (USE_MOCK) {
    // LLM 응답은 실제로 수 초 걸립니다. 대기 상태를 확인할 수 있게 길게 잡았습니다.
    await mockDelay(1200);
    return mockSendChat(payload);
  }
  return http.post<SendChatResult>('/chat', payload);
}

/** #111 임시 이력 경계. 실 API 경로를 추측하지 않고 계약 확정 후 내부만 교체합니다. */
export async function getChatMessages(sessionId: number): Promise<ChatMessage[]> {
  if (!USE_MOCK) throw new Error('대화 이력 API가 아직 준비되지 않았어요.');
  await mockDelay();
  return mockGetChatMessages(sessionId);
}

/** #111 임시 세션 목록 경계. 백엔드 계약이 확정되면 내부만 HTTP 조회로 교체합니다. */
export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  if (!USE_MOCK) throw new Error('대화 목록 API가 아직 준비되지 않았어요.');
  await mockDelay();
  return mockListChatSessions();
}

/** #111 임시 다중 삭제 경계. 실제 소프트 삭제 계약은 백엔드 API 확정 후 연결합니다. */
export async function deleteChatSessions(sessionIds: readonly number[]): Promise<void> {
  if (sessionIds.length === 0) return;
  if (!USE_MOCK) throw new Error('대화 삭제 API가 아직 준비되지 않았어요.');
  await mockDelay();
  mockDeleteChatSessions(sessionIds);
}
