import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { BaseInput, type InputProps } from './BaseInput';
import { Calendar, localDate, parseDate } from './Calendar';
import { Button } from './Button';
import { Dialog, DialogContent, DialogTitle } from './dialog';

export function DateInput(props: InputProps) {
  const { type, inputRef, inputClassName, value, defaultValue, onChange, onClick, onKeyDown, onBlur, min, max, ...rest } = props;
  const field = useRef<HTMLInputElement | null>(null);
  const popup = useRef<HTMLDivElement | null>(null);
  const selection = useRef<{ start: number; end: number } | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [uncontrolled, setUncontrolled] = useState(String(defaultValue ?? ''));
  const [partialInput, setPartialInput] = useState<string | null>(null);
  const current = String(value ?? uncontrolled);
  useLayoutEffect(() => {
    if (selection.current && document.activeElement === field.current) {
      field.current?.setSelectionRange(selection.current.start, selection.current.end);
    }
    selection.current = null;
  }, [current, partialInput]);
  const withTime = type === 'datetime-local';
  const title = String(props['aria-label'] ?? props.label ?? '날짜');
  const valid = (candidate: string) => {
    if (!candidate) return !props.required;
    const probe = document.createElement('input');
    probe.type = type!;
    probe.value = candidate;
    if (min !== undefined) probe.min = String(min);
    if (max !== undefined) probe.max = String(max);
    if (props.step !== undefined) probe.step = String(props.step);
    return probe.value !== '' && probe.checkValidity();
  };
  const updateValidity = (candidate: string) => field.current?.setCustomValidity(valid(candidate) ? '' : '선택 가능한 날짜와 시간을 확인해 주세요.');
  useEffect(() => { updateValidity(partialInput ?? current); }, [current, partialInput, min, max, type, props.step, props.required]);
  const openPicker = () => {
    if (props.disabled || props.readOnly) return;
    const now = new Date();
    let day = parseDate(current.slice(0, 10)) ? current.slice(0, 10) : localDate(now);
    if (min && day < String(min).slice(0, 10)) day = String(min).slice(0, 10);
    if (max && day > String(max).slice(0, 10)) day = String(max).slice(0, 10);
    const time = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(current) ? current.slice(11) : `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    setDraft(withTime ? `${day}T${time}` : day);
    setOpen(true);
  };
  const apply = () => {
    if (!field.current || !draft || !valid(draft)) return;
    // Preserve the existing controlled forms' real onChange event contract.
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field.current, draft);
    field.current.dispatchEvent(new Event('input', { bubbles: true }));
    setOpen(false);
  };
  const time = draft.slice(11).split(':');
  return <>
    <BaseInput {...rest} type="text" min={min} max={max} inputMode="none" value={partialInput ?? current} inputClassName={`${inputClassName ?? ''} !text-base cursor-pointer`} inputRef={(node) => {
      field.current = node;
      if (typeof inputRef === 'function') inputRef(node);
      else if (inputRef) inputRef.current = node;
    }} aria-haspopup="dialog" aria-expanded={open} onChange={(event) => {
      // Native date fields expose an empty value for impossible dates. Keep that
      // contract even when a hardware keyboard is used instead of the calendar.
      const probe = document.createElement('input');
      selection.current = { start: event.target.selectionStart ?? 0, end: event.target.selectionEnd ?? 0 };
      probe.type = type!;
      probe.value = event.target.value;
      setPartialInput(probe.value ? null : event.target.value);
      if (!probe.value) event.target.value = '';
      updateValidity(event.target.value);
      setUncontrolled(event.target.value);
      onChange?.(event);
    }} onBlur={(event) => { setPartialInput(null); onBlur?.(event); }} onClick={(event) => { onClick?.(event); if (!event.defaultPrevented) openPicker(); }} onKeyDown={(event) => {
      onKeyDown?.(event);
      if (!event.defaultPrevented && (event.key === 'Enter' || event.key === 'ArrowDown')) { event.preventDefault(); openPicker(); }
    }} trailingAction={<button type="button" aria-label="달력 열기" disabled={props.disabled || props.readOnly} className="flex size-touch items-center justify-center rounded-input text-primary focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground" onClick={openPicker}><CalendarDays aria-hidden className="size-5" /></button>} />
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent ref={popup} className="max-h-[90dvh] max-w-[400px] overflow-y-auto" aria-describedby={undefined} onOpenAutoFocus={(event) => {
        event.preventDefault();
        (popup.current?.querySelector<HTMLButtonElement>('[data-date][aria-pressed="true"]:not(:disabled)') ?? popup.current?.querySelector<HTMLButtonElement>('[data-date]:not(:disabled)'))?.focus();
      }} onCloseAutoFocus={(event) => { event.preventDefault(); field.current?.focus(); }}>
        <DialogTitle className="pr-9">{title} 선택</DialogTitle>
        <Calendar label={title} value={draft.slice(0, 10)} min={min === undefined ? undefined : String(min).slice(0, 10)} max={max === undefined ? undefined : String(max).slice(0, 10)} onSelect={(date) => setDraft(date + (withTime ? `T${draft.slice(11)}` : ''))} />
        {withTime && <div className="flex items-center justify-center gap-2">
          <select aria-label="시 (24시간제)" value={time[0]} className="h-control rounded-input border border-input bg-card px-3 text-base" onChange={(event) => setDraft(`${draft.slice(0, 10)}T${event.target.value}:${time[1] ?? '00'}`)}>
            {Array.from({ length: 24 }, (_, index) => { const hour = String(index).padStart(2, '0'); return <option key={hour} value={hour}>{hour}시</option>; })}
          </select>
          <span aria-hidden>:</span>
          <select aria-label="분" value={time[1]} className="h-control rounded-input border border-input bg-card px-3 text-base" onChange={(event) => setDraft(`${draft.slice(0, 10)}T${time[0] ?? '00'}:${event.target.value}`)}>
            {Array.from({ length: 60 }, (_, index) => { const minute = String(index).padStart(2, '0'); return <option key={minute} value={minute}>{minute}분</option>; })}
          </select>
        </div>}
        <div className="grid grid-cols-2 gap-2"><Button variant="secondary" onClick={() => setOpen(false)}>취소</Button><Button disabled={!draft || !valid(draft)} onClick={apply}>적용</Button></div>
      </DialogContent>
    </Dialog>
  </>;
}
