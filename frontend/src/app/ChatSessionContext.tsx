import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSession } from './SessionContext';

interface ChatSessionValue {
  activeSessionId: number | null;
  sessionRevision: number;
  chatRequestPending: boolean;
  beginChatRequest: (requestId: string) => void;
  endChatRequest: (requestId: string) => void;
  selectSession: (sessionId: number) => void;
  startNewSession: () => void;
  notifySessionUpdated: () => void;
}

const ChatSessionContext = createContext<ChatSessionValue | null>(null);

/** 현재 앱 실행에서 열어둔 채팅방만 기억하고, 메시지는 entities/chat에서 다시 읽습니다. */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const { principalKey } = useSession();
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionRevision, setSessionRevision] = useState(0);
  const [pendingRequestIds, setPendingRequestIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    // 로그아웃하거나 다른 계정으로 바뀌면 앱 메모리의 대화 선택·전송 상태를 넘기지 않습니다.
    setActiveSessionId(null);
    setPendingRequestIds(new Set());
  }, [principalKey]);

  const value = useMemo(
    () => ({
      activeSessionId,
      sessionRevision,
      chatRequestPending: pendingRequestIds.size > 0,
      beginChatRequest: (requestId: string) => {
        setPendingRequestIds((current) => new Set(current).add(requestId));
      },
      endChatRequest: (requestId: string) => {
        setPendingRequestIds((current) => {
          if (!current.has(requestId)) return current;
          const next = new Set(current);
          next.delete(requestId);
          return next;
        });
      },
      selectSession: (sessionId: number) => setActiveSessionId(sessionId),
      startNewSession: () => setActiveSessionId(null),
      notifySessionUpdated: () => setSessionRevision((current) => current + 1),
    }),
    [activeSessionId, pendingRequestIds, sessionRevision],
  );

  return <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>;
}

export function useChatSession(): ChatSessionValue {
  const value = useContext(ChatSessionContext);
  if (value === null) {
    throw new Error('useChatSession은 ChatSessionProvider 안에서 사용해야 합니다.');
  }
  return value;
}
