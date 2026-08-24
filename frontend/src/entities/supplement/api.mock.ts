import type { AddSupplementPayload, Supplement } from './types';

export function mockSupplements(): Supplement[] {
  return [
    {
      supplementId: 501,
      name: '오메가3',
      dailyCount: 2,
      times: ['아침', '저녁'],
      nutrients: [
        { nutrientId: 'vitamin-a', name: '비타민 A', amount: 600, unit: 'µg RAE', upperLimit: 3000 },
      ],
    },
    {
      supplementId: 502,
      name: '종합비타민',
      dailyCount: 1,
      times: ['아침'],
      nutrients: [
        { nutrientId: 'vitamin-a', name: '비타민 A', amount: 2600, unit: 'µg RAE', upperLimit: 3000 },
        { nutrientId: 'vitamin-d', name: '비타민 D', amount: 20, unit: 'µg', upperLimit: 100 },
        { nutrientId: 'iron', name: '철', amount: 18, unit: 'mg', upperLimit: 45 },
        { nutrientId: 'calcium', name: '칼슘', amount: 400, unit: 'mg', upperLimit: 2500 },
        { nutrientId: 'vitamin-c', name: '비타민 C', amount: 100, unit: 'mg', upperLimit: 2000 },
        { nutrientId: 'zinc', name: '아연', amount: 8, unit: 'mg', upperLimit: 35 },
        { nutrientId: 'magnesium', name: '마그네슘', amount: 150, unit: 'mg', upperLimit: 350 },
        { nutrientId: 'selenium', name: '셀레늄', amount: 55, unit: 'µg', upperLimit: 400 },
      ],
    },
    {
      supplementId: 503,
      name: '비타민 D',
      dailyCount: 1,
      times: ['저녁'],
      nutrients: [
        { nutrientId: 'vitamin-d', name: '비타민 D', amount: 30, unit: 'µg', upperLimit: 100 },
      ],
    },
  ];
}

export function mockSupplementsWithThreeExceeded(): Supplement[] {
  return mockSupplements().map((supplement, index) =>
    index === 0
      ? {
          ...supplement,
          nutrients: [
            ...supplement.nutrients,
            { nutrientId: 'vitamin-d', name: '비타민 D', amount: 60, unit: 'µg', upperLimit: 100 },
            { nutrientId: 'iron', name: '철', amount: 30, unit: 'mg', upperLimit: 45 },
          ],
        }
      : supplement,
  );
}

export function mockAddSupplement(payload: AddSupplementPayload): Supplement {
  return {
    supplementId: Date.now(),
    ...payload,
    nutrients: [],
  };
}
