import { FileText } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Button, Header } from '@/shared/ui';

/** Reports are intentionally transient; this is an entry page, not a history list. */
export function AiReportsPage() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="AI 보고서" onBack={() => navigate('/my')} />
      <main className="flex flex-1 flex-col gap-5 px-page-x py-5">
        <section className="flex flex-col items-center gap-3 rounded-card bg-card px-5 py-8 text-center shadow-card">
          <span className="flex size-14 items-center justify-center rounded-pill bg-primary-bg text-primary">
            <FileText aria-hidden className="size-6" />
          </span>
          <h2 className="text-lg font-bold text-foreground">현재 복용 정보를 살펴봐요</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            현재 복용 중인 약과 영양제를 함께 분석해요. 필요할 때 새 보고서를 요청해주세요.
          </p>
          <p className="text-sm text-muted-foreground">보고서는 저장되지 않아요.</p>
        </section>
        <Button onClick={() => navigate('/reports/new?source=medications')}>AI 보고서 받기</Button>
        <Button variant="secondary" onClick={() => navigate('/my')}>
          마이페이지로 돌아가기
        </Button>
      </main>
    </div>
  );
}
