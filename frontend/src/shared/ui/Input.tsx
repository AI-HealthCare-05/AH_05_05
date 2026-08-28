import type { InputHTMLAttributes, Ref } from 'react';
import { useId } from 'react';
import { cn } from '@/shared/lib/cn';

/**
 * Figma: Input (COMPONENT_SET)
 *   State: Default | Error
 *
 * 화면에서는 라벨 + 입력창이 한 묶음(Field)으로 쓰이므로 label을 함께 받습니다.
 */
export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> {
  label?: string;
  /** 에러 문구. 값이 있으면 Error 상태로 표시됩니다. */
  error?: string;
  /** 에러가 아닌 보조 설명 */
  hint?: string;
  inputRef?: Ref<HTMLInputElement>;
  className?: string;
}

export function Input({ label, error, hint, inputRef, className, id, ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;

  return (
    <div className={cn('flex w-full flex-col gap-1.5', className)}>
      {label && (
        <label htmlFor={inputId} className="text-sm font-bold text-foreground">
          {label}
        </label>
      )}
      <input
        ref={inputRef}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          'h-touch w-full rounded-input border bg-card px-3.5 text-base text-foreground',
          'placeholder:text-disabled-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring',
          // type="date"의 달력 아이콘. 기본 크기가 작아 NFR-ACC-001 기준에 맞게 키웁니다.
          '[&::-webkit-calendar-picker-indicator]:size-6 [&::-webkit-calendar-picker-indicator]:cursor-pointer',
          error ? 'border-danger' : 'border-input',
        )}
        {...rest}
      />
      {error && (
        <p id={`${inputId}-error`} className="text-sm text-danger-strong">
          {error}
        </p>
      )}
      {!error && hint && (
        <p id={`${inputId}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}
