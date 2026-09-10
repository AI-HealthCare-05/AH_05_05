import { useState } from 'react';
import { Check, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';

import type { CustomChallengeOccurrence, CustomChallengeParticipation } from '@/entities/custom-challenge';
import { cn } from '@/shared/lib/cn';
import { customChallengeDateLabel as dateLabel, seoulDate } from './customChallengeDates';

const SLOT_LABEL = { MORNING: '아침', LUNCH: '점심', EVENING: '저녁', BEDTIME: '자기전' };

function shiftMonth(month: string, offset: number) {
  const [year, number] = month.split('-').map(Number);
  return new Date(Date.UTC(year, number - 1 + offset, 1)).toISOString().slice(0, 7);
}

/** Read-only view of server occurrences; selecting a day never records a dose. */
export function CustomChallengeCalendar({ participation }: { participation: CustomChallengeParticipation }) {
  const today = seoulDate();
  const dates = [...new Set(participation.occurrences.map(item => item.scheduledDate))].sort();
  const start = seoulDate(new Date(participation.joinedAt));
  const end = dates.at(-1) ?? participation.actualEndDate ?? start;
  const initialDate = participation.status !== 'ACTIVE' ? end : today < start ? start : today > end ? end : today;
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [month, setMonth] = useState(initialDate.slice(0, 7));
  const [year, monthNumber] = month.split('-').map(Number);
  const offset = new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const targetNames = new Map(participation.targets.map(target => [target.id, target.name]));
  const byDate = new Map<string, CustomChallengeOccurrence[]>();
  for (const occurrence of participation.occurrences) {
    const items = byDate.get(occurrence.scheduledDate) ?? [];
    items.push(occurrence);
    byDate.set(occurrence.scheduledDate, items);
  }
  const selectedRecords = [...(byDate.get(selectedDate) ?? [])].sort((a, b) => a.scheduledAt.localeCompare(b.scheduledAt));

  function changeMonth(amount: number) {
    const next = shiftMonth(month, amount);
    setMonth(next);
    setSelectedDate(dates.find(date => date.startsWith(next)) ?? `${next}-01`);
  }

  return (
    <section aria-labelledby="custom-calendar-title" className="min-w-0 rounded-card bg-card p-4 shadow-card">
      <h2 id="custom-calendar-title" className="text-base font-bold">챌린지 달력</h2>
      {dates.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">예정된 목표 기록이 없어요.</p> : <>
        <div className="my-2 flex items-center justify-between">
          <button type="button" aria-label="이전 달" disabled={month <= start.slice(0, 7)} onClick={() => changeMonth(-1)} className="flex size-11 items-center justify-center rounded-pill text-primary disabled:text-disabled-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
            <ChevronLeft size={20} aria-hidden="true" />
          </button>
          <p aria-live="polite" className="text-sm font-bold">{year}년 {monthNumber}월</p>
          <button type="button" aria-label="다음 달" disabled={month >= end.slice(0, 7)} onClick={() => changeMonth(1)} className="flex size-11 items-center justify-center rounded-pill text-primary disabled:text-disabled-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
            <ChevronRight size={20} aria-hidden="true" />
          </button>
        </div>
        <div className="grid grid-cols-7 gap-x-1 gap-y-1.5 text-center">
          {['일', '월', '화', '수', '목', '금', '토'].map(day => <span key={day} className="py-1 text-caption text-muted-foreground">{day}</span>)}
          {Array.from({ length: offset }, (_, index) => <span key={`empty-${index}`} aria-hidden="true" />)}
          {Array.from({ length: daysInMonth }, (_, index) => {
            const day = index + 1;
            const date = `${month}-${String(day).padStart(2, '0')}`;
            const records = byDate.get(date) ?? [];
            const count = records.length;
            const completed = records.filter(item => item.isCompleted).length;
            const allDone = count > 0 && completed === count;
            const outside = date < start || date > end;
            const future = date > today;
            const summary = outside ? '참여 기간 밖' : !count ? '목표 없음' : allDone ? '모두 완료' : future && !completed ? `예정 ${count}회` : `${completed}/${count} 완료`;
            return <button
              key={date} type="button" disabled={outside || !count}
              aria-label={`${dateLabel(date)}, ${summary}${date === today ? ', 오늘' : ''}`}
              aria-pressed={date === selectedDate} aria-current={date === today ? 'date' : undefined}
              onClick={() => setSelectedDate(date)}
              className={cn('flex min-h-14 min-w-0 flex-col items-center justify-center gap-1 rounded-xl border text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                date === selectedDate ? 'border-primary bg-primary-bg font-bold text-primary' : 'border-transparent text-foreground',
                date === today && 'ring-1 ring-primary',
                (outside || !count) && 'text-disabled-foreground',
              )}
            >
              <span>{day}</span>
              <span aria-hidden="true" className="flex h-4 items-center text-[10px] font-bold leading-none text-primary">
                {allDone ? <Check size={14} strokeWidth={3} /> : count && !outside ? future && !completed ? '•' : `${completed}/${count}` : ''}
              </span>
            </button>;
          })}
        </div>
        <p className="mt-3 text-center text-caption text-muted-foreground">✓ 모두 완료 · 1/3 일부 완료 · • 예정</p>
        <section aria-labelledby="custom-selected-date-title" className="mt-4 border-t border-border pt-4">
          <details key={selectedDate} className="group">
            <summary className="flex min-h-touch cursor-pointer list-none items-center justify-between gap-3 [&::-webkit-details-marker]:hidden">
              <h3 id="custom-selected-date-title" className="text-sm font-bold">{dateLabel(selectedDate)} 기록</h3>
              <span className="flex shrink-0 items-center gap-2 text-caption text-muted-foreground">{selectedRecords.length}개<ChevronDown aria-hidden="true" className="size-4 group-open:rotate-180" /></span>
            </summary>
          {selectedRecords.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">이날은 목표 기록이 없어요.</p> : <ul className="mt-2 divide-y divide-border">
            {selectedRecords.map(occurrence => <li key={occurrence.id} className="flex min-w-0 flex-col gap-2 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-bold">{SLOT_LABEL[occurrence.slot]}</p>
              <span className={cn('shrink-0 rounded-pill px-2 py-1 text-caption', occurrence.isCompleted ? 'bg-primary-bg font-bold text-primary' : 'bg-muted-bg text-muted-foreground')}>
                {occurrence.isCompleted ? '완료' : occurrence.scheduledDate < today ? '미완료' : '예정'}
              </span>
              </div>
              <p className="break-words text-caption text-muted-foreground [overflow-wrap:anywhere]">{targetNames.get(occurrence.targetId) ?? '참여 대상'}</p>
            </li>)}
          </ul>}
          </details>
        </section>
      </>}
    </section>
  );
}
