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

export function mockAddSupplement(payload: AddSupplementPayload): Supplement {
  return {
    supplementId: Date.now(),
    ...payload,
    nutrients: [],
  };
}
