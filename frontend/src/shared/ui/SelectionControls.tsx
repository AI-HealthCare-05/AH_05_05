import type { ComponentProps } from 'react';

import { cn } from '@/shared/lib/cn';
import { Button } from './Button';
import { Checkbox } from './checkbox';

export interface SelectionActionsProps {
  selectionMode: boolean;
  selectedCount: number;
  onStart: () => void;
  onCancel: () => void;
  onDelete: () => void;
  deletePending?: boolean;
  className?: string;
  'aria-label'?: string;
}

/** 목록 제목 옆에서 선택 진입과 취소·삭제 상태를 일관되게 전환합니다. */
export function SelectionActions({
  selectionMode,
  selectedCount,
  onStart,
  onCancel,
  onDelete,
  deletePending = false,
  className,
  'aria-label': ariaLabel = '목록 선택',
}: SelectionActionsProps) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn('flex shrink-0 items-center gap-2', className)}
    >
      {selectionMode ? (
        <>
          <Button
            fullWidth={false}
            variant="secondary"
            disabled={deletePending}
            onClick={onCancel}
          >
            취소
          </Button>
          {selectedCount > 0 && (
            <Button
              fullWidth={false}
              variant="danger"
              loading={deletePending}
              onClick={onDelete}
            >
              {deletePending ? '삭제 중...' : `삭제 ${selectedCount}개`}
            </Button>
          )}
        </>
      ) : (
        <Button fullWidth={false} variant="secondary" onClick={onStart}>
          선택
        </Button>
      )}
    </div>
  );
}

export interface SelectionCheckboxProps
  extends Omit<ComponentProps<typeof Checkbox>, 'checked' | 'onCheckedChange'> {
  checked: boolean;
  onCheckedChange: () => void;
}

/** 복약·영양제·메모 목록에서 쓰는 24px 원형 선택 컨트롤입니다. */
export function SelectionCheckbox({
  className,
  checked,
  onCheckedChange,
  ...props
}: SelectionCheckboxProps) {
  return (
    <Checkbox
      checked={checked}
      onCheckedChange={onCheckedChange}
      className={cn('rounded-pill', className)}
      {...props}
    />
  );
}
