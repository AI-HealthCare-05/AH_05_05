import { House, MessageCircle, Pill, Sprout, UserRound } from 'lucide-react';
import { cn } from '@/shared/lib/cn';

/**
 * Figma: Bottom Tabbar
 * 높이 64px(size/tabbar). 5개 탭이 화면 폭을 균등 분할합니다.
 *
 * 아이콘은 24px 스트로크 SVG 세트(lucide-react)로 통일합니다.
 */
export const TABS = [
  { key: 'home', label: '홈', icon: House },
  { key: 'medication', label: '복약', icon: Pill },
  { key: 'supplement', label: '영양제', icon: Sprout },
  { key: 'chat', label: '챗봇', icon: MessageCircle },
  { key: 'my', label: '마이', icon: UserRound },
] as const;

export type TabKey = (typeof TABS)[number]['key'];

export interface BottomTabbarProps {
  active: TabKey;
  onChange: (key: TabKey) => void;
  className?: string;
}

export function BottomTabbar({ active, onChange, className }: BottomTabbarProps) {
  return (
    <nav
      className={cn('flex h-tabbar shrink-0 items-stretch bg-card', className)}
      aria-label="주요 화면"
    >
      {TABS.map((tab) => {
        const selected = tab.key === active;
        const Icon = tab.icon;
        return (
          <button
            key={tab.key}
            type="button"
            aria-current={selected ? 'page' : undefined}
            onClick={() => onChange(tab.key)}
            className={cn(
              'flex flex-1 flex-col items-center justify-center gap-0.5',
              selected ? 'text-primary' : 'text-muted-foreground',
            )}
          >
            <Icon aria-hidden className="size-5" strokeWidth={selected ? 2.5 : 2} />
            <span className={cn('text-sm', selected && 'font-bold')}>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
