// Copied from design-plans/447-implementation/remaining-reports-audit.mjs so
// implementation verification exercises the exact audited long-content shapes.
const longMedication = '아세트아미노펜서방정650밀리그램과리바록사반정10밀리그램복합확인용긴제품명';
const longSupplement = '프리미엄멀티비타민미네랄오메가쓰리프로바이오틱스복합영양제';
const longCopy = '등록한 복용 정보와 공개된 제품 안내를 기준으로 확인했어요. 복용을 바꾸기 전에는 의료진 또는 약사와 상의하세요. '.repeat(4).trim();

export const remainingBaseReport = {
  reportStatus: 'COMPLETED',
  generatedAt: '2026-09-13T03:00:00Z',
  dataAvailability: { activeMedicationCount: 2, activeSupplementCount: 2, approvedInteractionRuleAvailable: true, ragEvidenceAvailable: true },
  executiveSummary: {
    reviewedProductCount: 4,
    potentialRedundancyCount: 1,
    interactionCheckCount: 2,
    summary: longCopy,
    summaryCards: [
      { key: 'reviewed', label: '검토한 제품', value: 4, unit: '개' },
      { key: 'interaction', label: '함께 확인할 상호작용', value: 2, unit: '건' },
    ],
  },
  currentStack: [
    { itemType: 'MEDICATION', itemId: 71, productName: longMedication, ingredientName: '아세트아미노펜', registeredIntakeInfo: '하루 2회 1정씩 식후 복용', scheduledSlots: ['MORNING', 'EVENING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'MEDICATION', itemId: 72, productName: '리바록사반정 10mg', ingredientName: '리바록사반', registeredIntakeInfo: '하루 1회 저녁 식후', scheduledSlots: ['EVENING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'SUPPLEMENT', itemId: 73, productName: longSupplement, ingredientName: null, registeredIntakeInfo: '하루 1캡슐', scheduledSlots: ['EVENING'], evidenceLevel: 'REGISTERED_INTAKE' },
    { itemType: 'SUPPLEMENT', itemId: 74, productName: '비타민 D 2000 IU', ingredientName: null, registeredIntakeInfo: '하루 1정', scheduledSlots: [], evidenceLevel: 'REGISTERED_INTAKE' },
  ],
  reviewCards: [
    { cardType: 'INTERACTION', title: `${longMedication} 함께 복용 확인`, summary: longCopy, relatedItems: [longMedication, '리바록사반정 10mg'], checkItem: '현재 조합과 용량을 의료진에게 확인하세요.', evidenceLevel: 'APPROVED_RULE', sources: [{ title: '의약품 안전사용 안내', organization: '공공기관', url: 'https://example.com/guide', evidenceLevel: 'APPROVED_RULE' }] },
  ],
  nutrientTotals: [
    { nutrientName: '비타민 D', dailyTotal: '50μg', includedProductNames: [longSupplement, '비타민 D 2000 IU'], calculationStatus: 'PARTIAL', amount: '50', unit: 'μg', referenceValue: '10', referenceKind: 'AI', referencePercent: '500', unknownProductNames: [longSupplement] },
  ],
  chartData: { medicationCount: 2, supplementCount: 2, interactionCardCount: 2, redundancyCardCount: 1, cautionCardCount: 1, missingInfoCardCount: 1 },
  productGuides: [{ productName: longMedication, oneLineSummary: longCopy, generalRole: '통증과 발열 완화에 사용하는 일반적인 의약품 안내예요.', checkItem: '제품 설명서와 의료진의 지시를 우선하세요.', sources: [] }],
  unverifiedItems: [{ itemType: 'MISSING_AMOUNT', title: `${longSupplement} 함량 미확인`, message: '일부 함량을 확인하지 못해 합계에서 제외했어요.', relatedItems: [longSupplement], nextStep: '제품 라벨을 확인하세요.' }],
  reportMarkdown: `# 상세 복용 보고서\n\n${longCopy}\n\n| 제품 | 등록 정보 | 확인 사항 |\n| --- | --- | --- |\n| ${longMedication} | 하루 2회 | 전문가와 확인하세요. |`,
};

export const remainingV11Report = {
  ...remainingBaseReport,
  presentationVersion: 'ai-report-v11',
  profileLabel: `만성질환 복용 관리 · ${longSupplement}`,
  basisNote: '등록한 복용 정보와 확인 가능한 공개 근거만 사용했어요. 정보가 없다는 것이 안전하다는 뜻은 아니에요.',
  cards: {
    medications: [
      { itemId: 71, productName: longMedication, efficacy: { text: longCopy, sourceIds: ['med'] }, caution: { text: `즉시 복용을 중단하라는 뜻이 아니에요. ${longCopy}`, sourceIds: ['med'] }, contraindication: { text: longCopy, sourceIds: ['med'] }, details: [{ label: '등록한 복용 정보', text: '하루 2회 1정씩 식후 복용', sourceIds: [] }], sourceIds: ['med'] },
      { itemId: 72, productName: '리바록사반정 10mg', efficacy: { text: '확인된 효능 설명', sourceIds: ['med'] }, caution: { text: '확인된 주의 설명', sourceIds: ['med'] }, contraindication: { text: '확인된 금기 설명', sourceIds: ['med'] }, details: [], sourceIds: ['med'] },
    ],
    interactions: [
      { id: 'warning', title: `${longMedication} 함께 복용 시 확인`, summary: longCopy, action: '복용 전 의료진 또는 약사에게 현재 조합과 용량을 확인하세요.', relatedItemIds: [71, 72], sourceIds: ['med'], evidenceLevel: 'APPROVED_RULE', actionLevel: 'WARNING' },
      { id: 'guide', title: '공개 제품 안내 확인', summary: longCopy, action: '개인 조합에 해당하는지는 전문가에게 확인하세요.', relatedItemIds: [71], sourceIds: ['public'], evidenceLevel: 'PUBLIC_GUIDE', actionLevel: 'CHECK' },
    ],
    overlaps: [{ nutrientName: '비타민 D', title: `${longSupplement} 외 1개 제품에 비타민 D가 들어 있어요`, summary: longCopy, action: '추가 제품 전에는 각 제품 표시량을 확인하세요.', productNames: [longSupplement, '비타민 D 2000 IU'], sourceIds: ['public'] }],
    lifestyle: [{ id: 'habit', category: '복용 습관', title: '등록한 시간과 실제 복용 시간을 함께 기록하세요', summary: longCopy, action: '처방과 제품 안내를 우선하세요.', relatedItemIds: [71], sourceIds: ['public'] }],
    sources: [
      { id: 'med', title: '의약품 안전사용 안내', organization: '공공기관', url: 'https://example.com/medicine', evidenceLevel: 'APPROVED_RULE' },
      { id: 'public', title: '공개 복용 안내', organization: null, url: 'https://example.com/guide', evidenceLevel: 'PUBLIC_GUIDE' },
    ],
    originalTexts: [{ key: 'medication/71/caution', label: `${longMedication} · 주의`, text: longCopy, sourceIds: ['med'] }],
  },
};

export const remainingEmptyReport = {
  ...remainingBaseReport,
  reportStatus: 'EMPTY',
  currentStack: [],
  reviewCards: [],
  nutrientTotals: [],
  productGuides: [],
  unverifiedItems: [],
  reportMarkdown: '',
  dataAvailability: { activeMedicationCount: 0, activeSupplementCount: 0, approvedInteractionRuleAvailable: false, ragEvidenceAvailable: false },
  executiveSummary: { reviewedProductCount: 0, potentialRedundancyCount: 0, interactionCheckCount: 0, summary: '등록 정보가 없어요.', summaryCards: [] },
  chartData: { medicationCount: 0, supplementCount: 0, interactionCardCount: 0, redundancyCardCount: 0, cautionCardCount: 0, missingInfoCardCount: 0 },
};
