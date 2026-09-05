import type { MealSlot } from '@/shared/model/mealSlot';

export type SupplementSlot = MealSlot;
export type SupplementSortKey = 'name' | 'registered' | 'rating' | 'reviews';

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
  /** 서버가 사용자 설정에서 계산한 실제 시간대 시각. */
  slotTimes?: Partial<Record<SupplementSlot, string>>;
  startDate?: string;
  endDate?: string | null;
  /** 사용자가 남긴 별점 1~5. 안 남겼으면 null */
  score: number | null;
  /** 다른 사용자에게 공개되는 후기 본문. 안 썼으면 null */
  reviewBody: string | null;
  /** 사용자만 보는 복용 메모. 안 남겼으면 null */
  note: string | null;
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
  ratingAverage: number | null;
  reviewCount: number;
  /** 1개 단위 기준 성분량. 합계에서 회당 수량과 슬롯 수를 곱합니다. */
  nutrients: SupplementNutrientAmount[];
}

export interface SupplementSearchPage {
  items: SupplementProduct[];
  total: number;
  nextOffset: number | null;
}

export interface SupplementReview {
  /** registration_id. 신고할 때 이 값을 보냅니다. */
  id: number;
  /** 서버에서 이미 마스킹된 이름입니다. 프론트에서 다시 가공하지 않습니다. */
  authorLabel: string;
  score: number | null;
  reviewBody: string | null;
  updatedAt: string;
  isMine: boolean;
  reportedByMe: boolean;
}

export interface SupplementReviewList {
  items: SupplementReview[];
  total: number;
  offset: number;
  limit: number;
  ratingAverage: number | null;
  reviewCount: number;
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
  sort?: SupplementSortKey;
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
  score?: number | null;
  note?: string | null;
  reviewBody?: string | null;
}

export interface SupplementDoseRecord {
  supplementId: number;
  date: string;
  slot: SupplementSlot;
  taken: boolean;
}
