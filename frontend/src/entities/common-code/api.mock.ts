import type { CommonCodeItem } from './types';

const MOCK_COMMON_CODES: Record<string, CommonCodeItem[]> = {
  'CHAT:P_REASON': [
    { detailCode: 'P01', detailName: '최신', sortOrder: 0 },
    { detailCode: 'P02', detailName: '정확함', sortOrder: 1 },
    { detailCode: 'P03', detailName: '도움이 됨', sortOrder: 2 },
    { detailCode: 'P04', detailName: '지침을 따름', sortOrder: 3 },
    { detailCode: 'P05', detailName: '우수한 출처', sortOrder: 4 },
  ],
  'CHAT:N_REASON': [
    { detailCode: 'N01', detailName: '오래된 정보', sortOrder: 1 },
    { detailCode: 'N02', detailName: '부정확함', sortOrder: 2 },
    { detailCode: 'N03', detailName: '잘못된 출처', sortOrder: 3 },
    { detailCode: 'N04', detailName: '너무 김', sortOrder: 4 },
    { detailCode: 'N05', detailName: '너무 짧음', sortOrder: 5 },
  ],
};

export function mockListCommonCodes(category: string, groupCode: string): CommonCodeItem[] {
  const key = `${category.trim().toUpperCase()}:${groupCode.trim().toUpperCase()}`;
  return (MOCK_COMMON_CODES[key] ?? [])
    .map((item) => ({ ...item }))
    .sort((left, right) => left.sortOrder - right.sortOrder);
}
