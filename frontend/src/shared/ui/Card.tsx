import type { ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

/**
 * Figma: Card (COMPONENT)
 *
 * Figma 컴포넌트에는 variant가 없지만 화면에서는 네 가지 톤이 쓰입니다.
 * 코드에서 tone prop으로 구현합니다.
 *   default — 일반 카드 (card)
 *   info    — 정보 강조 (primary-bg). 홈의 '오늘의 복약' 등
 *   warning — 주의 (warning-bg). '즉시 연락할 증상', 'OCR 확인 필요 항목' 등
 *   success — 완료 (success-bg)
 */
export type CardTone = 'default' | 'info' | 'warning' | 'success';

export interface CardProps {
  tone?: CardTone;
  /** 카드 제목. 굵게 표시됩니다. */
  title?: ReactNode;
  /** 제목 오른쪽에 붙는 요소(예: StatusBadge) */
  titleRight?: ReactNode;
  children?: ReactNode;
  /** 값을 넘기면 카드 전체가 눌리는 영역이 됩니다. */
  onClick?: () => void;
  className?: string;
}

const toneClass: Record<CardTone, string> = {
  default: 'bg-card',
  info: 'bg-primary-bg',
  warning: 'bg-warning-bg',
  success: 'bg-success-bg',
};

export function Card({
  tone = 'default',
  title,
  titleRight,
  children,
  onClick,
  className,
}: CardProps) {
  const interactive = typeof onClick === 'function';

  const body = (
    <>
      {(title || titleRight) && (
        <div className="flex items-start justify-between gap-2">
          {title && <p className="text-sm font-bold text-foreground">{title}</p>}
          {titleRight}
        </div>
      )}
      {children && <div className="text-sm text-muted-foreground">{children}</div>}
    </>
  );

  const base = cn(
    'flex w-full flex-col gap-1 rounded-card px-3.5 py-2.5 text-left shadow-card',
    toneClass[tone],
    interactive && 'transition-colors hover:brightness-[0.98]',
    className,
  );

  if (interactive) {
    return (
      <button type="button" onClick={onClick} className={base}>
        {body}
      </button>
    );
  }
  return <div className={base}>{body}</div>;
}
