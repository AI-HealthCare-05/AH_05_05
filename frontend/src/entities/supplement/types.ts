export type SupplementTime = '아침' | '점심' | '저녁';

export interface SupplementNutrientAmount {
  nutrientId: string;
  name: string;
  amount: number;
  unit: string;
  upperLimit: number;
}

export interface Supplement {
  supplementId: number;
  name: string;
  dailyCount: number;
  times: SupplementTime[];
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
  upperLimit: number;
  exceeded: boolean;
  sourceNames: string[];
}

export interface AddSupplementPayload {
  source: 'standard' | 'manual';
  productId?: string;
  name: string;
  dailyCount: number;
  times: SupplementTime[];
}
