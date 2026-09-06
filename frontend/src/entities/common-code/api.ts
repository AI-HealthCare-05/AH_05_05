import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockListCommonCodes } from './api.mock';
import type { CommonCodeItem } from './types';

interface CommonCodeLookupItemSnakeCase {
  detail_code: string;
  detail_name: string;
  sort_order: number;
}

interface CommonCodeLookupItemCamelCase {
  detailCode: string;
  detailName: string;
  sortOrder: number;
}

interface CommonCodeLookupResponse {
  items: Array<CommonCodeLookupItemSnakeCase | CommonCodeLookupItemCamelCase>;
}

function mapCommonCodeItem(
  item: CommonCodeLookupItemSnakeCase | CommonCodeLookupItemCamelCase,
): CommonCodeItem {
  if ('detailCode' in item) {
    return {
      detailCode: item.detailCode,
      detailName: item.detailName,
      sortOrder: item.sortOrder,
    };
  }
  return {
    detailCode: item.detail_code,
    detailName: item.detail_name,
    sortOrder: item.sort_order,
  };
}

function sortCommonCodeItems(items: CommonCodeItem[]): CommonCodeItem[] {
  return items.sort((left, right) => left.sortOrder - right.sortOrder);
}

export async function listCommonCodes(
  category: string,
  groupCode: string,
): Promise<CommonCodeItem[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockListCommonCodes(category, groupCode);
  }
  const response = await http.get<CommonCodeLookupResponse>(
    `/v1/common-codes/${encodeURIComponent(category)}/${encodeURIComponent(groupCode)}`,
  );
  return sortCommonCodeItems(response.items.map(mapCommonCodeItem));
}
