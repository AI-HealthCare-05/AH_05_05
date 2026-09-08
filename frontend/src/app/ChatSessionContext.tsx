import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
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

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const { principalKey } = useSession();

  return (
    <PrincipalChatSessionProvider key={principalKey ?? 'guest'}>
      {children}
    </PrincipalChatSessionProvider>
  );
}

/** 현재 계정이 앱 실행 중 열어둔 채팅방만 기억하고, 메시지는 entities/chat에서 다시 읽습니다. */
function PrincipalChatSessionProvider({ children }: { children: ReactNode }) {
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionRevision, setSessionRevision] = useState(0);
  const [pendingRequestIds, setPendingRequestIds] = useState<Set<string>>(() => new Set());

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
