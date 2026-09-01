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
    if (left.exceeded !== right.exceeded) return left.exceeded ? -1 : 1;
    return standardRatio(right) - standardRatio(left);
  });
}

function standardRatio(total: NutrientTotal): number {
  const reference = total.ul ?? total.rni ?? total.ai;
  return reference === null || reference === 0 ? 0 : total.amount / reference;
}
