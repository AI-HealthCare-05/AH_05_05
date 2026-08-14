import type { ComponentProps } from 'react';
import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import { CheckIcon } from 'lucide-react';
import { cn } from '@/shared/lib/cn';

/**
 * shadcn/ui Checkbox (Radix 기반) — 수기 작성.
 * 기존 shared/ui/Checkbox.tsx(직접 구현)를 대체합니다. Figma 치수(size-6,
 * rounded-input)는 그대로 유지했습니다.
 *
 * 이전 컴포넌트와 달리 label을 내장하지 않습니다(Radix Checkbox는 값 자체만
 * 담당). 화면에서는 이 컴포넌트를 <label>과 함께 조합해서 씁니다.
 * 예)
 *   <label htmlFor="agree" className="flex min-h-touch cursor-pointer items-center gap-3">
 *     <Checkbox id="agree" checked={checked} onCheckedChange={setChecked} />
 *     <span className="text-sm text-foreground">동의합니다 (필수)</span>
 *   </label>
 */
function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        'flex size-6 shrink-0 items-center justify-center rounded-input border border-input bg-card transition-colors',
        'data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'disabled:cursor-not-allowed disabled:opacity-60',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-current">
        <CheckIcon className="size-4" aria-hidden />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
