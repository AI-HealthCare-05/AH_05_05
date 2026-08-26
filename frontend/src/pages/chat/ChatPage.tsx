import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useChatSession } from '@/app/ChatSessionContext';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  Input,
  type TabKey,
} from '@/shared/ui';
import {
  ChatSessionNotFoundError,
  deleteChatSessions,
  getChatMessages,
  listChatSessions,
  sendChat,
  type ChatMessage,
  type ChatSessionSummary,
  type SendChatPayload,
  type SendChatResult,
} from '@/entities/chat';
import { ChatDeleteDialog } from './ChatDeleteDialog';
import { ChatSessionList } from './ChatSessionList';
import { ChatStartGuide } from './ChatStartGuide';
import { SourceList } from './SourceList';

/**
 * REQ-CHAT-001 · 화면 17 AI 상담 — 공공 근거를 보여주는 화면.
 *
 * 실제 이력 API 경로는 아직 확정되지 않아 loader 경계만 둡니다. loader가 없으면 빈 이력으로
 * 바로 시작하며, 서버 계약이 생기면 이 화면을 바꾸지 않고 entities/chat 함수로 교체합니다.
 *
 * 말풍선은 Card를 재사용하지 않고 직접 만들었습니다 — 정렬과 최대폭 규칙이 다릅니다.
 */
interface ChatLocationState {
  recordId?: number;
}

type ChatHistoryLoader = () => Promise<ChatMessage[]>;
type ChatSender = (payload: SendChatPayload) => Promise<SendChatResult>;
type ChatSessionListLoader = () => Promise<ChatSessionSummary[]>;
type ChatSessionHistoryLoader = (sessionId: number) => Promise<ChatMessage[]>;
type ChatSessionDeleter = (sessionIds: readonly number[]) => Promise<void>;
type ChatView = 'loading' | 'list' | 'room';

interface ChatPageProps {
  historyLoader?: ChatHistoryLoader;
  chatSender?: ChatSender;
  sessionListLoader?: ChatSessionListLoader;
  sessionHistoryLoader?: ChatSessionHistoryLoader;
  sessionDeleter?: ChatSessionDeleter;
}

export function ChatPage({
  historyLoader,
  chatSender = sendChat,
  sessionListLoader = listChatSessions,
  sessionHistoryLoader = getChatMessages,
  sessionDeleter = deleteChatSessions,
}: ChatPageProps = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ChatLocationState | null) ?? {};
  const recordId = state.recordId ?? null;
  const {
    activeSessionId,
    sessionRevision,
    chatRequestPending,
    beginChatRequest,
    endChatRequest,
    selectSession,
    startNewSession,
    notifySessionUpdated,
  } = useChatSession();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [view, setView] = useState<ChatView>('loading');
  const [newChatRequested, setNewChatRequested] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [sessionListError, setSessionListError] = useState<string | null>(null);
  const [sessionListReloadKey, setSessionListReloadKey] = useState(0);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<Set<number>>(() => new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const handledSessionRevisionRef = useRef(sessionRevision);
  const suppressNextSessionRefreshRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let requestKind: 'history' | 'list' | null = null;
    setHistoryError(null);
    setSessionListError(null);

    async function loadEntry() {
      try {
        if (historyLoader !== undefined) {
          requestKind = 'history';
          setHistoryLoading(true);
          const history = await historyLoader();
          if (cancelled) return;
          setMessages(history);
          setView('room');
          return;
        }

        if (activeSessionId !== null) {
          const revisionChanged = handledSessionRevisionRef.current !== sessionRevision;
          const hasCurrentRoom = conversationId === activeSessionId;
          if (
            hasCurrentRoom
            && (!revisionChanged || suppressNextSessionRefreshRef.current)
          ) {
            suppressNextSessionRefreshRef.current = false;
            handledSessionRevisionRef.current = sessionRevision;
            setHistoryLoading(false);
            setView('room');
            return;
          }

          requestKind = 'history';
          setHistoryLoading(true);
          const history = await sessionHistoryLoader(activeSessionId);
          if (cancelled) return;
          setMessages(history);
          setConversationId(activeSessionId);
          handledSessionRevisionRef.current = sessionRevision;
          setView('room');
          return;
        }

        if (newChatRequested) {
          setHistoryLoading(false);
          setView('room');
          return;
        }

        requestKind = 'list';
        setHistoryLoading(true);
        const loadedSessions = await sessionListLoader();
        if (cancelled) return;
        setSessions(loadedSessions);
        if (loadedSessions.length === 0) {
          setMessages([]);
          setConversationId(null);
          setView('room');
        } else {
          setView('list');
        }
      } catch (error: unknown) {
        if (cancelled) return;
        if (error instanceof ChatSessionNotFoundError) {
          handledSessionRevisionRef.current = sessionRevision;
          startNewSession();
          setMessages([]);
          setConversationId(null);
          setNewChatRequested(false);
          setView('loading');
          setSessionListReloadKey((current) => current + 1);
          return;
        }

        setMessages([]);
        const message = error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.';
        if (requestKind === 'list') setSessionListError(message);
        else setHistoryError(message);
        setView('room');
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }

    void loadEntry();
    return () => {
      cancelled = true;
    };
  }, [
    activeSessionId,
    conversationId,
    historyLoader,
    newChatRequested,
    sessionRevision,
    sessionListLoader,
    sessionHistoryLoader,
    sessionListReloadKey,
  ]);

  // 새 메시지·대기 상태가 생기면 맨 아래로 내립니다.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [chatRequestPending, messages, pending]);

  async function sendMessage(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || pending || chatRequestPending || historyLoading || view === 'loading') return;

    const requestId = crypto.randomUUID();
    beginChatRequest(requestId);
    setHistoryError(null);
    setSessionListError(null);
    setMessages((prev) => [...prev, { role: 'user', text: message, sources: [] }]);
    setDraft('');
    setPending(true);
    try {
      const result = await chatSender({
        requestId,
        recordId,
        message,
        conversationId,
      });
      suppressNextSessionRefreshRef.current = true;
      setConversationId(result.conversationId);
      setNewChatRequested(false);
      selectSession(result.conversationId);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: result.answer, sources: result.sources },
      ]);
      notifySessionUpdated();
    } catch (error: unknown) {
      // 목업은 실패하지 않지만 실 API(명세 15번)는 4xx·5xx 를 냅니다. catch 가 없으면
      // 질문만 남고 답변도 오류도 없는 상태로 끝나서 사용자가 원인을 알 수 없습니다.
      toast.error(error instanceof Error ? error.message : '답변을 가져오지 못했어요.');
    } finally {
      endChatRequest(requestId);
      setPending(false);
    }
  }

  function handleSend() {
    void sendMessage(draft);
  }

  function handleTabChange(key: TabKey) {
    if (key === 'chat') return;
    const routes: Record<TabKey, string> = {
      home: '/home',
      medication: '/medications',
      supplement: '/supplements',
      chat: '/chat',
      my: '/my',
    };
    navigate(routes[key]);
  }

  function openSession(sessionId: number) {
    setNewChatRequested(false);
    setMessages([]);
    setConversationId(null);
    setDraft('');
    setHistoryError(null);
    setSessionListError(null);
    setHistoryLoading(true);
    selectSession(sessionId);
    setView('loading');
  }

  function startNewChat() {
    startNewSession();
    setNewChatRequested(true);
    setMessages([]);
    setConversationId(null);
    setDraft('');
    setHistoryError(null);
    setSessionListError(null);
    setHistoryLoading(false);
    setSelectionMode(false);
    setSelectedSessionIds(new Set());
    setView('room');
  }

  function handleRoomBack() {
    if (historyLoader !== undefined) {
      navigate(-1);
      return;
    }

    if (
      sessions.length > 0
      || activeSessionId !== null
      || conversationId !== null
    ) {
      startNewSession();
      setNewChatRequested(false);
      setMessages([]);
      setConversationId(null);
      setDraft('');
      setHistoryError(null);
      setSessionListError(null);
      setSelectionMode(false);
      setSelectedSessionIds(new Set());
      setHistoryLoading(true);
      setView('loading');
      setSessionListReloadKey((current) => current + 1);
      return;
    }

    navigate(-1);
  }

  function toggleSelectionMode() {
    setSelectionMode((current) => {
      if (current) setSelectedSessionIds(new Set());
      return !current;
    });
  }

  function toggleSession(sessionId: number) {
    setSelectedSessionIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  async function confirmDelete() {
    if (selectedSessionIds.size === 0 || deleting) return;
    const deletingIds = [...selectedSessionIds];
    setDeleting(true);
    try {
      await sessionDeleter(deletingIds);
      const deleted = new Set(deletingIds);
      const remaining = sessions.filter((session) => !deleted.has(session.sessionId));
      setSessions(remaining);
      setDeleteDialogOpen(false);
      setSelectionMode(false);
      setSelectedSessionIds(new Set());
      if (activeSessionId !== null && deleted.has(activeSessionId)) startNewSession();
      if (remaining.length === 0) {
        startNewSession();
        setNewChatRequested(true);
        setMessages([]);
        setConversationId(null);
        setView('room');
      }
    } catch (error: unknown) {
      setDeleteDialogOpen(false);
      setDeleteError(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.');
    } finally {
      setDeleting(false);
    }
  }

  if (view === 'list') {
    return (
      <>
        <ChatSessionList
          sessions={sessions}
          selectionMode={selectionMode}
          selectedSessionIds={selectedSessionIds}
          onBack={() => navigate(-1)}
          onDeleteSelected={() => setDeleteDialogOpen(true)}
          onNewChat={startNewChat}
          onOpen={openSession}
          onTabChange={handleTabChange}
          onToggleSelectionMode={toggleSelectionMode}
          onToggleSession={toggleSession}
        />
        <ChatDeleteDialog
          open={deleteDialogOpen}
          count={selectedSessionIds.size}
          deleting={deleting}
          onCancel={() => setDeleteDialogOpen(false)}
          onConfirm={() => void confirmDelete()}
        />
        <ErrorDialog
          open={deleteError !== null}
          title="대화를 삭제하지 못했어요"
          message={deleteError ?? ''}
          onRetry={() => {
            setDeleteError(null);
            void confirmDelete();
          }}
          secondaryLabel="닫기"
          onSecondary={() => setDeleteError(null)}
        />
      </>
    );
  }

  const composerDisabled = chatRequestPending || pending || historyLoading || view === 'loading';

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="AI 상담" onBack={handleRoomBack} />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        {historyLoading ? (
          <div
            role="status"
            aria-label="대화 이력 불러오는 중"
            className="min-h-20 animate-pulse rounded-card bg-muted-bg"
          />
        ) : (
          <>
            {historyError !== null && (
              <Card title="대화 이력을 불러오지 못했어요.">{historyError}</Card>
            )}
            {sessionListError !== null && (
              <Card title="대화 목록을 불러오지 못했어요.">
                <div className="flex flex-col gap-3">
                  <p>{sessionListError}</p>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setView('loading');
                      setSessionListReloadKey((current) => current + 1);
                    }}
                  >
                    다시 시도
                  </Button>
                </div>
              </Card>
            )}
            {messages.length === 0 && (
              <ChatStartGuide
                pending={chatRequestPending || pending}
                onQuestion={(question) => void sendMessage(question)}
              />
            )}
          </>
        )}

        {messages.map((message, index) =>
          message.role === 'user' ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[80%] rounded-card bg-primary px-3.5 py-2.5 text-base break-words text-card">
                {message.text}
              </p>
            </div>
          ) : (
            <div key={index} className="flex justify-start">
              <div className="flex max-w-[80%] flex-col gap-2 rounded-card bg-muted-bg px-3.5 py-2.5">
                <p className="whitespace-pre-wrap text-base break-words text-foreground">
                  {message.text}
                </p>
                {message.sources.length > 0 ? (
                  <SourceList sources={message.sources} />
                ) : (
                  // 근거가 없는데 있는 것처럼 보이면 안 됩니다. 명시적으로 알립니다.
                  <p className="border-t border-border pt-2 text-sm text-muted-foreground">
                    이 답변은 일반적인 안내이며 등록하신 약에 근거하지 않았습니다.
                  </p>
                )}
              </div>
            </div>
          ),
        )}

        {(chatRequestPending || pending) && (
          <div className="flex justify-start">
            <p className="max-w-[80%] rounded-card bg-muted-bg px-3.5 py-2.5 text-base text-muted-foreground">
              답변을 준비하고 있어요...
            </p>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* 입력 영역 — BottomTabbar 위에 붙습니다. */}
      <div className="flex shrink-0 items-start gap-2 border-t border-border bg-card px-page-x py-3">
        <Input
          aria-label="질문 입력"
          value={draft}
          disabled={composerDisabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={composerDisabled ? '답변을 기다리는 중이에요' : '궁금한 것을 입력하세요'}
        />
        <Button
          fullWidth={false}
          className="shrink-0 px-5"
          disabled={composerDisabled || draft.trim().length === 0}
          onClick={handleSend}
        >
          보내기
        </Button>
      </div>

      <BottomTabbar active="chat" onChange={handleTabChange} className="border-t border-border" />
    </div>
  );
}
