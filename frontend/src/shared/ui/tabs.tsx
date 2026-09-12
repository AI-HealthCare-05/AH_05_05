import type { ComponentProps, ReactNode } from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { NavLink } from 'react-router';
import { cn } from '@/shared/lib/cn';

/**
 * shadcn/ui Tabs (Radix 기반) — 수기 작성.
 * 로그인/회원가입 탭 전환(REQ-USER-002)처럼 고령 사용자가 직접 탭을 누르는
 * 화면에 쓰이므로 탭 높이를 h-touch(44px, NFR-ACC-001)로 맞췄습니다.
 */
function Tabs({ className, ...props }: ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn('flex flex-col gap-2', className)}
      {...props}
    />
  );
}

function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        'grid min-h-touch w-full grid-flow-col auto-cols-fr border-b border-border',
        className,
      )}
      {...props}
    />
  );
}

function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        'relative inline-flex min-h-touch min-w-0 items-center justify-center px-2 pb-2 pt-1 text-sm font-bold text-muted-foreground transition-colors',
        "after:absolute after:inset-x-2 after:bottom-0 after:h-[3px] after:rounded-pill after:bg-transparent after:content-['']",
        'hover:text-foreground data-[state=active]:text-primary data-[state=active]:after:bg-primary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'disabled:pointer-events-none disabled:opacity-50',
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn('flex-1 outline-none', className)}
      {...props}
    />
  );
}

export interface NavigationTabItem {
  label: ReactNode;
  to: string;
  /** 상위 경로가 하위 탭까지 선택된 것으로 표시되지 않게 합니다. */
  end?: boolean;
}

export interface NavigationTabsProps extends Omit<ComponentProps<'nav'>, 'aria-label' | 'children'> {
  label: string;
  items: NavigationTabItem[];
}

/**
 * 페이지를 이동하는 탭입니다. 채워진 clay 표면 대신 하단 ink를 써서
 * 실행 버튼과 역할을 시각적으로 구분합니다.
 */
function NavigationTabs({ label, items, className, ...props }: NavigationTabsProps) {
  return (
    <nav
      aria-label={label}
      data-slot="navigation-tabs"
      className={cn('grid min-h-touch grid-flow-col auto-cols-fr border-b border-border', className)}
      {...props}
    >
      {items.map(item => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => cn(
            'relative flex min-h-touch min-w-0 items-center justify-center px-2 pb-2 pt-1 text-sm font-bold transition-colors',
            "after:absolute after:inset-x-2 after:bottom-0 after:h-[3px] after:rounded-pill after:bg-transparent after:content-['']",
            isActive
              ? 'text-primary after:bg-primary'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

export { NavigationTabs, Tabs, TabsContent, TabsList, TabsTrigger };
