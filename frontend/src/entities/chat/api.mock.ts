/**
 * 챗봇 목업.
 *
 * 개인 출처(personal)에 페이지를 붙이지 않습니다. 원본 파일을 저장하지 않기로
 * 결정했으므로 개인 출처는 확정한 약봉투의 약 데이터를 가리킵니다.
 * 가짜 페이지 번호를 만들면 근거가 아니라 거짓이 됩니다.
 *
 * 근거 없는 응답 경로(`sources: []`)도 눌러볼 수 있어야 하므로, 질문에 "일반"·"보통"
 * 같은 말이 들어오면 근거 없는 답변을 돌려줍니다. 근거가 없는데 있는 것처럼 보이는 게
 * 이 서비스에서 가장 위험한 실패라, 그 상태를 개발 중에 반드시 확인해야 합니다.
 */
import type {
  ChatMessage,
  ChatSessionSummary,
  SendChatPayload,
  SendChatResult,
} from './types';

const MOCK_CHAT_STORAGE_KEY = 'poke.mock-chat-sessions';

interface MockStoredSession {
  sessionId: number;
  createdAt: string;
  lastMessageAt: string;
  messages: ChatMessage[];
}

interface MockChatStore {
  nextSessionId: number;
  nextMessageId: number;
  sessions: MockStoredSession[];
}

const EMPTY_STORE: MockChatStore = {
  nextSessionId: 77,
  nextMessageId: 1204,
  sessions: [],
};

function readStore(): MockChatStore {
  if (typeof window === 'undefined') return { ...EMPTY_STORE, sessions: [] };
  const saved = window.localStorage.getItem(MOCK_CHAT_STORAGE_KEY);
  if (!saved) return { ...EMPTY_STORE, sessions: [] };
  try {
    const parsed = JSON.parse(saved) as MockChatStore;
    if (!Array.isArray(parsed.sessions)) throw new Error('invalid mock chat store');
    return parsed;
  } catch {
    window.localStorage.removeItem(MOCK_CHAT_STORAGE_KEY);
    return { ...EMPTY_STORE, sessions: [] };
  }
}

function writeStore(store: MockChatStore): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(MOCK_CHAT_STORAGE_KEY, JSON.stringify(store));
}

/** 근거 없는 답변을 돌려줄 질문인지. 목업 전용 규칙입니다. */
function shouldAnswerWithoutSources(message: string): boolean {
  return /일반|보통|아무|그냥/.test(message);
}

export function mockSendChat(payload: SendChatPayload): SendChatResult {
  const store = readStore();
  const sessionId = payload.conversationId ?? store.nextSessionId++;
  const now = new Date().toISOString();
  let session = store.sessions.find((item) => item.sessionId === sessionId);
  if (!session) {
    session = { sessionId, createdAt: now, lastMessageAt: now, messages: [] };
    store.sessions.push(session);
  }

  store.nextMessageId += 1;
  const response: SendChatResult = shouldAnswerWithoutSources(payload.message)
    ? {
        conversationId: sessionId,
        messageId: store.nextMessageId,
        answer:
          '수술 후 회복 기간은 사람마다 달라서 일반적인 범위만 말씀드릴 수 있어요. '
          + '정확한 판단은 담당 의료진에게 확인해주세요.',
        sources: [],
      }
    : {
        conversationId: sessionId,
        messageId: store.nextMessageId,
        answer:
          '리바록사반을 복용하는 동안 잇몸이나 코피가 잘 멎지 않거나 이유 없이 멍이 크게 '
          + '들면 처방한 의료진에게 알려주세요. 임의로 중단하지 마세요.',
        sources: [
          { scope: 'personal', title: '약봉투 · 리바록사반 10mg' },
          {
            scope: 'official',
            title: 'e약은요 · 리바록사반',
            organization: '식품의약품안전처',
            url: 'https://nedrug.mfds.go.kr',
          },
        ],
      };

  session.messages.push(
    { role: 'user', text: payload.message, sources: [] },
    { role: 'assistant', text: response.answer, sources: response.sources },
  );
  session.lastMessageAt = now;
  writeStore(store);
  return response;
}

export function mockGetChatMessages(sessionId: number): ChatMessage[] {
  const session = readStore().sessions.find((item) => item.sessionId === sessionId);
  if (!session) throw new Error('대화를 찾지 못했어요.');
  return session.messages.map((message) => ({
    ...message,
    sources: message.sources.map((source) => ({ ...source })),
  }));
}

export function mockListChatSessions(): ChatSessionSummary[] {
  return readStore()
    .sessions.map((session) => ({
      sessionId: session.sessionId,
      title: session.messages.find((message) => message.role === 'user')?.text ?? '새 대화',
      lastMessagePreview: session.messages.at(-1)?.text ?? '',
      lastMessageAt: session.lastMessageAt,
    }))
    .sort((left, right) => right.lastMessageAt.localeCompare(left.lastMessageAt));
}

export function mockDeleteChatSessions(sessionIds: readonly number[]): void {
  if (sessionIds.length === 0) return;
  const deleted = new Set(sessionIds);
  const store = readStore();
  store.sessions = store.sessions.filter((session) => !deleted.has(session.sessionId));
  writeStore(store);
}
