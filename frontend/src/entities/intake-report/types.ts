/** POST /api/v1/intake-reports: app/dtos/intake_reports.py camelCase contract. */
export interface ReportSource {
  title: string; organization: string | null; url: string | null; evidenceLevel: string;
}
export interface IntakeReport {
  reportStatus: 'COMPLETED' | 'PARTIAL' | 'EMPTY';
  generatedAt: string;
  dataAvailability: { activeMedicationCount: number; activeSupplementCount: number; approvedInteractionRuleAvailable: boolean; ragEvidenceAvailable: boolean };
  executiveSummary: {
    reviewedProductCount: number; potentialRedundancyCount: number; interactionCheckCount: number; summary: string;
    summaryCards: { key: string; label: string; value: number; unit: string }[];
  };
  currentStack: { itemType: string; itemId: number; productName: string; ingredientName: string | null; registeredIntakeInfo: string; scheduledSlots: string[]; evidenceLevel: string }[];
  reviewCards: { cardType: string; title: string; summary: string; relatedItems: string[]; checkItem: string; evidenceLevel: string; sources: ReportSource[] }[];
  nutrientTotals: { nutrientName: string; dailyTotal: string; includedProductNames: string[]; calculationStatus: string }[];
  chartData: { medicationCount: number; supplementCount: number; interactionCardCount: number; redundancyCardCount: number; cautionCardCount: number; missingInfoCardCount: number };
  productGuides: { productName: string; oneLineSummary: string; generalRole: string | null; checkItem: string; sources: ReportSource[] }[];
  unverifiedItems: { itemType: string; title: string; message: string; relatedItems: string[]; nextStep: string }[];
  reportMarkdown: string;
}
