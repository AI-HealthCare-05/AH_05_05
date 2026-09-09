export interface FollowUpVisit {
  id: number;
  visitDate: string;
  visitTime: string | null;
  hospital: string | null;
  createdAt: string;
  updatedAt: string | null;
}

export interface FollowUpVisitInput {
  visitDate: string;
  visitTime: string | null;
  hospital: string;
}

export interface FollowUpVisitListParams {
  startDate?: string;
  endDate?: string;
}
