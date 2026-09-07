import { Check, Pill, Sprout } from 'lucide-react';

import type { ChallengeBadge } from '@/features/challenges/types';
import { cn } from '@/shared/lib/cn';

const fallbackIcons = { check: Check, pill: Pill, sprout: Sprout } as const;

export function ChallengeBadgeArt({
  badge,
  className,
}: {
  badge: ChallengeBadge;
  className?: string;
}) {
  const earned = Boolean(badge.earnedAt);
  const Icon = fallbackIcons[badge.icon];

  return (
    <span
      className={cn(
        'flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-pill bg-card text-primary',
        !earned && 'opacity-60 grayscale',
        className,
      )}
    >
      {badge.imageUrl ? (
        <img
          src={badge.imageUrl}
          alt={badge.name}
          className="size-full object-contain"
        />
      ) : (
        <Icon aria-hidden className="size-6" />
      )}
    </span>
  );
}
