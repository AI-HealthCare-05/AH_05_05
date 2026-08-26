import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { BottomTabbar, Button, Card, Header, Input, type TabKey } from '@/shared/ui';
import {
  sendChat,
  type ChatMessage,
  type SendChatPayload,
  type SendChatResult,
} from '@/entities/chat';
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

interface ChatPageProps {
  historyLoader?: ChatHistoryLoader;
  chatSender?: ChatSender;
}

export function ChatPage({
  historyLoader,
  chatSender = sendChat,
}: ChatPageProps = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ChatLocationState | null) ?? {};
  const recordId = state.recordId ?? null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(historyLoader !== undefined);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (historyLoader === undefined) {
      setHistoryLoading(false);
      setHistoryError(null);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    setHistoryError(null);
    historyLoader()
      .then((history) => {
        if (!cancelled) setMessages(history);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessages([]);
          setHistoryError(
            error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [historyLoader]);

  // 새 메시지·대기 상태가 생기면 맨 아래로 내립니다.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, pending]);

  async function sendMessage(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || pending) return;

    setMessages((prev) => [...prev, { role: 'user', text: message, sources: [] }]);
    setDraft('');
    setPending(true);
    try {
      const result = await chatSender({
        requestId: crypto.randomUUID(),
        recordId,
        message,
        conversationId,
      });
      setConversationId(result.conversationId);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: result.answer, sources: result.sources },
      ]);
    } catch (error: unknown) {
      // 목업은 실패하지 않지만 실 API(명세 15번)는 4xx·5xx 를 냅니다. catch 가 없으면
      // 질문만 남고 답변도 오류도 없는 상태로 끝나서 사용자가 원인을 알 수 없습니다.
      toast.error(error instanceof Error ? error.message : '답변을 가져오지 못했어요.');
    } finally {
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

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="AI 상담" onBack={() => navigate(-1)} />

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
            {messages.length === 0 && (
              <ChatStartGuide
                pending={pending}
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

        {pending && (
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
          disabled={pending}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={pending ? '답변을 기다리는 중이에요' : '궁금한 것을 입력하세요'}
        />
        <Button
          fullWidth={false}
          className="shrink-0 px-5"
          disabled={pending || draft.trim().length === 0}
          onClick={handleSend}
        >
          보내기
        </Button>
      </div>

      <BottomTabbar active="chat" onChange={handleTabChange} className="border-t border-border" />
    </div>
  );
}
