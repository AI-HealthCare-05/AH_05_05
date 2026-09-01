import type { MealSlot } from '@/shared/model/mealSlot';

export type SupplementSlot = MealSlot;

export interface SupplementNutrientAmount {
  nutrientId: string;
  name: string;
  amount: number;
  unit: string;
}

export interface Supplement {
  supplementId: number;
  productId: string | null;
  name: string;
  /** 한 번 먹을 때 섭취하는 수량입니다. */
  doseAmount: number;
  doseUnit: string;
  slots: SupplementSlot[];
  /** false면 직접 입력 제품으로, 성분 합계에서 제외합니다. */
  nutrientDataAvailable: boolean;
  nutrients: SupplementNutrientAmount[];
}

/** 사용자의 나이·성별에 맞는 섭취기준. nutrientId로 찾습니다. */
export interface NutrientStandards {
  /** 화면 표시가 아니라 매칭된 원본 행 확인에 사용합니다. */
  group: string;
  ageRange: string | null;
  byNutrientId: Record<
    string,
    { rni: number | null; ai: number | null; ul: number | null }
  >;
}

export interface SupplementListResult {
  items: Supplement[];
  standards: NutrientStandards | null;
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
  /** RDB의 1회분량·중량·1일섭취횟수 원문입니다. */
  servingDescription: string;
  servingSize: string;
  dailyFrequency: string;
  /** 표시사항에서 읽은 1회 섭취 수량과 단위입니다. */
  recommendedDoseAmount: number | null;
  doseUnit: string;
  recommendedSlots: SupplementSlot[];
  /** 1개 단위 기준 성분량. 합계에서 회당 수량과 슬롯 수를 곱합니다. */
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
  name: string;
  alreadyRegistered: boolean;
}

export interface SupplementRanking {
  title: string;
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

interface StandardSupplementPayload {
  source: 'standard';
  productId: string;
  name: string;
  doseAmount: number;
  doseUnit: string;
  slots: SupplementSlot[];
}

interface ManualSupplementPayload {
  source: 'manual';
  name: string;
  doseAmount: number;
  doseUnit: string;
  slots: SupplementSlot[];
}

export type AddSupplementPayload = StandardSupplementPayload | ManualSupplementPayload;

export interface UpdateSupplementPayload {
  doseAmount: number;
  slots: SupplementSlot[];
}
