import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { Check } from 'lucide-react';

import type { CustomChallengeOccurrence, CustomChallengeParticipation } from '@/entities/custom-challenge';
import { cn } from '@/shared/lib/cn';
import { customChallengeDateLabel as dateLabel, seoulDate } from './customChallengeDates';
import './custom-challenge-date-strip.css';

const SLOT_LABEL = { MORNING: '아침', LUNCH: '점심', EVENING: '저녁', BEDTIME: '자기전' };
const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary';

function shiftDate(date: string, amount: number) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + amount);
  return value.toISOString().slice(0, 10);
}

function monthDay(date: string) {
  const [, month, day] = date.split('-').map(Number);
  return `${month}월 ${day}일`;
}

/** Server occurrences are read-only. Date navigation never records a dose. */
export function CustomChallengeCalendar({ participation }: { participation: CustomChallengeParticipation }) {
  const today = seoulDate();
  const occurrenceDates = participation.occurrences.map(item => item.scheduledDate).sort();
  const joinedDate = seoulDate(new Date(participation.joinedAt));
  const start = [today, joinedDate, occurrenceDates[0] ?? joinedDate].sort()[0];
  const end = [today, participation.actualEndDate ?? joinedDate, occurrenceDates.at(-1) ?? joinedDate].sort().at(-1)!;
  const [chosenDate, setChosenDate] = useState(today);
  const selectedDate = chosenDate < start ? start : chosenDate > end ? end : chosenDate;
  const stripRef = useRef<HTMLDivElement>(null);
  const dateButtons = useRef(new Map<string, HTMLButtonElement>());
  const selectedDateRef = useRef(selectedDate);
  selectedDateRef.current = selectedDate;
  const identity = useRef(participation.id);
  const scrollFrame = useRef<number | null>(null);
  const gesture = useRef<{ id: number; x: number; y: number } | null>(null);
  const dates: string[] = [];
  for (let date = start; date <= end; date = shiftDate(date, 1)) dates.push(date);
  const targetNames = new Map(participation.targets.map(target => [target.id, target.name]));
  const byDate = new Map<string, CustomChallengeOccurrence[]>();
  for (const occurrence of participation.occurrences) {
    const items = byDate.get(occurrence.scheduledDate) ?? [];
    items.push(occurrence);
    byDate.set(occurrence.scheduledDate, items);
  }
  const selectedRecords = [...(byDate.get(selectedDate) ?? [])].sort((a, b) => a.scheduledAt.localeCompare(b.scheduledAt));
  const completedCount = selectedRecords.filter(item => item.isCompleted).length;
  const allDone = selectedDate <= today && selectedRecords.length > 0 && completedCount === selectedRecords.length;
  const doseLabel = participation.challengeType === 'SUPPLEMENT' ? '영양제를' : '약을';

  function centerDate(date: string, behavior: ScrollBehavior = 'auto') {
    const button = dateButtons.current.get(date);
    const strip = stripRef.current;
    if (!button || !strip) return;
    strip.scrollTo({ left: strip.scrollLeft + button.getBoundingClientRect().left - strip.getBoundingClientRect().left
      - (strip.clientWidth - button.offsetWidth) / 2, behavior });
  }

  useLayoutEffect(() => {
    const date = identity.current === participation.id ? selectedDateRef.current : today;
    identity.current = participation.id;
    setChosenDate(date);
    centerDate(date);
    // Selection itself must never restart native scrolling. A refresh with the
    // same bounds keeps the viewed day, while a different challenge starts today.
  }, [participation.id, start, end, today]);

  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    let width = strip.clientWidth;
    const observer = new ResizeObserver(() => {
      if (width === strip.clientWidth) return;
      width = strip.clientWidth;
      centerDate(selectedDateRef.current);
    });
    observer.observe(strip);
    return () => {
      observer.disconnect();
      if (scrollFrame.current !== null) cancelAnimationFrame(scrollFrame.current);
    };
  }, []);

  function syncCenteredDate() {
    if (scrollFrame.current !== null) return;
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = null;
      const strip = stripRef.current;
      if (!strip) return;
      const center = strip.getBoundingClientRect().left + strip.clientWidth / 2;
      let nearest = selectedDateRef.current;
      let distance = Infinity;
      dateButtons.current.forEach((button, date) => {
        const rect = button.getBoundingClientRect();
        const delta = Math.abs(rect.left + rect.width / 2 - center);
        if (delta < distance) { distance = delta; nearest = date; }
      });
      setChosenDate(nearest);
    });
  }

  function selectDate(date: string, keyboard = false) {
    const next = date < start ? start : date > end ? end : date;
    if (keyboard) dateButtons.current.get(next)?.focus({ preventScroll: true });
    centerDate(next, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth');
  }

  function navigateWithKeyboard(event: KeyboardEvent<HTMLButtonElement>) {
    const focused = event.currentTarget.dataset.date ?? selectedDate;
    const next = event.key === 'ArrowLeft' ? shiftDate(focused, -1)
      : event.key === 'ArrowRight' ? shiftDate(focused, 1)
      : event.key === 'Home' ? start : event.key === 'End' ? end : null;
    if (!next) return;
    event.preventDefault();
    selectDate(next, true);
  }

  function startSwipe(event: PointerEvent<HTMLElement>) {
    if (!event.isPrimary || event.pointerType === 'mouse') { gesture.current = null; return; }
    gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
    if (event.nativeEvent.isTrusted) event.currentTarget.setPointerCapture(event.pointerId);
  }

  function finishSwipe(event: PointerEvent<HTMLElement>) {
    const from = gesture.current;
    gesture.current = null;
    if (!from || from.id !== event.pointerId) return;
    const dx = event.clientX - from.x;
    const dy = event.clientY - from.y;
    if (Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      selectDate(shiftDate(selectedDate, dx < 0 ? 1 : -1));
    }
  }

  return (
    <section aria-labelledby="custom-calendar-title" className="min-w-0 rounded-card bg-card p-4 shadow-card">
      <h2 id="custom-calendar-title" className="sr-only">챌린지 달력</h2>
        <div className="mb-3 mt-2 text-center">
          <div aria-live="polite" aria-atomic="true" className="min-w-0">
            <p className="text-caption text-muted-foreground">{selectedDate.slice(0, 4)}년</p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <h3 id="custom-selected-date-title" className="text-2xl font-bold tracking-tight">{monthDay(selectedDate)}</h3>
              {selectedDate === today && <span className="rounded-pill bg-primary-bg px-2 py-0.5 text-caption font-bold text-primary">오늘</span>}
            </div>
          </div>
        </div>
        <div ref={stripRef} role="group" aria-label="챌린지 날짜 선택" onScroll={syncCenteredDate} className="custom-challenge-date-strip">
          {dates.map(date => {
            const records = byDate.get(date) ?? [];
            const completed = records.filter(item => item.isCompleted).length;
            const done = records.length > 0 && completed === records.length;
            const summary = !records.length ? '목표 없음' : done ? '모두 완료' : date > today ? `예정 ${records.length}회` : `${completed}/${records.length} 완료`;
            const selected = date === selectedDate;
            return <button
              key={date} ref={button => { if (button) dateButtons.current.set(date, button); else dateButtons.current.delete(date); }}
              type="button" data-date={date} tabIndex={selected ? 0 : -1}
              aria-label={`${dateLabel(date)}, ${summary}${date === today ? ', 오늘' : ''}`}
              aria-pressed={selected} aria-current={date === today ? 'date' : undefined}
              onClick={() => selectDate(date)} onKeyDown={navigateWithKeyboard}
              className={cn('custom-challenge-date-hit', FOCUS)}
            >
              <span aria-hidden="true" className={cn('custom-challenge-date-square border border-border', done ? 'bg-primary' : 'bg-card')} />
            </button>;
          })}
        </div>
        <section aria-label="날짜별 복용 기록" aria-describedby="custom-date-navigation-hint" className="mt-4 min-w-0 touch-pan-y"
          onPointerDown={startSwipe} onPointerUp={finishSwipe} onPointerCancel={() => { gesture.current = null; }}>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h4 className="text-sm font-bold">복용 기록</h4>
            <p className="text-caption text-muted-foreground">{completedCount} / {selectedRecords.length}회 완료</p>
          </div>
          {allDone && <div role="status" className="mb-4 flex flex-col items-center gap-3 rounded-card bg-primary-bg px-4 py-6 text-center text-primary">
            <span className="flex size-16 items-center justify-center rounded-pill bg-primary text-primary-foreground shadow-card"><Check size={34} strokeWidth={3} aria-hidden="true" /></span>
            <p className="text-base font-bold">{selectedDate === today ? '오늘' : monthDay(selectedDate)} 먹을 {doseLabel} 다 먹었어요!</p>
          </div>}
          {selectedRecords.length === 0 ? <p className="rounded-card bg-muted-bg px-4 py-6 text-sm text-muted-foreground">이날은 목표 기록이 없어요.</p> : <ul aria-label="선택한 날짜의 복용 기록" className="flex flex-col gap-3">
            {selectedRecords.map(occurrence => <li key={occurrence.id} className="flex min-w-0 items-center gap-3 rounded-card border border-border bg-card p-4">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <p className="text-sm font-bold">{SLOT_LABEL[occurrence.slot]}</p>
                  <span className={cn('text-caption', occurrence.isCompleted ? 'font-bold text-primary' : 'text-muted-foreground')}>
                    {occurrence.isCompleted ? '완료' : occurrence.scheduledDate < today ? '미완료' : '예정'}
                  </span>
                </div>
                <p className="break-words text-caption leading-5 text-muted-foreground [overflow-wrap:anywhere]">{targetNames.get(occurrence.targetId) ?? '참여 대상'}</p>
              </div>
              <span aria-hidden="true" className={cn('flex size-8 shrink-0 items-center justify-center rounded-pill border-2', occurrence.isCompleted ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card')}>
                {occurrence.isCompleted && <Check size={18} strokeWidth={3} />}
              </span>
            </li>)}
          </ul>}
          <p id="custom-date-navigation-hint" className="mt-4 text-center text-caption text-muted-foreground">기록을 좌우로 밀어 다른 날짜를 확인해요.</p>
        </section>
    </section>
  );
}
