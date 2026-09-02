import type {
  AddSupplementPayload,
  NutrientStandards,
  SearchSupplementProductsParams,
  Supplement,
  SupplementNutrientAmount,
  SupplementProduct,
  SupplementRanking,
  SupplementReview,
  SupplementReviewList,
  SupplementSearchPage,
  UpdateSupplementPayload,
} from './types';

const BASE_MULTIVITAMIN_NUTRIENTS: SupplementNutrientAmount[] = [
  { nutrientId: 'vitamin-a', name: '비타민 A', amount: 400, unit: 'µg RAE' },
  { nutrientId: 'vitamin-d', name: '비타민 D', amount: 10, unit: 'µg' },
  { nutrientId: 'iron', name: '철', amount: 6, unit: 'mg' },
];

function product(
  productId: string,
  productName: string,
  brand: string,
  manufacturer: string,
  packageAmount: string,
  recommendedDailyCount: number | null,
  ratingAverage: number | null = null,
  reviewCount = 0,
): SupplementProduct {
  return {
    productId,
    productName,
    brand,
    manufacturer,
    dosageForm: '정제',
    packageAmount,
    category: '종합비타민',
    servingDescription: `${recommendedDailyCount ?? 1}정`,
    servingSize: packageAmount,
    dailyFrequency: '1회',
    recommendedDoseAmount: recommendedDailyCount,
    doseUnit: '정',
    recommendedSlots: ['morning'],
    ratingAverage,
    reviewCount,
    nutrients: BASE_MULTIVITAMIN_NUTRIENTS.map((nutrient) => ({ ...nutrient })),
  };
}

/**
 * 건강기능식품 영양성분 표준데이터(2026.06) 형태를 따른 검색 목업입니다.
 * 실제 제품 동기화가 아니라 과다 결과·브랜드 검색·페이지네이션을 검증하는 고정 픽스처입니다.
 */
const SUPPLEMENT_PRODUCTS: SupplementProduct[] = [
  product('sp-001', '센트룸 실버 우먼', '센트룸', '한국화이자', '90정', 1, 4.2, 12),
  product('sp-002', '센트룸 실버 맨', '센트룸', '한국화이자', '90정', 1),
  product('sp-003', '고려은단 멀티비타민 올인원', '고려은단', '고려은단헬스케어', '60정', 2, 5, 1),
  product('sp-004', '종근당 아이커버 멀티비타민', '종근당', '종근당건강', '60정', 1),
  product('sp-005', '얼라이브 원스데일리 포 우먼', '얼라이브', '네이쳐스웨이', '60정', null),
  product('sp-006', '얼라이브 원스데일리 포 맨', '얼라이브', '네이쳐스웨이', '60정', 1),
  product('sp-007', '뉴트리코어 멀티비타민 미네랄', '뉴트리코어', '에프앤디넷', '60정', 2),
  product('sp-008', '오쏘몰 이뮨', '오쏘몰', '오쏘몰파마', '30정', 1, 4.7, 8),
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

const REGISTERED_MOCK_PRODUCT = product(
  'mock-501',
  '오메가3',
  'RxVita 목업',
  'RxVita',
  '60캡슐',
  1,
  4.8,
  32,
);

export function mockSupplementRanking(): SupplementRanking {
  return {
    title: '9월 면역력 관리',
    items: [
      { rank: 1, productId: 'mock-501', name: '오메가3', alreadyRegistered: false },
      {
        rank: 2,
        productId: 'sp-003',
        name: '고려은단 멀티비타민 올인원',
        alreadyRegistered: false,
      },
      { rank: 3, productId: 'sp-008', name: '오쏘몰 이뮨', alreadyRegistered: false },
      { rank: 4, productId: 'sp-009', name: '세노비스 트리플러스', alreadyRegistered: false },
      {
        rank: 5,
        productId: 'sp-015',
        name: '닥터린 멀티비타민 미네랄',
        alreadyRegistered: false,
      },
    ],
  };
}

export function mockSupplementProduct(productId: string): SupplementProduct {
  const found =
    productId === REGISTERED_MOCK_PRODUCT.productId
      ? REGISTERED_MOCK_PRODUCT
      : SUPPLEMENT_PRODUCTS.find((item) => item.productId === productId);
  if (!found) throw new Error('영양제를 찾지 못했어요.');
  return {
    ...found,
    nutrients: found.nutrients.map((nutrient) => ({ ...nutrient })),
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

const MOCK_REGISTRATION_COUNTS: Record<string, number> = {
  'sp-001': 18,
  'sp-002': 7,
  'sp-003': 25,
  'sp-008': 14,
};

function compareName(left: SupplementProduct, right: SupplementProduct): number {
  return left.productName.localeCompare(right.productName, 'ko-KR') || left.productId.localeCompare(right.productId);
}

export function mockSearchSupplementProducts({
  query,
  sort,
  offset = 0,
  limit = 20,
}: SearchSupplementProductsParams): SupplementSearchPage {
  const trimmedQuery = normalized(query);
  if (!trimmedQuery) return { items: [], total: 0, nextOffset: null };

  const matches = SUPPLEMENT_PRODUCTS.filter((productItem) =>
    [
      productItem.productName,
      productItem.brand,
      productItem.manufacturer,
      productItem.category,
    ].some((field) => normalized(field).includes(trimmedQuery)),
  ).sort((left, right) => {
    if (sort === undefined) {
      return (
        relevance(right, trimmedQuery) - relevance(left, trimmedQuery) ||
        SUPPLEMENT_PRODUCTS.indexOf(left) - SUPPLEMENT_PRODUCTS.indexOf(right)
      );
    }
    if (sort === 'registered') {
      return (
        (MOCK_REGISTRATION_COUNTS[right.productId] ?? 0) -
          (MOCK_REGISTRATION_COUNTS[left.productId] ?? 0) || compareName(left, right)
      );
    }
    if (sort === 'rating') {
      if (left.ratingAverage === null) return right.ratingAverage === null ? compareName(left, right) : 1;
      if (right.ratingAverage === null) return -1;
      return (
        right.ratingAverage - left.ratingAverage ||
        right.reviewCount - left.reviewCount ||
        compareName(left, right)
      );
    }
    if (sort === 'reviews') {
      return (
        right.reviewCount - left.reviewCount ||
        (right.ratingAverage ?? -1) - (left.ratingAverage ?? -1) ||
        compareName(left, right)
      );
    }
    return compareName(left, right);
  });
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
      productId: 'mock-501',
      name: '오메가3',
      doseAmount: 1,
      doseUnit: '정',
      slots: ['morning', 'evening'],
      score: 4,
      reviewBody: '꾸준히 챙겨 먹기 편해요.',
      note: '아침 식후에 먹기',
      nutrientDataAvailable: true,
      nutrients: [
        { nutrientId: 'vitamin-a', name: '비타민 A', amount: 300, unit: 'µg RAE' },
      ],
    },
    {
      supplementId: 502,
      productId: 'mock-502',
      name: '종합비타민',
      doseAmount: 1,
      doseUnit: '정',
      slots: ['morning'],
      score: null,
      reviewBody: null,
      note: null,
      nutrientDataAvailable: true,
      nutrients: [
        { nutrientId: 'vitamin-a', name: '비타민 A', amount: 2600, unit: 'µg RAE' },
        { nutrientId: 'vitamin-d', name: '비타민 D', amount: 20, unit: 'µg' },
        { nutrientId: 'iron', name: '철', amount: 18, unit: 'mg' },
        { nutrientId: 'calcium', name: '칼슘', amount: 400, unit: 'mg' },
        { nutrientId: 'vitamin-c', name: '비타민 C', amount: 100, unit: 'mg' },
        { nutrientId: 'zinc', name: '아연', amount: 8, unit: 'mg' },
        { nutrientId: 'magnesium', name: '마그네슘', amount: 150, unit: 'mg' },
        { nutrientId: 'selenium', name: '셀레늄', amount: 55, unit: 'µg' },
      ],
    },
    {
      supplementId: 503,
      productId: 'mock-503',
      name: '비타민 D',
      doseAmount: 1,
      doseUnit: '정',
      slots: ['evening'],
      score: null,
      reviewBody: null,
      note: null,
      nutrientDataAvailable: true,
      nutrients: [
        { nutrientId: 'vitamin-d', name: '비타민 D', amount: 30, unit: 'µg' },
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

export function mockNutrientStandards(): NutrientStandards {
  return {
    group: '남자',
    ageRange: '19-29세',
    byNutrientId: {
      protein: { rni: 65, ai: null, ul: null },
      carbohydrate: { rni: 130, ai: null, ul: null },
      fat: { rni: null, ai: null, ul: null },
      fiber: { rni: null, ai: 30, ul: null },
      calcium: { rni: 800, ai: null, ul: 3000 },
      iron: { rni: 8, ai: null, ul: 45 },
      phosphorus: { rni: 650, ai: null, ul: 3500 },
      potassium: { rni: null, ai: 3500, ul: null },
      sodium: { rni: null, ai: 1500, ul: 2300 },
      'vitamin-a': { rni: 800, ai: null, ul: 3000 },
      thiamine: { rni: 1.2, ai: null, ul: null },
      riboflavin: { rni: 1.5, ai: null, ul: null },
      niacin: { rni: 14, ai: null, ul: 35 },
      'vitamin-c': { rni: 100, ai: null, ul: 2000 },
      'vitamin-d': { rni: null, ai: 10, ul: 100 },
    },
  };
}

export function mockSupplementsWithThreeExceeded(): Supplement[] {
  return mockSupplements().map((supplement, index) =>
    index === 0
      ? {
          ...supplement,
          nutrients: [
            ...supplement.nutrients,
            { nutrientId: 'vitamin-d', name: '비타민 D', amount: 60, unit: 'µg' },
            { nutrientId: 'iron', name: '철', amount: 30, unit: 'mg' },
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
    productId: standardProduct?.productId ?? null,
    name: standardProduct?.productName ?? payload.name,
    doseAmount: payload.doseAmount,
    doseUnit: payload.doseUnit,
    slots: [...payload.slots],
    score: null,
    reviewBody: null,
    note: null,
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
    doseAmount: payload.doseAmount,
    slots: [...payload.slots],
    score: 'score' in payload ? (payload.score ?? null) : supplementStore[index].score,
    reviewBody:
      'reviewBody' in payload ? (payload.reviewBody ?? null) : supplementStore[index].reviewBody,
    note: 'note' in payload ? (payload.note ?? null) : supplementStore[index].note,
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

const MOCK_REVIEWS: SupplementReview[] = [
  { id: 9001, authorLabel: '김*훈', score: 5, reviewBody: '두 달째 꾸준히 먹고 있어요.', updatedAt: '2026-09-02T09:00:00', isMine: false, reportedByMe: false },
  { id: 9002, authorLabel: '김*훈', score: 4, reviewBody: '목 넘김이 편했어요.', updatedAt: '2026-09-01T18:00:00', isMine: false, reportedByMe: false },
  { id: 9003, authorLabel: '박*', score: 3, reviewBody: '포장이 간편해요.', updatedAt: '2026-08-31T12:00:00', isMine: false, reportedByMe: false },
  { id: 9004, authorLabel: '남**훈', score: 2, reviewBody: '저에게는 잘 맞지 않았어요.', updatedAt: '2026-08-30T12:00:00', isMine: false, reportedByMe: false },
  { id: 9005, authorLabel: 'K***g', score: null, reviewBody: '본문만 남긴 후기예요.', updatedAt: '2026-08-29T12:00:00', isMine: false, reportedByMe: false },
  { id: 9006, authorLabel: '이*영', score: 4, reviewBody: null, updatedAt: '2026-08-28T12:00:00', isMine: false, reportedByMe: false },
  { id: 9007, authorLabel: '황***이', score: 5, reviewBody: '제 후기예요.', updatedAt: '2026-08-27T12:00:00', isMine: true, reportedByMe: false },
  { id: 9008, authorLabel: '최*우', score: 4, reviewBody: '매일 챙겨 먹고 있어요.', updatedAt: '2026-08-26T12:00:00', isMine: false, reportedByMe: false },
  { id: 9009, authorLabel: '정*민', score: 5, reviewBody: '재구매했어요.', updatedAt: '2026-08-25T12:00:00', isMine: false, reportedByMe: false },
  { id: 9010, authorLabel: '한*진', score: 4, reviewBody: '크기가 적당해요.', updatedAt: '2026-08-24T12:00:00', isMine: false, reportedByMe: false },
  { id: 9011, authorLabel: '오*서', score: 3, reviewBody: '무난하게 먹고 있어요.', updatedAt: '2026-08-23T12:00:00', isMine: false, reportedByMe: false },
  { id: 9012, authorLabel: '윤*호', score: 5, reviewBody: '꾸준히 먹기 좋아요.', updatedAt: '2026-08-22T12:00:00', isMine: false, reportedByMe: false },
];

export function mockFetchSupplementReviews(
  productId: string,
  { offset, limit }: { offset: number; limit: number },
): SupplementReviewList {
  const source = productId === 'mock-501' ? MOCK_REVIEWS : [];
  return {
    items: source.slice(offset, offset + limit).map((review) => ({ ...review })),
    total: source.length,
    offset,
    limit,
    ratingAverage: source.length === 0 ? null : 4.1,
    reviewCount: source.filter((review) => review.score !== null).length,
  };
}

export function mockReportSupplementReview(registrationId: number): void {
  if (registrationId === 9004) throw new Error('잠시 후 다시 시도해주세요');
}
