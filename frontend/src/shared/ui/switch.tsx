import type { ComponentProps } from 'react';
import * as SwitchPrimitive from '@radix-ui/react-switch';
import { cn } from '@/shared/lib/cn';

/**
 * shadcn/ui Switch (Radix 기반) — 수기 작성.
 * 기존 shared/ui/Toggle.tsx(직접 구현)를 대체합니다. 트랙 h-8 w-14, 손잡이
 * size-6 등 기존 Toggle의 치수를 그대로 유지해 겉모습을 보존했습니다.
 *
 * 이전 Toggle과 달리 label/description을 내장하지 않습니다. 알림 설정처럼
 * 라벨이 있는 설정 행이 필요하면 화면에서 이 컴포넌트를 감싸서 구성하세요.
 */
function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'rx-switch relative inline-flex h-touch w-14 shrink-0 items-center',
        'before:absolute before:inset-x-0 before:top-1/2 before:h-8 before:-translate-y-1/2 before:rounded-pill before:bg-muted before:transition-colors',
        'data-[state=checked]:before:bg-primary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'disabled:cursor-not-allowed disabled:opacity-60',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          'pointer-events-none z-10 block size-6 translate-x-1 rounded-pill bg-card transition-transform',
          'data-[state=checked]:translate-x-7',
        )}
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
