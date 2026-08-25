import type { ComponentProps } from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
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
        'inline-flex h-touch w-full items-center justify-center gap-1 rounded-input bg-muted p-1',
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
        'inline-flex flex-1 items-center justify-center rounded-input py-2 text-sm font-bold text-muted-foreground transition-colors',
        'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-card',
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

export { Tabs, TabsContent, TabsList, TabsTrigger };
