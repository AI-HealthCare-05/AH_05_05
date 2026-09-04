import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

/**
 * Figma: Button (COMPONENT_SET)
 *   Style: Primary | Secondary
 *   State: Default | Disabled
 *
 * Figma 컴포넌트에는 Secondary + Disabled 조합이 빠져 있습니다.
 * 코드에서는 두 조합 모두 지원합니다.
 *
 * `danger`는 Figma에 없는 변형입니다. O07(복약 정보 편집 모달)의 "삭제" 확인
 * 버튼처럼 파괴적 동작에 필요해 추가했습니다. 새 색을 만들지 않고 기존
 * danger/danger-strong 토큰만 재사용합니다.
 */
export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'style'> {
  variant?: 'primary' | 'secondary' | 'danger';
  /** 화면 하단 CTA는 대부분 가로 전체를 차지합니다. */
  fullWidth?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  fullWidth = true,
  disabled = false,
  className,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled}
      className={cn(
        // 공통 — 최소 터치 영역 44px 보장(NFR-ACC-001)
        'inline-flex min-h-touch items-center justify-center rounded-button px-4 text-sm font-bold transition-colors',
        'h-control',
        fullWidth && 'w-full',
        // 변형
        variant === 'primary' && !disabled && 'bg-primary text-card hover:bg-primary-strong',
        variant === 'secondary' &&
          !disabled &&
          'border border-border bg-card text-foreground hover:bg-muted-bg',
        variant === 'danger' && !disabled && 'bg-danger text-card hover:bg-danger-strong',
        // 비활성
        disabled && 'cursor-not-allowed bg-muted-bg text-disabled-foreground',
        disabled && variant === 'secondary' && 'border border-border bg-card',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
