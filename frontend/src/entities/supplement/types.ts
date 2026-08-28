import type { MealSlot } from '@/shared/model/mealSlot';

export type SupplementSlot = MealSlot;

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
