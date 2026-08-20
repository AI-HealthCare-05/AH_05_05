import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { BottomTabbar, Button, Header, Input, type TabKey } from '@/shared/ui';
import { sendChat, type ChatMessage } from '@/entities/chat';
import { SourceList } from './SourceList';

/**
 * REQ-CHAT-001 · 화면 17 AI 상담 — 공공 근거를 보여주는 화면.
 *
 * 이번 범위에서 잘라낸 것: 대화 이력 조회(명세 16), 세션 목록·삭제, 질문 재전송·수정,
 * SSE 스트리밍. 출처 표시가 유일한 필수 기능입니다.
 *
 * 말풍선은 Card를 재사용하지 않고 직접 만들었습니다 — 정렬과 최대폭 규칙이 다릅니다.
 */
interface ChatLocationState {
  recordId?: number;
}

export function ChatPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ChatLocationState | null) ?? {};
  const recordId = state.recordId ?? null;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 새 메시지·대기 상태가 생기면 맨 아래로 내립니다.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, pending]);

  async function handleSend() {
    const message = draft.trim();
    if (!message || pending) return;

    setMessages((prev) => [...prev, { role: 'user', text: message, sources: [] }]);
    setDraft('');
    setPending(true);
    try {
      const result = await sendChat({ recordId, message, conversationId });
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

  function handleTabChange(key: TabKey) {
    if (key === 'chat') return;
    if (key === 'life') {
      navigate('/dev/life-guide');
      return;
    }
    toast('이 탭 화면은 아직 구현 전입니다.');
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="AI 상담" />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        {messages.length === 0 && !pending && (
          <p className="text-sm text-muted-foreground">
            복약·회복에 대해 궁금한 것을 물어보세요. 답변에는 근거를 함께 보여드립니다.
          </p>
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
                <p className="text-base break-words text-foreground">{message.text}</p>
                {message.sources.length > 0 ? (
                  <SourceList sources={message.sources} />
                ) : (
                  // 근거가 없는데 있는 것처럼 보이면 안 됩니다. 명시적으로 알립니다.
                  <p className="border-t border-border pt-2 text-sm text-muted-foreground">
                    이 답변은 일반적인 안내이며 개인 진료기록에 근거하지 않았습니다.
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
              void handleSend();
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
