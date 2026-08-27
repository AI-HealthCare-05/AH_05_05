import type {
  AddSupplementPayload,
  SearchSupplementProductsParams,
  Supplement,
  SupplementNutrientAmount,
  SupplementProduct,
  SupplementRanking,
  SupplementRankingItem,
  SupplementSearchPage,
  UpdateSupplementPayload,
} from './types';

const BASE_MULTIVITAMIN_NUTRIENTS: SupplementNutrientAmount[] = [
  {
    nutrientId: 'vitamin-a', name: '비타민 A', amount: 400, unit: 'µg RAE',
    rni: 700, ai: null, ul: 3000,
  },
  {
    nutrientId: 'vitamin-d', name: '비타민 D', amount: 10, unit: 'µg',
    rni: 10, ai: null, ul: 100,
  },
  {
    nutrientId: 'iron', name: '철', amount: 6, unit: 'mg',
    rni: 10, ai: null, ul: 45,
  },
];

function product(
  productId: string,
  productName: string,
  brand: string,
  manufacturer: string,
  packageAmount: string,
  recommendedDailyCount: number | null,
): SupplementProduct {
  return {
    productId,
    productName,
    brand,
    manufacturer,
    dosageForm: '정제',
    packageAmount,
    category: '종합비타민',
    recommendedDailyCount,
    nutrients: BASE_MULTIVITAMIN_NUTRIENTS.map((nutrient) => ({ ...nutrient })),
  };
}

/**
 * 건강기능식품 영양성분 표준데이터(2026.06) 형태를 따른 검색 목업입니다.
 * 실제 제품 동기화가 아니라 과다 결과·브랜드 검색·페이지네이션을 검증하는 고정 픽스처입니다.
 */
const SUPPLEMENT_PRODUCTS: SupplementProduct[] = [
  product('sp-001', '센트룸 실버 우먼', '센트룸', '한국화이자', '90정', 1),
  product('sp-002', '센트룸 실버 맨', '센트룸', '한국화이자', '90정', 1),
  product('sp-003', '고려은단 멀티비타민 올인원', '고려은단', '고려은단헬스케어', '60정', 2),
  product('sp-004', '종근당 아이커버 멀티비타민', '종근당', '종근당건강', '60정', 1),
  product('sp-005', '얼라이브 원스데일리 포 우먼', '얼라이브', '네이쳐스웨이', '60정', null),
  product('sp-006', '얼라이브 원스데일리 포 맨', '얼라이브', '네이쳐스웨이', '60정', 1),
  product('sp-007', '뉴트리코어 멀티비타민 미네랄', '뉴트리코어', '에프앤디넷', '60정', 2),
  product('sp-008', '오쏘몰 이뮨', '오쏘몰', '오쏘몰파마', '30정', 1),
  product('sp-009', '세노비스 트리플러스', '세노비스', '사노피아벤티스', '100정', 2),
  product('sp-010', '솔가 여성용 멀티비타민', '솔가', '솔가코리아', '60정', 1),
  product('sp-011', 'GNC 메가맨', 'GNC', '동원F&B', '90정', 2),
  product('sp-012', 'GNC 우먼스 울트라 메가', 'GNC', '동원F&B', '90정', 2),
  product('sp-013', '네이쳐메이드 멀티 포 허', '네이쳐메이드', '한국오츠카제약', '90정', 1),
  product('sp-014', '네이쳐메이드 멀티 포 힘', '네이쳐메이드', '한국오츠카제약', '90정', 1),
  product('sp-015', '닥터린 멀티비타민 미네랄', '닥터린', '비즈메디', '60정', 1),
  product('sp-016', '락티브 올인원 멀티비타민', '락티브', '한미양행', '60정', 1),
  product('sp-017', '덴프스 트루바이타민', '덴프스', '에이치피오', '30정', 1),
  product('sp-018', 'JW중외제약 리얼메디 멀티', 'JW중외제약', '콜마코리아', '60정', 2),
  product('sp-019', '일양약품 프라임 멀티비타민', '일양약품', '일양약품', '90정', 1),
  product('sp-020', '유한양행 유한 멀티비타민', '유한양행', '유한건강생활', '60정', 1),
  product('sp-021', '동국제약 마이핏 멀티비타민', '동국제약', '동국제약', '60정', 1),
  product('sp-022', '안국건강 앤트리 멀티비타민', '안국건강', '안국건강', '60정', 1),
  product('sp-023', '대상웰라이프 뉴케어 멀티비타민', '뉴케어', '대상웰라이프', '60정', 1),
  product('sp-024', '풀무원 그린체 멀티비타민', '그린체', '풀무원건강생활', '60정', 2),
];

const SUPPLEMENT_RANKING_ITEMS: SupplementRankingItem[] = [
  {
    rank: 1,
    productId: 'P00123',
    productName: '오메가3',
    registeredCount: 1240,
    alreadyRegistered: false,
  },
  {
    rank: 2,
    productId: 'P00456',
    productName: '종합비타민',
    registeredCount: 980,
    alreadyRegistered: false,
  },
  {
    rank: 3,
    productId: 'P00777',
    productName: '비타민D',
    registeredCount: 870,
    alreadyRegistered: true,
  },
  {
    rank: 4,
    productId: 'P00901',
    productName: '마그네슘',
    registeredCount: 760,
    alreadyRegistered: false,
  },
  {
    rank: 5,
    productId: 'P01111',
    productName: '유산균',
    registeredCount: 650,
    alreadyRegistered: false,
  },
];

export function mockSupplementRanking(limit = 5): SupplementRanking {
  return {
    basis: '최근 7일 등록 수',
    periodDays: 7,
    items: SUPPLEMENT_RANKING_ITEMS.slice(0, limit).map((item) => ({ ...item })),
  };
}

function normalized(value: string): string {
  return value.toLocaleLowerCase('ko-KR').replace(/\s+/g, '');
}

function relevance(productItem: SupplementProduct, query: string): number {
  const fields = [
    productItem.productName,
    productItem.brand,
    productItem.manufacturer,
    productItem.category,
  ].map(normalized);
  const normalizedQuery = normalized(query);
  return fields.reduce((score, field, index) => {
    if (field === normalizedQuery) return score + 100 - index;
    if (field.startsWith(normalizedQuery)) return score + 60 - index;
    if (field.includes(normalizedQuery)) return score + 30 - index;
    return score;
  }, 0);
}

export function mockSearchSupplementProducts({
  query,
  offset = 0,
  limit = 20,
}: SearchSupplementProductsParams): SupplementSearchPage {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) return { items: [], total: 0, nextOffset: null };

  const matches = SUPPLEMENT_PRODUCTS
    .map((productItem, index) => ({ productItem, index, score: relevance(productItem, trimmedQuery) }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .map(({ productItem }) => productItem);
  const items = matches.slice(offset, offset + limit).map((productItem) => ({
    ...productItem,
    nutrients: productItem.nutrients.map((nutrient) => ({ ...nutrient })),
  }));
  const nextOffset = offset + items.length < matches.length ? offset + items.length : null;
  return { items, total: matches.length, nextOffset };
}

function initialSupplements(): Supplement[] {
  return [
    {
      supplementId: 501,
      name: '오메가3',
      dailyCount: 2,
      slots: ['morning', 'evening'],
      nutrientDataAvailable: true,
      nutrients: [
        {
          nutrientId: 'vitamin-a', name: '비타민 A', amount: 300, unit: 'µg RAE',
          rni: 700, ai: null, ul: 3000,
        },
      ],
    },
    {
      supplementId: 502,
      name: '종합비타민',
      dailyCount: 1,
      slots: ['morning'],
      nutrientDataAvailable: true,
      nutrients: [
        {
          nutrientId: 'vitamin-a', name: '비타민 A', amount: 2600, unit: 'µg RAE',
          rni: 700, ai: null, ul: 3000,
        },
        {
          nutrientId: 'vitamin-d', name: '비타민 D', amount: 20, unit: 'µg',
          rni: 10, ai: null, ul: 100,
        },
        {
          nutrientId: 'iron', name: '철', amount: 18, unit: 'mg',
          rni: 10, ai: null, ul: 45,
        },
        {
          nutrientId: 'calcium', name: '칼슘', amount: 400, unit: 'mg',
          rni: 700, ai: null, ul: 2500,
        },
        {
          nutrientId: 'vitamin-c', name: '비타민 C', amount: 100, unit: 'mg',
          rni: 100, ai: null, ul: null,
        },
        {
          nutrientId: 'zinc', name: '아연', amount: 8, unit: 'mg',
          rni: null, ai: null, ul: 35,
        },
        {
          nutrientId: 'magnesium', name: '마그네슘', amount: 150, unit: 'mg',
          rni: null, ai: 350, ul: 350,
        },
        {
          nutrientId: 'selenium', name: '셀레늄', amount: 55, unit: 'µg',
          rni: null, ai: null, ul: null,
        },
      ],
    },
    {
      supplementId: 503,
      name: '비타민 D',
      dailyCount: 1,
      slots: ['evening'],
      nutrientDataAvailable: true,
      nutrients: [
        {
          nutrientId: 'vitamin-d', name: '비타민 D', amount: 30, unit: 'µg',
          rni: 10, ai: null, ul: 100,
        },
      ],
    },
  ];
}

let supplementStore = initialSupplements();

function cloneSupplement(supplement: Supplement): Supplement {
  return {
    ...supplement,
    slots: [...supplement.slots],
    nutrients: supplement.nutrients.map((nutrient) => ({ ...nutrient })),
  };
}

export function mockSupplements(): Supplement[] {
  return supplementStore.map(cloneSupplement);
}

export function mockSupplementsWithThreeExceeded(): Supplement[] {
  return mockSupplements().map((supplement, index) =>
    index === 0
      ? {
          ...supplement,
          nutrients: [
            ...supplement.nutrients,
            {
              nutrientId: 'vitamin-d', name: '비타민 D', amount: 60, unit: 'µg',
              rni: 10, ai: null, ul: 100,
            },
            {
              nutrientId: 'iron', name: '철', amount: 30, unit: 'mg',
              rni: 10, ai: null, ul: 45,
            },
          ],
        }
      : supplement,
  );
}

export function mockAddSupplement(payload: AddSupplementPayload): Supplement {
  const standardProduct =
    payload.source === 'standard'
      ? SUPPLEMENT_PRODUCTS.find((productItem) => productItem.productId === payload.productId)
      : undefined;
  const added: Supplement = {
    supplementId: Date.now(),
    name: standardProduct?.productName ?? payload.name,
    dailyCount: payload.dailyCount,
    slots: [...payload.slots],
    nutrientDataAvailable: Boolean(standardProduct),
    nutrients: standardProduct
      ? standardProduct.nutrients.map((nutrient) => ({ ...nutrient }))
      : [],
  };
  supplementStore = [added, ...supplementStore];
  return cloneSupplement(added);
}

export function mockUpdateSupplement(
  supplementId: number,
  payload: UpdateSupplementPayload,
): Supplement {
  const index = supplementStore.findIndex((supplement) => supplement.supplementId === supplementId);
  if (index === -1) throw new Error('영양제를 찾지 못했어요.');
  const updated: Supplement = {
    ...supplementStore[index],
    dailyCount: payload.dailyCount,
    slots: [...payload.slots],
  };
  supplementStore = supplementStore.map((supplement, itemIndex) =>
    itemIndex === index ? updated : supplement,
  );
  return cloneSupplement(updated);
}

export function mockStopSupplement(supplementId: number): void {
  const exists = supplementStore.some((supplement) => supplement.supplementId === supplementId);
  if (!exists) throw new Error('영양제를 찾지 못했어요.');
  supplementStore = supplementStore.filter((supplement) => supplement.supplementId !== supplementId);
}
