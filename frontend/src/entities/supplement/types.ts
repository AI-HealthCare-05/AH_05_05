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
  nutrients: SupplementNutrientAmount[];
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
  name: string;
  dailyCount: number;
  times: SupplementTime[];
}
