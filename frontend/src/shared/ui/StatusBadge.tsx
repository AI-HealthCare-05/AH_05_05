import type { ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

/**
 * Figma: Status Badge (COMPONENT_SET)
 *   Type: New | Stopped | Dose | Frequency | Review
 *
 * active / done 은 Figma에 아직 없지만 홈·히스토리의 진료기록 상태 뱃지에 필요해
 * 코드에서 먼저 정의했습니다(계약서 3장 '컴포넌트 계약의 알려진 공백' 참고).
 */
export type StatusBadgeType =
  | 'new'
  | 'stopped'
  | 'dose'
  | 'frequency'
  | 'review'
  | 'active'
  | 'done';

const styles: Record<StatusBadgeType, string> = {
  new: 'bg-primary-bg text-primary-strong',
  stopped: 'bg-muted-bg text-muted-foreground',
  dose: 'bg-warning-bg text-warning-strong',
  frequency: 'bg-warning-bg text-warning-strong',
  review: 'bg-danger-bg text-danger-strong',
  active: 'bg-success-bg text-success-strong',
  done: 'bg-muted-bg text-muted-foreground',
};

const defaultLabel: Record<StatusBadgeType, string> = {
  new: '신규 처방',
  stopped: '중단',
  dose: '용량 변경',
  frequency: '횟수 변경',
  review: '확인 필요',
  active: '활성',
  done: '완료',
};

export interface StatusBadgeProps {
  type: StatusBadgeType;
  /** 기본 문구를 바꾸고 싶을 때만 넘깁니다. */
  children?: ReactNode;
  className?: string;
}

export function StatusBadge({ type, children, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-pill px-3 py-1.5 text-sm',
        styles[type],
        className,
      )}
    >
      {children ?? defaultLabel[type]}
    </span>
  );
}
