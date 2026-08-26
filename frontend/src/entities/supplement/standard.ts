import type { NutrientTotal } from './types';

export type NutrientStandardStatus =
  | 'below-base'
  | 'recommended'
  | 'over-upper-limit'
  | 'upper-only'
  | 'unrated';

export interface NutrientStandardEvaluation {
  base: number | null;
  baseKind: 'rni' | 'ai' | null;
  status: NutrientStandardStatus;
  percentOfBase: number | null;
}

/** RNI와 AI는 대체 관계이며, 비정상적으로 둘 다 오면 RNI를 우선합니다. */
export function evaluateNutrientStandard(total: NutrientTotal): NutrientStandardEvaluation {
  const base = total.rni ?? total.ai ?? null;
  const baseKind = total.rni !== null ? 'rni' : total.ai !== null ? 'ai' : null;

  if (total.ul !== null && total.amount > total.ul) {
    return { base, baseKind, status: 'over-upper-limit', percentOfBase: percent(total.amount, base) };
  }
  if (base !== null && total.amount < base) {
    return { base, baseKind, status: 'below-base', percentOfBase: percent(total.amount, base) };
  }
  if (base !== null) {
    return { base, baseKind, status: 'recommended', percentOfBase: percent(total.amount, base) };
  }
  if (total.ul !== null) {
    return { base, baseKind, status: 'upper-only', percentOfBase: null };
  }
  return { base, baseKind, status: 'unrated', percentOfBase: null };
}

function percent(amount: number, base: number | null): number | null {
  return base === null || base === 0 ? null : Math.round((amount / base) * 100);
}
