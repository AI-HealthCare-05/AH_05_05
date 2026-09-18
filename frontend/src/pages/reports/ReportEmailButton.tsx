import { useEffect, useRef, useState } from 'react';
import { emailIntakeReport, getIntakeReportEmailJob } from '@/entities/intake-report/api';
import type { IntakeReportEmailJob } from '@/entities/intake-report/types';
import { ApiError, getAuthGeneration } from '@/shared/api/client';
import { Button, Input } from '@/shared/ui';
import { Dialog, DialogContent, DialogTitle, DialogHeader, DialogFooter, DialogDescription } from '@/shared/ui/dialog';

const terminal = (job: IntakeReportEmailJob) => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(job.status);

export function ReportEmailButton({ emailToken, onRegenerate, demoRecipient = false }: { emailToken?: string | null; onRegenerate: () => void; demoRecipient?: boolean }) {
  const [recipientOpen, setRecipientOpen] = useState(false);
  const [recipient, setRecipient] = useState('');
  const [job, setJob] = useState<IntakeReportEmailJob | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  useEffect(() => {
    if (!job || terminal(job) || !polling) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const generation = getAuthGeneration();
    const current = () => !cancelled && generation === getAuthGeneration();
    async function poll() {
      try {
        const result = await getIntakeReportEmailJob(job!.jobId);
        if (!current()) return;
        setJob(result);
        if (terminal(result)) return;
        if (++attempts >= 30) { setPolling(false); return; }
        timer = setTimeout(() => void poll(), 2000);
      } catch {
        if (current()) {
          setError('발송 상태를 확인하지 못했어요. 잠시 후 상태 확인을 눌러주세요.');
          setPolling(false);
        }
      }
    }
    timer = setTimeout(() => void poll(), 2000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job?.jobId, polling]);

  async function send() {
    if (!emailToken || inFlight.current || job) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    const generation = getAuthGeneration();
    try {
      const result = await emailIntakeReport(emailToken, demoRecipient ? recipient.trim() : undefined);
      if (mounted.current && generation === getAuthGeneration()) {
        setJob(result);
        setRecipientOpen(false);
      }
    } catch (cause) {
      if (mounted.current && generation === getAuthGeneration()) {
        setError(cause instanceof ApiError ? cause.message : '발송 요청을 확인하지 못했어요. 다시 눌러도 같은 보고서는 중복 접수되지 않아요.');
      }
    } finally {
      inFlight.current = false;
      if (mounted.current && generation === getAuthGeneration()) setPending(false);
    }
  }

  const failed = job?.status === 'FAILED' || job?.status === 'CANCELLED';
  const message = !emailToken ? '이 보고서는 이메일 발송을 사용할 수 없어요. 새 보고서를 생성해주세요.'
    : job?.status === 'COMPLETED' ? '메일 서버로 발송했어요. 받은편지함과 스팸함을 확인해주세요.'
    : failed ? '이메일을 발송하지 못했어요. 잠시 후 새 보고서를 생성해 다시 요청해주세요.'
    : job ? '발송 요청이 접수됐어요. 아직 발송이 완료되지는 않았어요.'
    : '현재 보고서를 암호화된 HTML 첨부파일로 보내요. 비밀번호는 등록된 생년월일 6자리(YYMMDD)예요. 생성 후 1시간 이내에 요청해주세요.';
  return <>
    <Button onClick={() => demoRecipient ? setRecipientOpen(true) : void send()} disabled={!emailToken || pending || !!job} aria-describedby="report-email-help">
      {pending ? '이메일 요청 중' : job?.status === 'COMPLETED' ? '이메일 발송 완료' : job && !failed ? '이메일 발송 처리 중' : '이메일로 받기'}
    </Button>
    <p id="report-email-help" role={failed ? 'alert' : job ? 'status' : undefined} className="text-center text-xs leading-relaxed text-muted-foreground">{message}</p>
    {error && <p role="alert" className="text-center text-sm text-foreground">{error}</p>}
    {(!emailToken || failed || (error && !job)) && <Button variant="secondary" onClick={onRegenerate}>새 보고서 생성하기</Button>}
    {job && !terminal(job) && !polling && <Button variant="secondary" onClick={() => { setError(null); setPolling(true); }}>발송 상태 확인</Button>}
    <Dialog open={recipientOpen} onOpenChange={open => { if (!pending) setRecipientOpen(open); }}>
      <DialogContent showCloseButton={!pending}>
        <DialogHeader><DialogTitle>보고서 이메일 발송</DialogTitle>
          <DialogDescription>공유 데모 계정의 보고서를 입력한 주소로 발송합니다.</DialogDescription>
        </DialogHeader>
        <form onSubmit={event => { event.preventDefault(); void send(); }} className="space-y-4">
          <Input label="[데모버전] 이메일 받을 주소를 입력하세요:" type="email" required maxLength={254}
            value={recipient} disabled={pending} onChange={event => setRecipient(event.target.value)} />
          {error && <p role="alert">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="secondary" disabled={pending} onClick={() => setRecipientOpen(false)}>취소</Button>
            <Button type="submit" disabled={pending || !recipient.trim()}>{pending ? '발송 요청 중' : '확인'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </>;
}
