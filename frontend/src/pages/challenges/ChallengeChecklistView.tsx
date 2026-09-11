import { Link, useLocation } from 'react-router';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import type { ChallengeParticipation } from '@/features/challenges';

export interface ChallengeChecklistViewProps {
  participation: ChallengeParticipation;
}

export function ChallengeChecklistView({ participation }: ChallengeChecklistViewProps) {
  const { pathname } = useLocation();
  const base = pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const checklist = participation.checklist ?? [];
  const requiredItems = checklist.filter((item) => item.available);
  const completed = requiredItems.filter((item) => item.checked).length;

  return (
    <section aria-labelledby="challenge-checklist-title" className="flex flex-col gap-3">
      {participation.kind === 'review' && (
        <div className="rounded-card bg-card p-5 shadow-card">
          <h2 className="text-base font-bold text-foreground">이번 주 기록</h2>
          <p className="mt-1 text-xs text-primary">09.07 ~ 09.13</p>
          <p className="mt-3 whitespace-pre-line text-sm leading-6 text-muted-foreground">
            {'복약 기록 6회\n영양제 기록 5회\n복약 메모 없음'}
          </p>
        </div>
      )}
      {participation.kind === 'visit' && (
        <>
          <div className="rounded-card bg-card p-5 shadow-card">
            <h2 className="text-base font-bold text-foreground">예정된 진료</h2>
            <p className="mt-1 text-xs text-primary">09.21 월요일</p>
            <p className="mt-3 text-sm text-muted-foreground">오후 2:00 · 내과 · 등록한 진료 일정 기준</p>
          </div>
          <div className="rounded-card bg-card p-5 shadow-card">
            <h2 className="text-base font-bold text-foreground">기록이 없어도 괜찮아요</h2>
            <p className="mt-1 text-xs text-primary">진료 일정이 있으면 참여 가능</p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              약·영양제·메모가 없으면 확인할 기록이 없는 상태로 안내해요.
            </p>
          </div>
        </>
      )}
      <div className="flex items-center justify-between gap-3">
        <h2 id="challenge-checklist-title" className="text-lg font-bold text-foreground">
          확인할 기록
        </h2>
        <p className="text-xs font-bold text-primary">
          {completed} / {requiredItems.length}개 확인
        </p>
      </div>
      <div className="overflow-hidden rounded-card bg-card">
        {checklist.map((item) => (
          <Link
            key={item.id}
            to={`${base}/participations/${participation.id}/records/${item.id}`}
            data-checked={item.checked}
            className="flex min-h-[56px] items-center gap-3 border-b border-border px-4 py-2 last:border-b-0"
          >
            <span
              aria-hidden="true"
              className={`flex size-5 shrink-0 items-center justify-center rounded border text-xs font-bold ${item.checked ? 'border-primary bg-primary text-card' : 'border-input bg-card'}`}
            >
              {item.checked ? '✓' : ''}
            </span>
            <span className="flex-1 text-sm font-bold text-foreground">{item.label}</span>
            <span className="sr-only">{item.checked ? '확인 완료' : '미확인'}</span>
            {!item.available && <span className="text-xs text-tertiary-foreground">기록 없음</span>}
            <DrawnChevron direction="right" className="size-5 text-tertiary-foreground" />
          </Link>
        ))}
      </div>
      {requiredItems.length > 0 && completed === requiredItems.length && (
        <p role="status" className="rounded-card bg-success-bg px-4 py-3 text-sm font-bold text-success-strong">
          필요한 기록을 모두 확인했어요.
        </p>
      )}
    </section>
  );
}
