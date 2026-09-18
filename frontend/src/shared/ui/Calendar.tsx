import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { Button } from './Button';

export function localDate(value: Date): string {
  return `${String(value.getFullYear()).padStart(4, '0')}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function dateAt(year: number, month: number, day: number): Date {
  const date = new Date(0);
  date.setHours(12, 0, 0, 0);
  date.setFullYear(year, month, day);
  return date;
}

export function parseDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const date = dateAt(year, month - 1, day);
  return year >= 1 && localDate(date) === value ? date : null;
}

interface CalendarProps {
  label: string;
  value: string;
  min?: string;
  max?: string;
  onSelect: (date: string) => void;
  onClose?: () => void;
}

export function Calendar({ label, value, min = '0001-01-01', max = '9999-12-31', onSelect, onClose }: CalendarProps) {
  const today = localDate(new Date());
  const candidate = parseDate(value) ? value : today;
  const initial = candidate < min ? min : candidate > max ? max : candidate;
  const [month, setMonth] = useState(() => initial.slice(0, 7));
  const [yearText, setYearText] = useState(() => String(Number(initial.slice(0, 4))));
  const [active, setActive] = useState(initial);
  const pendingFocus = useRef(false);
  const grid = useRef<HTMLDivElement>(null);
  const [year, monthNumber] = month.split('-').map(Number);
  const first = dateAt(year, monthNumber - 1, 1);
  const days = dateAt(year, monthNumber, 0).getDate();
  const allowed = (date: string) => date >= min && date <= max;
  const monthAllowed = (date: Date) => date.getFullYear() >= 1 && date.getFullYear() <= 9999 && localDate(dateAt(date.getFullYear(), date.getMonth() + 1, 0)) >= min && localDate(date) <= max;
  const previous = dateAt(year, monthNumber - 2, 1);
  const next = dateAt(year, monthNumber, 1);
  useEffect(() => { setYearText(String(year)); }, [year]);
  const showMonth = (date: Date) => {
    const requested = localDate(date).slice(0, 7);
    const bounded = requested < min.slice(0, 7) ? min.slice(0, 7) : requested > max.slice(0, 7) ? max.slice(0, 7) : requested;
    setMonth(bounded);
    setYearText(String(Number(bounded.slice(0, 4))));
    setActive(bounded === min.slice(0, 7) ? min : `${bounded}-01`);
  };
  const enteredYear = () => {
    const entered = Number(yearText);
    return Number.isFinite(entered) && yearText !== ''
      ? Math.max(Number(min.slice(0, 4)), Math.min(Number(max.slice(0, 4)), Math.trunc(entered)))
      : year;
  };
  const applyYear = () => showMonth(dateAt(enteredYear(), monthNumber - 1, 1));
  useEffect(() => {
    if (pendingFocus.current) {
      grid.current?.querySelector<HTMLButtonElement>(`[data-date="${active}"]`)?.focus();
      pendingFocus.current = false;
    }
  }, [active, month]);
  const move = (date: Date) => {
    const iso = localDate(date);
    if (!allowed(iso)) return;
    pendingFocus.current = true;
    setActive(iso);
    setMonth(iso.slice(0, 7));
  };
  const navClass = 'flex size-touch shrink-0 items-center justify-center rounded-input focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground';
  return (
    <section aria-label={`${label} 달력`} className="mx-auto w-full min-w-0 max-w-[360px]">
      <h3 className="sr-only" aria-live="polite">{year}년 {monthNumber}월</h3>
      <div className="mb-2 flex items-center justify-between gap-1">
        <button type="button" aria-label="이전 달" className={navClass} disabled={!monthAllowed(previous)} onClick={() => showMonth(previous)}><ChevronLeft className="size-5" /></button>
        <div className="flex min-w-0 items-center gap-1">
          <input aria-label="연도" type="number" min={Number(min.slice(0, 4))} max={Number(max.slice(0, 4))} value={yearText} className="h-touch w-[76px] min-w-0 rounded-input border border-input bg-card px-1 text-base" onChange={(event) => setYearText(event.target.value)} onBlur={applyYear} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); applyYear(); } }} />
          <select aria-label="월" value={monthNumber} className="h-touch min-w-0 rounded-input border border-input bg-card px-1 text-base" onChange={(event) => showMonth(dateAt(enteredYear(), Number(event.target.value) - 1, 1))}>
            {Array.from({ length: 12 }, (_, index) => <option key={index} value={index + 1} disabled={!monthAllowed(dateAt(year, index, 1))}>{index + 1}월</option>)}
          </select>
        </div>
        <button type="button" aria-label="다음 달" className={navClass} disabled={!monthAllowed(next)} onClick={() => showMonth(next)}><ChevronRight className="size-5" /></button>
        {onClose && <button type="button" aria-label="달력 닫기" className={navClass} onClick={onClose}><X className="size-4" /></button>}
      </div>
      <div aria-hidden className="grid grid-cols-7 text-center text-sm text-muted-foreground">
        {['일', '월', '화', '수', '목', '금', '토'].map((day) => <span className="py-2" key={day}>{day}</span>)}
      </div>
      <div ref={grid} className="grid grid-cols-7">
        {Array.from({ length: first.getDay() }, (_, index) => <span aria-hidden key={`blank-${index}`} />)}
        {Array.from({ length: days }, (_, index) => {
          const date = dateAt(year, monthNumber - 1, index + 1);
          const iso = localDate(date);
          return <button key={iso} type="button" data-date={iso} aria-label={`${year}년 ${monthNumber}월 ${index + 1}일`} aria-pressed={iso === value} aria-current={iso === today ? 'date' : undefined}
            disabled={!allowed(iso)} tabIndex={iso === active || (active.slice(0, 7) !== month && iso === (min.slice(0, 7) === month ? min : `${month}-01`)) ? 0 : -1}
            className={`h-touch min-w-0 rounded-input text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground ${iso === value ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-primary-bg'}`}
            onClick={() => { setActive(iso); onSelect(iso); }} onKeyDown={(event) => {
              const offsets: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -date.getDay(), End: 6 - date.getDay() };
              if (event.key in offsets) { event.preventDefault(); move(dateAt(year, monthNumber - 1, index + 1 + offsets[event.key])); }
              if (event.key === 'PageUp' || event.key === 'PageDown') { event.preventDefault(); const targetMonth = monthNumber - 1 + (event.key === 'PageUp' ? -1 : 1); move(dateAt(year, targetMonth, Math.min(index + 1, dateAt(year, targetMonth + 1, 0).getDate()))); }
            }}>{index + 1}</button>;
        })}
      </div>
      <div className="mt-1 flex justify-center"><Button variant="secondary" size="compact" fullWidth={false} disabled={!allowed(today)} onClick={() => { setMonth(today.slice(0, 7)); setActive(today); onSelect(today); }}>오늘</Button></div>
    </section>
  );
}
