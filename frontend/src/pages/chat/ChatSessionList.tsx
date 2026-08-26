import { Plus } from 'lucide-react';
import type { ChatSessionSummary } from '@/entities/chat';
import { BottomTabbar, Header, type TabKey } from '@/shared/ui';

interface ChatSessionListProps {
  sessions: ChatSessionSummary[];
  onBack: () => void;
  onNewChat: () => void;
  onOpen: (sessionId: number) => void;
  onTabChange: (key: TabKey) => void;
}

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  month: 'long',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

export function ChatSessionList({
  sessions,
  onBack,
  onNewChat,
  onOpen,
  onTabChange,
}: ChatSessionListProps) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title="AI 상담"
        onBack={onBack}
        right={
          <button
            type="button"
            aria-label="새 채팅"
            onClick={onNewChat}
            className="flex size-touch items-center justify-center text-primary"
          >
            <Plus aria-hidden className="size-6" />
          </button>
        }
      />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <h2 className="text-xl font-bold text-foreground">최근 대화</h2>
        <div className="flex flex-col overflow-hidden rounded-card border border-border bg-card shadow-card">
          {sessions.map((session) => (
            <button
              key={session.sessionId}
              type="button"
              aria-label={`${session.title} ${session.lastMessagePreview}`}
              onClick={() => onOpen(session.sessionId)}
              className="flex min-h-touch min-w-0 flex-col gap-1 border-b border-border px-4 py-3 text-left last:border-b-0"
            >
              <span className="w-full truncate text-base font-bold text-foreground">
                {session.title}
              </span>
              <span className="w-full truncate text-sm text-muted-foreground">
                {session.lastMessagePreview}
              </span>
              <time className="text-xs text-muted-foreground" dateTime={session.lastMessageAt}>
                {dateFormatter.format(new Date(session.lastMessageAt))}
              </time>
            </button>
          ))}
        </div>
      </main>

      <BottomTabbar active="chat" onChange={onTabChange} className="border-t border-border" />
    </div>
  );
}
