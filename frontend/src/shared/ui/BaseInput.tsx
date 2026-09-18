import type { InputHTMLAttributes, ReactNode, Ref } from 'react';
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
  /** 입력창 우측에 배치할 버튼 등의 액션 */
  trailingAction?: ReactNode;
  inputRef?: Ref<HTMLInputElement>;
  /** 입력 요소 자체에만 적용할 레이아웃 보정 클래스입니다. */
  inputClassName?: string;
  className?: string;
}

export function BaseInput({
  label,
  error,
  hint,
  trailingAction,
  inputRef,
  inputClassName,
  className,
  id,
  ...rest
}: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;

  return (
    <div className={cn('flex min-w-0 w-full flex-col gap-1', className)}>
      {label && (
        <label htmlFor={inputId} className="text-sm font-bold text-foreground">
          {label}
        </label>
      )}
      <div className="relative min-w-0 max-w-full">
        <input
          ref={inputRef}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            // iOS의 작은 입력 글자에 따른 포커스 확대를 피하되 사용자 확대는 제한하지 않습니다.
            'rx-input h-control w-full rounded-input border bg-card px-3.5 text-base text-foreground',
            'min-w-0 max-w-full',
            'placeholder:text-tertiary-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring',
            // type="date"의 달력 아이콘. 기본 크기가 작아 NFR-ACC-001 기준에 맞게 키웁니다.
            '[&::-webkit-calendar-picker-indicator]:size-6 [&::-webkit-calendar-picker-indicator]:cursor-pointer',
            trailingAction && 'pr-12',
            error ? 'border-danger' : 'border-input',
            inputClassName,
          )}
          {...rest}
        />
        {trailingAction && (
          <div className="absolute inset-y-0 right-1 flex items-center">{trailingAction}</div>
        )}
      </div>
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
