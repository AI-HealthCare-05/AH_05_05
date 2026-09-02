import { ApiError, http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import {
  mockAddSupplement,
  mockNutrientStandards,
  mockSearchSupplementProducts,
  mockStopSupplement,
  mockSupplementProduct,
  mockSupplementRanking,
  mockSupplements,
  mockUpdateSupplement,
} from './api.mock';
import type {
  AddSupplementPayload,
  NutrientStandards,
  SearchSupplementProductsParams,
  Supplement,
  SupplementListResult,
  SupplementNutrientAmount,
  SupplementProduct,
  SupplementRanking,
  SupplementSearchPage,
  SupplementSlot,
  UpdateSupplementPayload,
} from './types';

/** 서버 응답 원형. snake_case와 관리자 메타데이터는 이 API 경계 밖으로 노출하지 않습니다. */
interface SupplementRankingApiResponse {
  display_id: number;
  title: string;
  start_at: string;
  end_at: string;
  is_enabled: boolean;
  created_by_admin_id: number | null;
  created_at: string;
  updated_at: string | null;
  items: Array<{
    supplement_nutrient_id: number;
    name: string;
    rank_no: number;
  }>;
}

type NumericApiValue = number | string | null;

interface SupplementNutrientApiResponse {
  id: number;
  food_code: string;
  name: string;
  basis_qty: string;
  energy_kcal: number;
  water_g: NumericApiValue;
  protein_g: NumericApiValue;
  fat_g: NumericApiValue;
  ash_g: NumericApiValue;
  carb_g: NumericApiValue;
  sugar_g: NumericApiValue;
  fiber_g: NumericApiValue;
  calcium_mg: NumericApiValue;
  iron_mg: NumericApiValue;
  phosphorus_mg: NumericApiValue;
  potassium_mg: NumericApiValue;
  sodium_mg: NumericApiValue;
  vitamin_a_ug_rae: NumericApiValue;
  retinol_ug: NumericApiValue;
  beta_carotene_ug: NumericApiValue;
  thiamine_mg: NumericApiValue;
  riboflavin_mg: NumericApiValue;
  niacin_mg: NumericApiValue;
  vitamin_c_mg: NumericApiValue;
  vitamin_d_ug: NumericApiValue;
  cholesterol_mg: NumericApiValue;
  sat_fat_g: NumericApiValue;
  trans_fat_g: NumericApiValue;
  serving_desc: string;
  serving_size: string;
  daily_freq: string;
  target: string | null;
  rating_average: NumericApiValue;
  review_count: number;
}

interface SupplementNutrientListApiResponse {
  items: SupplementNutrientApiResponse[];
  total: number;
  offset: number;
  limit: number;
}

type SupplementSlotApi = 'MORNING' | 'LUNCH' | 'EVENING' | 'BEDTIME';

interface UserSupplementNutrientApiResponse {
  id: number;
  custom_name: string | null;
  dose_amount: number | string;
  dose_unit: string;
  start_date: string;
  end_date: string | null;
  status: 'ACTIVE' | 'PAUSED' | 'COMPLETED';
  score: number | null;
  note: string | null;
  created_at: string;
  updated_at: string | null;
  slots: Array<{ slot: SupplementSlotApi; time: string }>;
  supplement: SupplementNutrientApiResponse | null;
}

interface NutrientStandardValuesApiResponse {
  rni: NumericApiValue;
  ai: NumericApiValue;
  ul: NumericApiValue;
}

interface UserNutrientStandardApiResponse {
  grp: string;
  age: string | null;
  protein_g: NutrientStandardValuesApiResponse;
  carb_g: NutrientStandardValuesApiResponse;
  fat_g: NutrientStandardValuesApiResponse;
  fiber_g: NutrientStandardValuesApiResponse;
  calcium_mg: NutrientStandardValuesApiResponse;
  iron_mg: NutrientStandardValuesApiResponse;
  phosphorus_mg: NutrientStandardValuesApiResponse;
  potassium_mg: NutrientStandardValuesApiResponse;
  sodium_mg: NutrientStandardValuesApiResponse;
  vitamin_a_ug_rae: NutrientStandardValuesApiResponse;
  thiamine_mg: NutrientStandardValuesApiResponse;
  riboflavin_mg: NutrientStandardValuesApiResponse;
  niacin_mg: NutrientStandardValuesApiResponse;
  vitamin_c_mg: NutrientStandardValuesApiResponse;
  vitamin_d_ug: NutrientStandardValuesApiResponse;
}

interface UserSupplementNutrientListApiResponse {
  items: UserSupplementNutrientApiResponse[];
  total: number;
  offset: number;
  limit: number;
  nutrient_standard: UserNutrientStandardApiResponse | null;
}

const SLOT_TO_API: Record<SupplementSlot, SupplementSlotApi> = {
  morning: 'MORNING',
  lunch: 'LUNCH',
  evening: 'EVENING',
  bedtime: 'BEDTIME',
};

const API_TO_SLOT: Record<SupplementSlotApi, SupplementSlot> = {
  MORNING: 'morning',
  LUNCH: 'lunch',
  EVENING: 'evening',
  BEDTIME: 'bedtime',
};

const NUTRIENT_FIELDS: Array<{
  field: keyof SupplementNutrientApiResponse;
  nutrientId: string;
  name: string;
  unit: string;
}> = [
  { field: 'protein_g', nutrientId: 'protein', name: '단백질', unit: 'g' },
  { field: 'fat_g', nutrientId: 'fat', name: '지방', unit: 'g' },
  { field: 'carb_g', nutrientId: 'carbohydrate', name: '탄수화물', unit: 'g' },
  { field: 'fiber_g', nutrientId: 'fiber', name: '식이섬유', unit: 'g' },
  { field: 'calcium_mg', nutrientId: 'calcium', name: '칼슘', unit: 'mg' },
  { field: 'iron_mg', nutrientId: 'iron', name: '철', unit: 'mg' },
  { field: 'phosphorus_mg', nutrientId: 'phosphorus', name: '인', unit: 'mg' },
  { field: 'potassium_mg', nutrientId: 'potassium', name: '칼륨', unit: 'mg' },
  { field: 'sodium_mg', nutrientId: 'sodium', name: '나트륨', unit: 'mg' },
  { field: 'vitamin_a_ug_rae', nutrientId: 'vitamin-a', name: '비타민 A', unit: 'µg RAE' },
  { field: 'thiamine_mg', nutrientId: 'thiamine', name: '티아민', unit: 'mg' },
  { field: 'riboflavin_mg', nutrientId: 'riboflavin', name: '리보플라빈', unit: 'mg' },
  { field: 'niacin_mg', nutrientId: 'niacin', name: '나이아신', unit: 'mg' },
  { field: 'vitamin_c_mg', nutrientId: 'vitamin-c', name: '비타민 C', unit: 'mg' },
  { field: 'vitamin_d_ug', nutrientId: 'vitamin-d', name: '비타민 D', unit: 'µg' },
];

export async function getSupplements(): Promise<SupplementListResult> {
  if (USE_MOCK) {
    await mockDelay();
    return { items: mockSupplements(), standards: mockNutrientStandards() };
  }
  const response = await http.get<UserSupplementNutrientListApiResponse>(
    '/v1/med/user-suppl-nutr?status=ACTIVE&offset=0&limit=100',
  );
  return {
    items: response.items.map(mapUserSupplement),
    standards: mapNutrientStandards(response.nutrient_standard),
  };
}

export async function getSupplementRanking(): Promise<SupplementRanking | null> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSupplementRanking();
  }
  try {
    const response = await http.get<SupplementRankingApiResponse>(
      '/v1/display/med/nutr/rank',
    );
    return mapSupplementRanking(response);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getSupplementProduct(productId: string): Promise<SupplementProduct> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSupplementProduct(productId);
  }
  const response = await http.get<SupplementNutrientApiResponse>(
    `/v1/med/nutr/${encodeURIComponent(productId)}`,
  );
  return mapSupplementProduct(response);
}

export async function addSupplement(payload: AddSupplementPayload): Promise<Supplement> {
  if (USE_MOCK) {
    await mockDelay();
    return mockAddSupplement(payload);
  }
  if (payload.source === 'manual') {
    const response = await http.post<UserSupplementNutrientApiResponse>(
      '/v1/med/user-suppl-nutr',
      {
        custom_name: payload.name,
        dose_amount: payload.doseAmount,
        dose_unit: payload.doseUnit,
        start_date: todayInKorea(),
        end_date: null,
        slots: payload.slots.map((slot) => SLOT_TO_API[slot]),
        note: null,
      },
    );
    return mapUserSupplement(response);
  }
  const response = await http.put<UserSupplementNutrientApiResponse>(
    `/v1/med/user-suppl-nutr/${encodeURIComponent(payload.productId)}`,
    {
      dose_amount: payload.doseAmount,
      dose_unit: payload.doseUnit,
      start_date: todayInKorea(),
      end_date: null,
      slots: payload.slots.map((slot) => SLOT_TO_API[slot]),
      note: null,
    },
  );
  return mapUserSupplement(response);
}

export async function updateSupplement(
  supplementId: number,
  payload: UpdateSupplementPayload,
): Promise<Supplement> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateSupplement(supplementId, payload);
  }
  const body: Record<string, unknown> = {
    dose_amount: payload.doseAmount,
    slots: payload.slots.map((slot) => SLOT_TO_API[slot]),
  };
  if ('score' in payload) body.score = payload.score;
  if ('note' in payload) body.note = payload.note;
  const response = await http.patch<UserSupplementNutrientApiResponse>(
    `/v1/med/user-suppl-nutr/${supplementId}`,
    body,
  );
  return mapUserSupplement(response);
}

export async function stopSupplement(supplementId: number): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    mockStopSupplement(supplementId);
    return;
  }
  await http.delete<void>(`/v1/med/user-suppl-nutr/${supplementId}`);
}

export async function searchSupplementProducts(
  params: SearchSupplementProductsParams,
): Promise<SupplementSearchPage> {
  if (USE_MOCK) {
    await mockDelay();
    return mockSearchSupplementProducts(params);
  }
  const query = new URLSearchParams({
    name: params.query.trim(),
    offset: String(params.offset ?? 0),
    limit: String(params.limit ?? 20),
  });
  if (params.sort) query.set('sort', params.sort);
  const response = await http.get<SupplementNutrientListApiResponse>(
    `/v1/med/nutr?${query.toString()}`,
  );
  const items = response.items.map(mapSupplementProduct);
  const loaded = response.offset + items.length;
  return {
    items,
    total: response.total,
    nextOffset: loaded < response.total ? loaded : null,
  };
}

function mapUserSupplement(registration: UserSupplementNutrientApiResponse): Supplement {
  if (registration.supplement === null) {
    return {
      supplementId: registration.id,
      productId: null,
      name: registration.custom_name ?? '이름 없는 영양제',
      doseAmount: Number(registration.dose_amount),
      doseUnit: registration.dose_unit,
      slots: registration.slots.map(({ slot }) => API_TO_SLOT[slot]),
      score: registration.score ?? null,
      note: registration.note ?? null,
      nutrientDataAvailable: false,
      nutrients: [],
    };
  }
  const product = mapSupplementProduct(registration.supplement);
  return {
    supplementId: registration.id,
    productId: product.productId,
    name: product.productName,
    doseAmount: Number(registration.dose_amount),
    doseUnit: registration.dose_unit,
    slots: registration.slots.map(({ slot }) => API_TO_SLOT[slot]),
    score: registration.score ?? null,
    note: registration.note ?? null,
    nutrientDataAvailable: product.nutrients.length > 0,
    nutrients: product.nutrients,
  };
}

function mapSupplementProduct(product: SupplementNutrientApiResponse): SupplementProduct {
  const serving = parseServingDescription(product.serving_desc);
  return {
    productId: String(product.id),
    productName: product.name,
    brand: '',
    manufacturer: product.target ?? '섭취 대상 정보 없음',
    dosageForm: product.serving_desc,
    packageAmount: product.serving_size,
    category: product.target ?? '',
    servingDescription: product.serving_desc,
    servingSize: product.serving_size,
    dailyFrequency: product.daily_freq,
    recommendedDoseAmount: serving.amount,
    doseUnit: serving.unit,
    recommendedSlots: defaultSlotsForDailyFrequency(product.daily_freq),
    ratingAverage: toNumberOrNull(product.rating_average),
    reviewCount: Number(product.review_count ?? 0),
    nutrients: mapNutrients(product, serving.amount),
  };
}

function mapSupplementRanking(response: SupplementRankingApiResponse): SupplementRanking {
  return {
    title: response.title,
    items: response.items.map((item) => ({
      productId: String(item.supplement_nutrient_id),
      name: item.name,
      rank: item.rank_no,
      alreadyRegistered: false,
    })),
  };
}

function mapNutrients(
  product: SupplementNutrientApiResponse,
  servingCount: number,
): SupplementNutrientAmount[] {
  const perUnitFactor = nutrientPerUnitFactor(product, servingCount);
  return NUTRIENT_FIELDS.flatMap(({ field, nutrientId, name, unit }) => {
    const rawValue = product[field];
    const amount = typeof rawValue === 'number' || typeof rawValue === 'string'
      ? Number(rawValue) * perUnitFactor
      : Number.NaN;
    if (!Number.isFinite(amount) || amount <= 0) return [];
    return [{ nutrientId, name, amount, unit }];
  });
}

function mapNutrientStandards(
  raw: UserNutrientStandardApiResponse | null | undefined,
): NutrientStandards | null {
  if (!raw) return null;
  const byNutrientId: NutrientStandards['byNutrientId'] = {};
  for (const { field, nutrientId } of NUTRIENT_FIELDS) {
    const values = raw[field as keyof Omit<UserNutrientStandardApiResponse, 'grp' | 'age'>];
    byNutrientId[nutrientId] = {
      rni: toNumberOrNull(values?.rni),
      ai: toNumberOrNull(values?.ai),
      ul: toNumberOrNull(values?.ul),
    };
  }
  return { group: raw.grp, ageRange: raw.age, byNutrientId };
}

function toNumberOrNull(value: NumericApiValue | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nutrientPerUnitFactor(
  product: SupplementNutrientApiResponse,
  servingCount: number,
): number {
  const basis = parseMeasurement(product.basis_qty);
  const servingSize = parseMeasurement(product.serving_size);
  const servingRatio =
    basis !== null && servingSize !== null && basis.dimension === servingSize.dimension
      ? servingSize.value / basis.value
      : 1;
  const normalizedServingCount =
    Number.isFinite(servingCount) && servingCount > 0 ? servingCount : 1;
  return servingRatio / normalizedServingCount;
}

function parseServingDescription(value: string): { amount: number; unit: string } {
  const match = value.trim().match(/^(\d+(?:[.,]\d+)?)\s*(.+)$/);
  const amount = match ? Number(match[1].replace(',', '.')) : 1;
  return {
    amount: Number.isFinite(amount) && amount > 0 ? amount : 1,
    unit: match?.[2].trim() || '정',
  };
}

function defaultSlotsForDailyFrequency(value: string): SupplementSlot[] {
  const frequency = Number.parseInt(value.match(/\d+/)?.[0] ?? '', 10);
  switch (frequency) {
    case 2:
      return ['morning', 'evening'];
    case 3:
      return ['morning', 'lunch', 'evening'];
    case 4:
      return ['morning', 'lunch', 'evening', 'bedtime'];
    default:
      return Number.isFinite(frequency) && frequency > 4
        ? ['morning', 'lunch', 'evening', 'bedtime']
        : ['morning'];
  }
}

function parseMeasurement(
  value: string,
): { value: number; dimension: 'mass' | 'volume' } | null {
  const match = value.trim().match(/^(\d+(?:[.,]\d+)?)\s*(kg|g|mg|(?:µ|μ|u)g|l|ml)$/i);
  if (!match) return null;
  const amount = Number(match[1].replace(',', '.'));
  if (!Number.isFinite(amount) || amount <= 0) return null;
  const unit = match[2].toLowerCase().replace('μ', 'µ').replace('u', 'µ');
  const factors: Record<string, { factor: number; dimension: 'mass' | 'volume' }> = {
    kg: { factor: 1_000_000, dimension: 'mass' },
    g: { factor: 1_000, dimension: 'mass' },
    mg: { factor: 1, dimension: 'mass' },
    'µg': { factor: 0.001, dimension: 'mass' },
    l: { factor: 1_000, dimension: 'volume' },
    ml: { factor: 1, dimension: 'volume' },
  };
  const normalized = factors[unit];
  return normalized
    ? { value: amount * normalized.factor, dimension: normalized.dimension }
    : null;
}

function todayInKorea(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}
