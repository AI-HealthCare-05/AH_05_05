import type { NutrientTotal, Supplement } from './types';

/** 초과 성분이 화면 상단에 오도록 합계를 계산합니다. */
export function summarizeNutrients(supplements: Supplement[]): NutrientTotal[] {
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
        totals.set(nutrient.nutrientId, {
          ...nutrient,
          amount: dailyAmount,
          exceeded: nutrient.ul !== null && dailyAmount > nutrient.ul,
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
