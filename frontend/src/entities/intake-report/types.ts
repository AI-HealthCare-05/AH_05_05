/** POST /api/v1/intake-reports: app/dtos/intake_reports.py camelCase contract. */
export interface ReportSource {
  title: string; organization: string | null; url: string | null; evidenceLevel: string;
}
export interface IntakeReportCard {
  cardType: string; title: string; summary: string; relatedItems: string[]; checkItem: string; evidenceLevel: string; sources: ReportSource[];
}
export interface NutrientTotal {
  nutrientName: string; dailyTotal: string; includedProductNames: string[]; calculationStatus: string;
  amount?: string | null; unit?: string | null; referenceValue?: string | null;
  referenceKind?: 'RNI' | 'AI' | null; referencePercent?: string | null; unknownProductNames?: string[];
}
export interface ProductGuide {
  productName: string; oneLineSummary: string; generalRole: string | null; checkItem: string; sources: ReportSource[];
}
export interface CardSource {
  id: string; title: string; organization: string | null; url: string | null; evidenceLevel: string;
}
export interface CardSection { text: string; sourceIds: string[]; }
export interface CardDetail { label: string; text: string; sourceIds: string[]; }
export interface MedicationCard {
  itemId: number; productName: string; efficacy: CardSection; caution: CardSection;
  contraindication: CardSection; details: CardDetail[]; sourceIds: string[];
}
export interface InteractionCard {
  id: string; title: string; summary: string; action: string; relatedItemIds: number[];
  sourceIds: string[]; evidenceLevel: string; actionLevel: 'WARNING' | 'CHECK' | 'INFORMATION';
}
export interface OverlapCard {
  nutrientName: string; title: string; summary: string; action: string; productNames: string[];
  sourceIds: string[];
}
export interface LifestyleCard {
  id: string; category: string; title: string; summary: string; action: string;
  relatedItemIds: number[]; sourceIds: string[];
}
export interface IntakeReportCards {
  medications: MedicationCard[]; interactions: InteractionCard[]; overlaps: OverlapCard[];
  lifestyle: LifestyleCard[]; sources: CardSource[];
  originalTexts?: { key: string; label: string; text: string; sourceIds: string[] }[];
}
export interface IntakeReport {
  emailToken?: string | null;
  reportStatus: 'COMPLETED' | 'PARTIAL' | 'EMPTY';
  generatedAt: string;
  presentationVersion?: 'ai-report-v2' | 'ai-report-v11' | null;
  profileLabel?: string | null;
  basisNote?: string | null;
  /** Missing on legacy responses; the UI treats it as false. */
  fallbackUsed?: boolean;
  fallbackReason?: string | null;
  dataAvailability: { activeMedicationCount: number; activeSupplementCount: number; approvedInteractionRuleAvailable: boolean; ragEvidenceAvailable: boolean };
  executiveSummary: {
    reviewedProductCount: number; potentialRedundancyCount: number; interactionCheckCount: number; summary: string;
    summaryCards: { key: string; label: string; value: number; unit: string }[];
  };
  currentStack: { itemType: string; itemId: number; productName: string; ingredientName: string | null; registeredIntakeInfo: string; scheduledSlots: string[]; evidenceLevel: string }[];
  reviewCards: IntakeReportCard[];
  nutrientTotals: NutrientTotal[];
  chartData: { medicationCount: number; supplementCount: number; interactionCardCount: number; redundancyCardCount: number; cautionCardCount: number; missingInfoCardCount: number };
  productGuides: ProductGuide[];
  unverifiedItems: { itemType: string; title: string; message: string; relatedItems: string[]; nextStep: string }[];
  reportMarkdown: string;
  /** Optional so legacy and v2 responses remain backwards compatible. */
  cards?: IntakeReportCards | null;
}

export interface IntakeReportEmailJob {
  jobId: number;
  status: 'QUEUED' | 'PROCESSING' | 'RETRY_WAITING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
}
