import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/shared/lib/cn';

export interface DoseSlotButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-pressed'> {
  selected: boolean;
}

export function DoseSlotButton({
  selected,
  className,
  type = 'button',
  ...props
}: DoseSlotButtonProps) {
  return (
    <button
      {...props}
      type={type}
      aria-pressed={selected}
      className={cn(
        'rx-dose-slot min-h-touch rounded-input border px-1 text-sm font-bold',
        selected
          ? 'border-primary bg-[var(--color-primary)] text-card'
          : 'border-border bg-card text-muted-foreground',
        className,
      )}
    />
  );
}
