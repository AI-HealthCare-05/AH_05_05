const GUIDE_ITEMS = [
  '복용 중인 약의 효능 · 부작용 · 주의사항',
  '영양제 성분의 기능과 섭취 주의사항',
  '약과 약, 약과 영양제를 함께 먹을 때의 주의점',
  '임신 · 수유 · 고령자 · 간신장 질환자 주의사항',
] as const;

const FREQUENT_QUESTIONS = [
  '지금 먹는 약을 같이 먹어도 되나요?',
  '이 약은 왜 먹는 건가요?',
  '영양제와 같이 먹어도 괜찮나요?',
  '약을 먹다가 놓쳤으면 어떻게 하나요?',
] as const;

interface ChatStartGuideProps {
  pending: boolean;
  onQuestion: (question: string) => void;
}

/** 대화 이력이 없을 때만 그리는 정적 안내입니다. 질문 버튼만 기존 전송 경계를 사용합니다. */
export function ChatStartGuide({ pending, onQuestion }: ChatStartGuideProps) {
  return (
    <div className="flex flex-col gap-4">
      <section
        aria-label="챗봇 시작 가이드"
        className="flex flex-col gap-3 rounded-card bg-card p-4 shadow-card"
      >
        <div className="flex items-center gap-3">
          <img
            src="/images/rxvita-mark-256.png"
            alt=""
            aria-hidden
            className="size-16 shrink-0"
            width={256}
            height={256}
          />
          <h2 className="text-lg font-bold text-foreground">이 챗봇에서 확인할 수 있어요</h2>
        </div>
        <ul className="flex flex-col gap-1.5 text-sm leading-5 text-foreground">
          {GUIDE_ITEMS.map((item) => (
            <li key={item} className="flex items-start gap-2">
              <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-pill bg-muted-foreground" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <p className="border-t border-border pt-3 text-sm text-muted-foreground">
          답변에는 근거 자료의 출처를 함께 보여드려요
        </p>
      </section>

      <section aria-label="자주 묻는 질문" className="flex flex-col gap-2">
        <h2 className="text-base font-bold text-foreground">이런 걸 물어보세요</h2>
        <div className="flex flex-col gap-2">
          {FREQUENT_QUESTIONS.map((question) => (
            <button
              key={question}
              type="button"
              disabled={pending}
              className="min-h-touch rounded-pill border border-border bg-card px-4 py-2 text-left text-sm font-bold text-foreground transition-colors disabled:cursor-not-allowed disabled:text-disabled-foreground"
              onClick={() => onQuestion(question)}
            >
              {question}
            </button>
          ))}
        </div>
      </section>

      <div className="flex flex-col gap-0.5 text-unit leading-4 text-muted-foreground">
        <p>제공되는 내용은 참고 정보이며 진단이나 처방을 대신하지 않습니다.</p>
        <p>복용 변경이 필요한 경우 의료진 또는 약사와 상담해 주세요.</p>
      </div>
    </div>
  );
}
