/**
 * 챗봇 API. 화면은 이 함수만 부릅니다.
 *
 * SSE는 LLM 원문이 아니라 고정 진행 상태와 안전성 검사를 통과한 최종 답변만 받습니다.
 */
import {
  getAuthGeneration,
  http,
  mockDelay,
  restoreAccountPrincipal,
} from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockDeleteChatSessions,
  mockGetChatMessages,
  mockListChatSessions,
  mockSendChat,
} from './api.mock';
import type {
  ChatMessage,
  ChatProgress,
  ChatProgressHandler,
  ChatProgressStage,
  ChatSessionSummary,
  SendChatPayload,
  SendChatResult,
} from './types';

export class ChatSessionNotFoundError extends Error {
  constructor() {
    super('대화를 찾지 못했어요.');
    this.name = 'ChatSessionNotFoundError';
  }
}

export class ChatRequestAbortedError extends Error {
  constructor() {
    super('로그인 상태가 바뀌어 채팅 요청을 중단했어요.');
    this.name = 'ChatRequestAbortedError';
  }
}

const PROGRESS_MESSAGES: Record<ChatProgressStage, string> = {
  QUESTION_CHECKING: '질문 확인 중',
  EVIDENCE_SEARCHING: '근거 검색 중',
  ANSWER_GENERATING: '답변 정리 중',
  SAFETY_CHECKING: '안전 확인 중',
};

function fixedProgress(data: unknown): ChatProgress | null {
  if (typeof data !== 'object' || data === null || !('stage' in data)) return null;
  const stage = data.stage;
  if (typeof stage !== 'string' || !(stage in PROGRESS_MESSAGES)) return null;
  const safeStage = stage as ChatProgressStage;
  return { stage: safeStage, message: PROGRESS_MESSAGES[safeStage] };
}

function isSendChatResult(data: unknown): data is SendChatResult {
  if (typeof data !== 'object' || data === null) return false;
  const value = data as Partial<SendChatResult>;
  return (
    typeof value.conversationId === 'number' &&
    typeof value.messageId === 'number' &&
    typeof value.answer === 'string' &&
    Array.isArray(value.sources)
  );
}

function parseEventFrame(frame: string): { event: string; data: unknown } | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join('\n')) as unknown };
}

async function readChatStream(
  response: Response,
  onProgress?: ChatProgressHandler,
): Promise<SendChatResult> {
  if (!response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('채팅 스트림 응답 형식이 올바르지 않습니다.');
  }
  if (response.body === null) throw new Error('채팅 스트림을 읽을 수 없습니다.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed: SendChatResult | null = null;

  const handleFrame = (frame: string) => {
    const parsed = parseEventFrame(frame);
    if (parsed === null) return;
    if (parsed.event === 'progress') {
      const progress = fixedProgress(parsed.data);
      if (progress !== null) onProgress?.(progress);
      return;
    }
    if (parsed.event === 'complete') {
      if (!isSendChatResult(parsed.data)) {
        throw new Error('완료된 채팅 응답 형식이 올바르지 않습니다.');
      }
      completed = parsed.data;
      return;
    }
    if (parsed.event === 'error') {
      const data = parsed.data as { message?: unknown };
      throw new Error(
        typeof data?.message === 'string'
          ? data.message
          : '답변을 가져오지 못했어요.',
      );
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = buffer.replaceAll('\r\n', '\n');
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      handleFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }
    if (done) break;
  }
  if (buffer.trim()) handleFrame(buffer);
  if (completed === null) throw new Error('검증된 최종 답변을 받지 못했습니다.');
  return completed;
}

/** REQ-CHAT-001 — POST /api/v1/chat */
export async function sendChat(
  payload: SendChatPayload,
  onProgress?: ChatProgressHandler,
): Promise<SendChatResult> {
  const requestAuthGeneration = getAuthGeneration();
  const requestPrincipal = restoreAccountPrincipal();
  if (USE_MOCK) {
    for (const stage of Object.keys(PROGRESS_MESSAGES) as ChatProgressStage[]) {
      onProgress?.({ stage, message: PROGRESS_MESSAGES[stage] });
      await mockDelay(300);
    }
    if (requestAuthGeneration !== getAuthGeneration()) {
      throw new ChatRequestAbortedError();
    }
    return mockSendChat(payload, requestPrincipal);
  }
  const response = await http.postStream('/v1/chat/stream', payload);
  const result = await readChatStream(response, onProgress);
  if (requestAuthGeneration !== getAuthGeneration()) {
    throw new ChatRequestAbortedError();
  }
  return result;
}

/** #111 임시 이력 경계. 실 API 경로를 추측하지 않고 계약 확정 후 내부만 교체합니다. */
export async function getChatMessages(sessionId: number): Promise<ChatMessage[]> {
  if (!USE_MOCK) throw new Error('대화 이력 API가 아직 준비되지 않았어요.');
  const requestAuthGeneration = getAuthGeneration();
  const requestPrincipal = restoreAccountPrincipal();
  await mockDelay();
  if (requestAuthGeneration !== getAuthGeneration()) {
    throw new Error('로그인 상태가 바뀌어 대화 조회를 중단했어요.');
  }
  const messages = mockGetChatMessages(sessionId, requestPrincipal);
  if (messages === null) throw new ChatSessionNotFoundError();
  return messages;
}

/** #111 임시 세션 목록 경계. 백엔드 계약이 확정되면 내부만 HTTP 조회로 교체합니다. */
export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  if (!USE_MOCK) throw new Error('대화 목록 API가 아직 준비되지 않았어요.');
  const requestAuthGeneration = getAuthGeneration();
  const requestPrincipal = restoreAccountPrincipal();
  await mockDelay();
  if (requestAuthGeneration !== getAuthGeneration()) {
    throw new Error('로그인 상태가 바뀌어 대화 목록 조회를 중단했어요.');
  }
  return mockListChatSessions(requestPrincipal);
}

/** #111 임시 다중 삭제 경계. 실제 소프트 삭제 계약은 백엔드 API 확정 후 연결합니다. */
export async function deleteChatSessions(sessionIds: readonly number[]): Promise<void> {
  if (sessionIds.length === 0) return;
  if (!USE_MOCK) throw new Error('대화 삭제 API가 아직 준비되지 않았어요.');
  const requestAuthGeneration = getAuthGeneration();
  const requestPrincipal = restoreAccountPrincipal();
  await mockDelay();
  if (requestAuthGeneration !== getAuthGeneration()) {
    throw new Error('로그인 상태가 바뀌어 대화 삭제를 중단했어요.');
  }
  mockDeleteChatSessions(sessionIds, requestPrincipal);
}
