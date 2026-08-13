import { cn } from '@/shared/lib/cn';

/**
 * Figma: Bottom Tabbar
 * 높이 56px(size/tabbar). 5개 탭이 화면 폭을 균등 분할합니다.
 *
 * 와이어프레임이 ○/● 글리프로 그려져 있어 그대로 옮겼습니다.
 * 아이콘이 정해지면 dot 자리에 아이콘 컴포넌트를 넣으면 됩니다.
 */
export const TABS = [
  { key: 'home', label: '홈' },
  { key: 'med', label: '복약' },
  { key: 'life', label: '생활' },
  { key: 'schedule', label: '일정' },
  { key: 'chat', label: '챗봇' },
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
            <span aria-hidden className={cn('text-sm leading-none', selected && 'font-bold')}>
              {selected ? '●' : '○'}
            </span>
            <span className={cn('text-sm', selected && 'font-bold')}>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
