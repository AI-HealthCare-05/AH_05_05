import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';

interface MedicationPeriodCalendarProps {
  label: string;
  value: string;
  min: string;
  max: string;
  onSelect: (date: string) => void;
  onClose: () => void;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

function parseLocalIsoDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
    ? date
    : null;
}

function localIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function monthStart(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function shiftMonth(date: Date, offset: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + offset, 1);
}

function monthIntersectsRange(month: Date, min: string, max: string): boolean {
  const first = localIsoDate(monthStart(month));
  const last = localIsoDate(new Date(month.getFullYear(), month.getMonth() + 1, 0));
  return last >= min && first <= max;
}

function koreanDateLabel(date: Date): string {
  return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일`;
}

export function MedicationPeriodCalendar({
  label,
  value,
  min,
  max,
  onSelect,
  onClose,
}: MedicationPeriodCalendarProps) {
  const calendarRef = useRef<HTMLElement>(null);
  const selectedDate = parseLocalIsoDate(value);
  const maxDate = parseLocalIsoDate(max) ?? new Date();
  const [visibleMonth, setVisibleMonth] = useState(() => monthStart(selectedDate ?? maxDate));
  const previousMonth = shiftMonth(visibleMonth, -1);
  const nextMonth = shiftMonth(visibleMonth, 1);
  const firstWeekday = visibleMonth.getDay();
  const daysInMonth = new Date(
    visibleMonth.getFullYear(),
    visibleMonth.getMonth() + 1,
    0,
  ).getDate();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      calendarRef.current?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <section
      ref={calendarRef}
      role="region"
      aria-label={`${label} 달력`}
      className="mx-auto w-full max-w-[328px] rounded-card border border-border bg-card p-3 shadow-card"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="이전 달"
          disabled={!monthIntersectsRange(previousMonth, min, max)}
          className="flex size-touch shrink-0 items-center justify-center rounded-input text-foreground hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground"
          onClick={() => setVisibleMonth(previousMonth)}
        >
          <ChevronLeft aria-hidden className="size-5" />
        </button>
        <h3 className="text-base font-bold text-foreground" aria-live="polite">
          {visibleMonth.getFullYear()}년 {visibleMonth.getMonth() + 1}월
        </h3>
        <div className="flex shrink-0 items-center">
          <button
            type="button"
            aria-label="다음 달"
            disabled={!monthIntersectsRange(nextMonth, min, max)}
            className="flex size-touch items-center justify-center rounded-input text-foreground hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground"
            onClick={() => setVisibleMonth(nextMonth)}
          >
            <ChevronRight aria-hidden className="size-5" />
          </button>
          <button
            type="button"
            aria-label="달력 닫기"
            className="flex size-touch items-center justify-center rounded-input text-muted-foreground hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={onClose}
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center" aria-hidden>
        {WEEKDAYS.map((weekday) => (
          <span key={weekday} className="py-1 text-xs font-bold text-muted-foreground">
            {weekday}
          </span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: firstWeekday }, (_, index) => (
          <span key={`blank-${index}`} aria-hidden />
        ))}
        {Array.from({ length: daysInMonth }, (_, index) => {
          const date = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), index + 1);
          const isoDate = localIsoDate(date);
          const selected = isoDate === value;
          return (
            <button
              key={isoDate}
              type="button"
              aria-label={koreanDateLabel(date)}
              aria-pressed={selected}
              disabled={isoDate < min || isoDate > max}
              className={`aspect-square min-w-0 rounded-input text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground ${
                selected
                  ? 'bg-primary text-primary-foreground'
                  : 'text-foreground hover:bg-primary-bg'
              }`}
              onClick={() => onSelect(isoDate)}
            >
              {index + 1}
            </button>
          );
        })}
      </div>
    </section>
  );
}
