import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

interface ChatSessionValue {
  activeSessionId: number | null;
  selectSession: (sessionId: number) => void;
  startNewSession: () => void;
}

const ChatSessionContext = createContext<ChatSessionValue | null>(null);

/** 현재 앱 실행에서 열어둔 채팅방만 기억하고, 메시지는 entities/chat에서 다시 읽습니다. */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const value = useMemo(
    () => ({
      activeSessionId,
      selectSession: (sessionId: number) => setActiveSessionId(sessionId),
      startNewSession: () => setActiveSessionId(null),
    }),
    [activeSessionId],
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
