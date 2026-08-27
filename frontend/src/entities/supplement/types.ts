import type { MealSlot } from '@/shared/model/mealSlot';

export interface SupplementNutrientAmount {
  nutrientId: string;
  name: string;
  amount: number;
  unit: string;
  /** 권장섭취량. 충분섭취량과 동시에 값이 오면 이 값을 우선합니다. */
  rni: number | null;
  /** 충분섭취량. 권장섭취량을 정할 수 없을 때만 사용합니다. */
  ai: number | null;
  /** 상한섭취량. 기준이 없는 성분은 null입니다. */
  ul: number | null;
}

export interface Supplement {
  supplementId: number;
  name: string;
  dailyCount: number;
  slots: MealSlot[];
  /** false면 직접 입력 제품으로, 성분 합계에서 제외합니다. */
  nutrientDataAvailable: boolean;
  nutrients: SupplementNutrientAmount[];
}

export interface SupplementProduct {
  productId: string;
  /** 브랜드가 포함된 표준데이터 제품명 */
  productName: string;
  brand: string;
  manufacturer: string;
  dosageForm: string;
  packageAmount: string;
  category: string;
  /** 표시사항에서 읽은 1일 섭취 정수. null이면 프리필할 수 없습니다. */
  recommendedDailyCount: number | null;
  /** 1정 기준 성분량. 합계에서 dailyCount를 곱합니다. */
  nutrients: SupplementNutrientAmount[];
}

export interface SupplementSearchPage {
  items: SupplementProduct[];
  total: number;
  nextOffset: number | null;
}

export interface SupplementRankingItem {
  rank: number;
  productId: string;
  productName: string;
  registeredCount: number;
  alreadyRegistered: boolean;
}

export interface SupplementRanking {
  /** 서버가 집계 기준을 설명하는 문장. 화면에서 그대로 표시합니다. */
  basis: string;
  periodDays: number;
  items: SupplementRankingItem[];
}

export interface SearchSupplementProductsParams {
  query: string;
  offset?: number;
  limit?: number;
}

export interface NutrientTotal {
  nutrientId: string;
  name: string;
  amount: number;
  unit: string;
  rni: number | null;
  ai: number | null;
  ul: number | null;
  exceeded: boolean;
  sourceNames: string[];
}

export interface AddSupplementPayload {
  source: 'standard' | 'manual';
  productId?: string;
  name: string;
  dailyCount: number;
  slots: MealSlot[];
}

export interface UpdateSupplementPayload {
  dailyCount: number;
  slots: MealSlot[];
}
