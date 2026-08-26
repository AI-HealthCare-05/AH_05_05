import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { clearChatSessionCache } from '@/entities/chat';
import { useSession } from './SessionContext';

interface ChatSessionValue {
  activeSessionId: number | null;
  sessionRevision: number;
  selectSession: (sessionId: number) => void;
  startNewSession: () => void;
  notifySessionUpdated: () => void;
}

const ChatSessionContext = createContext<ChatSessionValue | null>(null);

/** 현재 앱 실행에서 열어둔 채팅방만 기억하고, 메시지는 entities/chat에서 다시 읽습니다. */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const { authenticated } = useSession();
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionRevision, setSessionRevision] = useState(0);

  useEffect(() => {
    if (!authenticated) {
      setActiveSessionId(null);
      clearChatSessionCache();
    }
  }, [authenticated]);

  const value = useMemo(
    () => ({
      activeSessionId,
      sessionRevision,
      selectSession: (sessionId: number) => setActiveSessionId(sessionId),
      startNewSession: () => setActiveSessionId(null),
      notifySessionUpdated: () => setSessionRevision((current) => current + 1),
    }),
    [activeSessionId, sessionRevision],
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
