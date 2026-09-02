import type { NutrientStandards, NutrientTotal, Supplement } from './types';

/** 초과 성분이 화면 상단에 오도록 합계를 계산합니다. */
export function summarizeNutrients(
  supplements: Supplement[],
  standards: NutrientStandards | null,
): NutrientTotal[] {
  const totals = new Map<string, NutrientTotal>();

  for (const supplement of supplements) {
    for (const nutrient of supplement.nutrients) {
      const current = totals.get(nutrient.nutrientId);
      const dailyAmount = nutrient.amount * supplement.doseAmount * supplement.slots.length;
      if (current) {
        current.amount += dailyAmount;
        current.exceeded = current.ul !== null && current.amount > current.ul;
        if (!current.sourceNames.includes(supplement.name)) current.sourceNames.push(supplement.name);
      } else {
        const standard = standards?.byNutrientId[nutrient.nutrientId];
        const rni = standard?.rni ?? null;
        const ai = standard?.ai ?? null;
        const ul = standard?.ul ?? null;
        totals.set(nutrient.nutrientId, {
          ...nutrient,
          amount: dailyAmount,
          rni,
          ai,
          ul,
          exceeded: ul !== null && dailyAmount > ul,
          sourceNames: [supplement.name],
        });
      }
    }
  }

  return [...totals.values()].sort((left, right) => {
    const leftTier = standardTier(left);
    const rightTier = standardTier(right);
    if (leftTier !== rightTier) return leftTier - rightTier;
    if (leftTier === 4) return left.name.localeCompare(right.name, 'ko');
    return tierRatio(right, rightTier) - tierRatio(left, leftTier);
  });
}

function standardTier(total: NutrientTotal): number {
  const base = total.rni ?? total.ai;
  if (total.exceeded) return 1;
  if (total.ul !== null) return 2;
  if (base !== null) return 3;
  return 4;
}

function tierRatio(total: NutrientTotal, tier: number): number {
  const reference = tier <= 2 ? total.ul : (total.rni ?? total.ai);
  return reference === null || reference === 0 ? 0 : total.amount / reference;
}
