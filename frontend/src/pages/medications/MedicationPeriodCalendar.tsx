import { useEffect, useRef } from 'react';
import { Calendar } from '@/shared/ui/Calendar';

interface MedicationPeriodCalendarProps {
  label: string;
  value: string;
  min: string;
  max: string;
  onSelect: (date: string) => void;
  onClose: () => void;
}

export function MedicationPeriodCalendar(props: MedicationPeriodCalendarProps) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => container.current?.scrollIntoView({ block: 'start' }));
    return () => cancelAnimationFrame(frame);
  }, []);
  return <div ref={container} className="mx-auto w-full max-w-[328px] rounded-card border border-border bg-card p-3 shadow-card" onKeyDown={(event) => {
    if (event.key === 'Escape') { event.preventDefault(); props.onClose(); }
  }}><Calendar {...props} /></div>;
}
