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
  /** 실제 요청 중에만 사용합니다. 문구·너비를 유지하고 중복 입력을 막습니다. */
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  fullWidth = true,
  disabled = false,
  loading = false,
  className,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const inactive = disabled || loading;
  return (
    <button
      type={type}
      disabled={inactive}
      aria-busy={loading || undefined}
      data-variant={variant}
      className={cn(
        // 공통 — 최소 터치 영역 44px 보장(NFR-ACC-001)
        'rx-button relative inline-flex min-h-touch items-center justify-center rounded-button px-4 text-sm font-bold',
        'h-control',
        fullWidth && 'w-full',
        // 변형
        variant === 'primary' && !inactive && 'bg-primary text-card hover:bg-primary-strong',
        variant === 'secondary' &&
          !inactive &&
          'border border-border bg-card text-foreground hover:bg-muted-bg',
        variant === 'danger' && !inactive && 'bg-danger text-card hover:bg-danger-strong',
        // 비활성
        inactive && 'cursor-not-allowed bg-muted-bg text-disabled-foreground',
        inactive && variant === 'secondary' && 'border border-border bg-card',
        className,
      )}
      {...rest}
    >
      {loading && <span className="rx-button-spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}
