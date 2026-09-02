import type {
  FollowUpVisit,
  FollowUpVisitInput,
  FollowUpVisitListParams,
} from './types';

let nextId = 5;
let visits: FollowUpVisit[] = [
  {
    id: 1,
    visitDate: '2026-09-15',
    visitTime: null,
    hospital: '서울병원',
    createdAt: '2026-09-01T09:00:00+09:00',
    updatedAt: null,
  },
  {
    id: 2,
    visitDate: '2026-09-18',
    visitTime: '14:30',
    hospital: null,
    createdAt: '2026-09-01T09:10:00+09:00',
    updatedAt: null,
  },
  {
    id: 3,
    visitDate: '2026-08-20',
    visitTime: null,
    hospital: '온유의원',
    createdAt: '2026-08-01T09:00:00+09:00',
    updatedAt: null,
  },
  {
    id: 4,
    visitDate: '2026-09-16',
    visitTime: '10:30',
    hospital: '늘봄병원',
    createdAt: '2026-09-01T09:20:00+09:00',
    updatedAt: null,
  },
];

export function mockListFollowUpVisits(params?: FollowUpVisitListParams): FollowUpVisit[] {
  return visits
    .filter((visit) => !params?.startDate || visit.visitDate >= params.startDate)
    .filter((visit) => !params?.endDate || visit.visitDate <= params.endDate)
    .map((visit) => ({ ...visit }));
}

export function mockCreateFollowUpVisit(input: FollowUpVisitInput): FollowUpVisit {
  const visit: FollowUpVisit = {
    id: nextId,
    ...input,
    createdAt: new Date().toISOString(),
    updatedAt: null,
  };
  nextId += 1;
  visits = [...visits, visit];
  return { ...visit };
}

export function mockUpdateFollowUpVisit(
  visitId: number,
  input: FollowUpVisitInput,
): FollowUpVisit {
  const current = visits.find((visit) => visit.id === visitId);
  if (!current) throw new Error('진료일정을 찾지 못했어요.');
  const updated: FollowUpVisit = {
    ...current,
    ...input,
    updatedAt: new Date().toISOString(),
  };
  visits = visits.map((visit) => (visit.id === visitId ? updated : visit));
  return { ...updated };
}

export function mockDeleteFollowUpVisit(visitId: number): void {
  visits = visits.filter((visit) => visit.id !== visitId);
}
