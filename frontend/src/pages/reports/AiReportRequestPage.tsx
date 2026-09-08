import { FileText } from 'lucide-react';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { Button, Header } from '@/shared/ui';

/** UI preparation only. No prompt, patient records or chat request is sent. */
export function AiReportRequestPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const source = searchParams.get('source');
  if (source !== 'medications' && source !== 'supplements') {
    return <Navigate to="/reports" replace />;
  }
  const label = source === 'medications' ? '복약' : '영양제';

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title={`${label} AI 보고서`} onBack={() => navigate(`/${source}`)} />
      <main className="flex flex-1 flex-col gap-5 px-page-x py-5">
        <section className="flex flex-col gap-4 rounded-card bg-card p-5 shadow-card" aria-labelledby="report-preparation-title">
          <span className="flex size-12 items-center justify-center rounded-pill bg-primary-bg text-primary">
            <FileText aria-hidden className="size-6" />
          </span>
          <div>
            <p className="mb-2 text-sm font-bold text-primary">{label} 정보 돌아보기</p>
            <h2 id="report-preparation-title" className="break-keep text-xl font-bold text-foreground">
              보고서 기능을 준비하고 있어요
            </h2>
          </div>
          <p className="break-keep text-sm leading-relaxed text-muted-foreground">
            아직 보고서를 생성하거나 건강정보를 전송하지 않아요.
          </p>
        </section>
        <div className="mt-auto flex flex-col gap-3 pt-6 pb-3">
          <Button disabled>보고서 생성 준비 중</Button>
          <Button variant="secondary" onClick={() => navigate('/reports')}>
            AI 보고서 모아보기
          </Button>
        </div>
      </main>
    </div>
  );
}
