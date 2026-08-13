import type { ReactNode } from 'react';
import { useId } from 'react';
import { Checkbox } from './checkbox';
import { cn } from '@/shared/lib/cn';

/**
 * shadcn Checkbox + 라벨/설명을 한 행으로 묶은 표현용 래퍼입니다.
 * shadcn Checkbox 자체(체크 상태만 담당)는 그대로 두고, 화면에서 자주
 * 반복되는 "라벨 클릭으로 토글 + (필수/선택) 표기 + 설명" 패턴만 뽑았습니다.
 * 03 개인정보 처리 동의, O08 낮은 신뢰도 항목 확인 등에서 씁니다.
 */
export interface CheckboxFieldProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  /** 넘기면 label 뒤에 (필수)/(선택)이 muted 색으로 붙습니다. 넘기지 않으면 표기하지 않습니다. */
  required?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function CheckboxField({
  checked,
  onCheckedChange,
  label,
  description,
  required,
  disabled,
  id,
  className,
}: CheckboxFieldProps) {
  const autoId = useId();
  const checkboxId = id ?? autoId;

  return (
    <label
      htmlFor={checkboxId}
      className={cn(
        'flex min-h-touch cursor-pointer items-start gap-3 py-2',
        disabled && 'cursor-not-allowed opacity-60',
        className,
      )}
    >
      <Checkbox
        id={checkboxId}
        checked={checked}
        disabled={disabled}
        onCheckedChange={(next) => onCheckedChange(next === true)}
        className="mt-0.5 shrink-0"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm text-foreground">
          {label}
          {required !== undefined && (
            <span className="text-muted-foreground">{required ? ' (필수)' : ' (선택)'}</span>
          )}
        </span>
        {description && <span className="text-sm text-muted-foreground">{description}</span>}
      </span>
    </label>
  );
}
