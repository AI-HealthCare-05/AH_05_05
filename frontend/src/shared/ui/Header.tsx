import { ChevronLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/shared/lib/cn';

/**
 * Figma: Header
 * 높이 64px(size/header). 뒤로가기 버튼은 44x44(size/touch-min)를 확보합니다.
 */
export interface HeaderProps {
  title: ReactNode;
  /** 값을 넘기면 왼쪽에 뒤로가기 버튼이 표시됩니다. */
  onBack?: () => void;
  /** 오른쪽 영역(예: 마이페이지 아이콘) */
  right?: ReactNode;
  className?: string;
}

export function Header({ title, onBack, right, className }: HeaderProps) {
  return (
    <header
      className={cn(
        'flex h-header shrink-0 items-center gap-1 border-b border-border bg-card px-page-x',
        className,
      )}
    >
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          aria-label="뒤로 가기"
          className="-ml-2.5 flex size-touch items-center justify-center text-foreground"
        >
          <ChevronLeft aria-hidden="true" className="size-5" />
        </button>
      )}
      <h1 className="min-w-0 flex-1 truncate text-xl font-bold text-foreground">{title}</h1>
      {right}
    </header>
  );
}
