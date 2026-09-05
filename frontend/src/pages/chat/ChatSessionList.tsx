import type { ChatSessionSummary } from '@/entities/chat';
import { BottomTabbar, Button, Checkbox, Header, type TabKey } from '@/shared/ui';

interface ChatSessionListProps {
  sessions: ChatSessionSummary[];
  selectionMode: boolean;
  selectedSessionIds: ReadonlySet<number>;
  onBack: () => void;
  onDeleteSelected: () => void;
  onNewChat: () => void;
  onOpen: (sessionId: number) => void;
  onTabChange: (key: TabKey) => void;
  onToggleSelectionMode: () => void;
  onToggleSession: (sessionId: number) => void;
}

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  month: 'long',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

function formatSessionDate(value: string): string {
  const date = new Date(value);
  const now = new Date();
  if (
    date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
  ) {
    return `오늘 · ${new Intl.DateTimeFormat('ko-KR', {
      hour: 'numeric',
      minute: '2-digit',
    }).format(date)}`;
  }
  return dateFormatter.format(date);
}

export function ChatSessionList({
  sessions,
  selectionMode,
  selectedSessionIds,
  onBack,
  onDeleteSelected,
  onNewChat,
  onOpen,
  onTabChange,
  onToggleSelectionMode,
  onToggleSession,
}: ChatSessionListProps) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title="챗봇"
        onBack={onBack}
        right={
          <button
            type="button"
            aria-label={selectionMode ? '삭제 취소' : '대화 삭제'}
            onClick={onToggleSelectionMode}
            className="flex min-h-touch items-center justify-center px-2 text-sm font-bold text-foreground"
          >
            {selectionMode ? '취소' : '삭제'}
          </button>
        }
      />

      <main className="flex flex-1 flex-col gap-4 overflow-y-auto px-page-x py-4">
        {!selectionMode && (
          <Button aria-label="새 채팅" onClick={onNewChat} className="h-12 rounded-button">
            + 새 상담
          </Button>
        )}
        <h2 className="text-xl font-bold text-foreground">
          {selectionMode ? '삭제할 대화를 선택하세요' : '최근 대화'}
        </h2>
        <div className="flex flex-col overflow-hidden rounded-card border border-border bg-card shadow-card">
          {sessions.map((session) => {
            const content = (
              <>
                <span className="w-full truncate text-base font-bold text-foreground">
                  {session.title}
                </span>
                <span className="w-full truncate text-sm text-muted-foreground">
                  {session.lastMessagePreview}
                </span>
                <time className="text-unit text-muted-foreground" dateTime={session.lastMessageAt}>
                  {formatSessionDate(session.lastMessageAt)}
                </time>
              </>
            );

            return selectionMode ? (
              <label
                key={session.sessionId}
                className="flex min-h-touch min-w-0 cursor-pointer items-center gap-3 border-b border-border px-4 py-3 last:border-b-0"
              >
                <Checkbox
                  aria-label={`${session.title} 선택`}
                  checked={selectedSessionIds.has(session.sessionId)}
                  onCheckedChange={() => onToggleSession(session.sessionId)}
                />
                <span className="flex min-w-0 flex-1 flex-col gap-1 text-left">{content}</span>
              </label>
            ) : (
              <button
                key={session.sessionId}
                type="button"
                aria-label={`${session.title} ${session.lastMessagePreview}`}
                onClick={() => onOpen(session.sessionId)}
                className="flex min-h-touch min-w-0 flex-col gap-1 border-b border-border px-4 py-3 text-left last:border-b-0"
              >
                {content}
              </button>
            );
          })}
        </div>
      </main>

      {selectionMode && (
        <div className="shrink-0 border-t border-border bg-card px-page-x py-3">
          <Button disabled={selectedSessionIds.size === 0} onClick={onDeleteSelected}>
            {selectedSessionIds.size}개 삭제
          </Button>
        </div>
      )}
      <BottomTabbar active="chat" onChange={onTabChange} className="border-t border-border" />
    </div>
  );
}
