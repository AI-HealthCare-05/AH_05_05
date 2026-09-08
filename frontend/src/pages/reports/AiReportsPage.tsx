import { FileText } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Button, Header } from '@/shared/ui';

/** Report persistence is not connected yet; do not present mock records as user data. */
export function AiReportsPage() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="AI 보고서 모아보기" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col gap-5 px-page-x py-5">
        <section className="flex flex-col items-center gap-3 rounded-card bg-card px-5 py-8 text-center shadow-card">
          <span className="flex size-14 items-center justify-center rounded-pill bg-primary-bg text-primary">
            <FileText aria-hidden className="size-6" />
          </span>
          <h2 className="text-lg font-bold text-foreground">아직 받은 AI 보고서가 없어요</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            복약과 영양제 보고서를 한곳에서 확인할 수 있도록 준비하고 있어요.
          </p>
        </section>
        <Button variant="secondary" onClick={() => navigate('/my')}>
          마이페이지로 돌아가기
        </Button>
      </main>
    </div>
  );
}
