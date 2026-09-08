import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { FileText } from 'lucide-react';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { generateIntakeReport } from '@/entities/intake-report/api';
import type { IntakeReport } from '@/entities/intake-report/types';
import { ApiError, getAuthGeneration } from '@/shared/api/client';
import { Button, Header } from '@/shared/ui';
const IntakeReportBody = lazy(() => import('./IntakeReportBody').then(module => ({ default: module.IntakeReportBody })));

export function AiReportRequestPage() {
  const [params] = useSearchParams();
  const { principalKey } = useSession();
  const source = params.get('source');
  if (source !== 'medications' && source !== 'supplements') return <Navigate to="/reports" replace />;
  return <ReportRequest key={`${principalKey}:${source}`} source={source} />;
}

function ReportRequest({ source }: { source: 'medications' | 'supplements' }) {
  const navigate = useNavigate();
  const [report, setReport] = useState<IntakeReport | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef(0);
  const inFlight = useRef(false);
  useEffect(() => () => { activeRequest.current += 1; }, []);

  async function generate() {
    if (inFlight.current) return;
    inFlight.current = true;
    const requestId = ++activeRequest.current;
    const authGeneration = getAuthGeneration();
    const current = () => requestId === activeRequest.current && authGeneration === getAuthGeneration();
    setPending(true);
    setError(null);
    setReport(null);
    try {
      const result = await generateIntakeReport();
      if (current()) setReport(result);
    } catch (cause) {
      if (current()) setError(cause instanceof ApiError ? cause.message : '보고서를 불러오지 못했어요. 연결 상태를 확인하고 다시 시도해주세요.');
    } finally {
      if (current()) { setPending(false); inFlight.current = false; }
    }
  }

  const label = source === 'medications' ? '복약' : '영양제';
  return <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
    <Header title="복용 정보 AI 보고서" onBack={() => navigate(`/${source}`)} />
    <main className="flex min-w-0 flex-1 flex-col gap-5 px-page-x py-5">
      {!report && <section className="space-y-4 rounded-card bg-card p-5 shadow-card">
        <FileText aria-hidden className="size-8 text-primary" />
        <h2 className="text-xl font-bold text-foreground">현재 복용 정보를 함께 살펴봐요</h2>
        <p className="break-keep text-sm leading-relaxed text-muted-foreground">등록한 복용약과 영양제를 함께 분석해요. 생성하기를 누르면 현재 복용 정보를 바탕으로 AI 보고서를 요청해요.</p>
        <p className="text-sm text-muted-foreground">보고서는 저장되지 않아요.</p>
      </section>}
      {pending && <p role="status" className="text-sm text-primary">보고서를 생성하고 있어요. 최대 30초 정도 걸릴 수 있어요.</p>}
      {error && <p role="alert" className="rounded-card border border-border bg-card p-4 text-sm text-foreground">{error}</p>}
      {report?.reportStatus === 'EMPTY' ? <section className="space-y-4 rounded-card bg-card p-5 shadow-card">
        <h2 className="text-lg font-bold">분석할 복용 정보가 없어요</h2>
        <p className="text-sm text-muted-foreground">현재 복용 중인 약이나 영양제를 등록한 뒤 다시 요청해주세요.</p>
        <Button onClick={() => navigate(`/${source}`)}>{label} 관리로 이동</Button>
      </section> : report ? <Suspense fallback={<p role="status" className="text-sm text-primary">보고서 화면을 준비하고 있어요.</p>}><IntakeReportBody report={report} /></Suspense> : null}
      <div className="mt-auto flex flex-col gap-3 pt-4 pb-3">
        <Button onClick={() => void generate()} disabled={pending}>{pending ? '보고서 생성 중' : error ? '다시 시도' : report ? '새 보고서 생성하기' : '보고서 생성하기'}</Button>
        <Button variant="secondary" onClick={() => navigate(`/${source}`)}>{source === 'medications' ? '복약으로 돌아가기' : '영양제로 돌아가기'}</Button>
      </div>
    </main>
  </div>;
}
