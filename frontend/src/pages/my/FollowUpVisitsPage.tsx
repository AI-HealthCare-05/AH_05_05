import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import {
  createFollowUpVisit,
  deleteFollowUpVisit,
  listFollowUpVisits,
  updateFollowUpVisit,
  type FollowUpVisit,
  type FollowUpVisitInput,
} from '@/entities/follow-up-visit';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import { BottomTabbar, Button, Card, ErrorDialog, Header } from '@/shared/ui';
import { DeleteFollowUpVisitDialog } from './DeleteFollowUpVisitDialog';
import { FollowUpVisitSheet } from './FollowUpVisitSheet';

function todayString(): string {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${today.getFullYear()}-${month}-${day}`;
}

function compareVisits(left: FollowUpVisit, right: FollowUpVisit): number {
  const dateOrder = left.visitDate.localeCompare(right.visitDate);
  if (dateOrder !== 0) return dateOrder;
  const leftTime = left.visitTime ?? '24:00';
  const rightTime = right.visitTime ?? '24:00';
  return leftTime.localeCompare(rightTime) || left.id - right.id;
}

export function FollowUpVisitsPage() {
  const navigate = useNavigate();
  const [visits, setVisits] = useState<FollowUpVisit[]>([]);
  const [showPast, setShowPast] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selectedVisit, setSelectedVisit] = useState<FollowUpVisit | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FollowUpVisit | null>(null);
  const [deleting, setDeleting] = useState(false);
  const today = todayString();
  const upcomingVisits = visits.filter((visit) => visit.visitDate >= today);
  const pastVisits = visits.filter((visit) => visit.visitDate < today);
  const [upcomingVisit, ...laterVisits] = upcomingVisits;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    listFollowUpVisits(showPast ? undefined : { startDate: todayString() })
      .then((items) => {
        if (!cancelled) setVisits([...items].sort(compareVisits));
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '진료일정을 불러오지 못했어요.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showPast]);

  function openCreateSheet() {
    setSelectedVisit(null);
    setSheetOpen(true);
  }

  function openEditSheet(visit: FollowUpVisit) {
    setSelectedVisit(visit);
    setSheetOpen(true);
  }

  async function saveVisit(input: FollowUpVisitInput) {
    setActionError(null);
    try {
      const saved = selectedVisit
        ? await updateFollowUpVisit(selectedVisit.id, input)
        : await createFollowUpVisit(input);
      setVisits((current) =>
        [
          ...current.filter((visit) => visit.id !== saved.id),
          saved,
        ].sort(compareVisits),
      );
      setSelectedVisit(null);
      toast.success(selectedVisit ? '진료일정을 수정했어요.' : '진료일정을 추가했어요.');
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : '진료일정을 저장하지 못했어요.');
      throw error;
    }
  }

  async function removeVisit() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setActionError(null);
    try {
      await deleteFollowUpVisit(deleteTarget.id);
      setVisits((current) => current.filter((visit) => visit.id !== deleteTarget.id));
      setDeleteTarget(null);
      setSelectedVisit(null);
      toast.success('진료일정을 삭제했어요.');
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : '진료일정을 삭제하지 못했어요.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="진료일정" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col overflow-y-auto px-page-x pb-5 pt-8">
        {loadError ? (
          <Card title="진료일정을 불러오지 못했어요">{loadError}</Card>
        ) : loading && visits.length === 0 ? (
          <p className="text-sm text-muted-foreground">진료일정을 불러오는 중...</p>
        ) : upcomingVisits.length === 0 && pastVisits.length === 0 ? (
          <Card title="등록된 진료일정이 없어요">아래 버튼으로 일정을 추가해보세요.</Card>
        ) : (
          <div className="flex flex-col">
            <section aria-labelledby="upcoming-visits-title" className="flex flex-col">
              <h2 id="upcoming-visits-title" className="text-[22px] font-bold text-foreground">
                다가오는 일정
              </h2>
              {upcomingVisit ? (
                <VisitCard visit={upcomingVisit} onClick={() => openEditSheet(upcomingVisit)} />
              ) : (
                <p className="mt-4 text-sm text-muted-foreground">예정된 일정이 없어요.</p>
              )}
            </section>

            {laterVisits.length > 0 && (
              <section aria-labelledby="later-visits-title" className="mt-7 flex flex-col">
                <h2 id="later-visits-title" className="text-xl font-bold text-foreground">
                  이후 일정
                </h2>
                <div className="mt-3 overflow-hidden bg-card">
                  {laterVisits.map((visit, index) => (
                    <VisitRow
                      key={visit.id}
                      visit={visit}
                      divided={index > 0}
                      onClick={() => openEditSheet(visit)}
                    />
                  ))}
                </div>
              </section>
            )}

            {showPast && pastVisits.length > 0 && (
              <section aria-labelledby="past-visits-title" className="mt-7 flex flex-col">
                <h2 id="past-visits-title" className="text-xl font-bold text-foreground">
                  지난 일정
                </h2>
                <div className="mt-3 overflow-hidden bg-card">
                  {pastVisits.map((visit, index) => (
                    <VisitRow
                      key={visit.id}
                      visit={visit}
                      divided={index > 0}
                      onClick={() => openEditSheet(visit)}
                      past
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        <Button className="mt-auto" onClick={openCreateSheet}>
          진료일정 추가
        </Button>
        <button
          type="button"
          className="mt-2 min-h-touch self-center px-4 text-sm font-bold text-primary-strong"
          onClick={() => setShowPast((current) => !current)}
        >
          {showPast ? '예정된 일정만 보기' : '지난 일정 보기'}
        </button>
      </main>

      <BottomTabbar
        active="my"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />

      <FollowUpVisitSheet
        open={sheetOpen}
        visit={selectedVisit}
        onOpenChange={setSheetOpen}
        onSave={saveVisit}
        onDelete={(visit) => {
          setSheetOpen(false);
          setDeleteTarget(visit);
        }}
      />
      <DeleteFollowUpVisitDialog
        visit={deleteTarget}
        deleting={deleting}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        onConfirm={() => void removeVisit()}
      />
      <ErrorDialog
        open={actionError !== null}
        title="진료일정을 처리하지 못했어요"
        message={actionError ?? ''}
        retryLabel="확인"
        onRetry={() => setActionError(null)}
      />
    </div>
  );
}

function VisitCard({ visit, onClick }: { visit: FollowUpVisit; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-4 flex min-h-[148px] w-full flex-col rounded-[20px] border border-border bg-card p-4 text-left"
    >
      <span className="flex items-start justify-between gap-3">
        <span className="text-lg font-bold text-foreground">
          {formatVisitDate(visit.visitDate)}
        </span>
        <span className="shrink-0 text-[13px] font-bold text-primary-strong">
          {daysUntil(visit.visitDate)}
        </span>
      </span>
      <span className="mt-2 text-[15px] font-medium text-foreground">
        {visit.hospital ?? '병원 미정'} · {visit.visitTime ?? '시간 미정'}
      </span>
      <span className="mt-4 border-t border-border pt-3 text-[13px] text-muted-foreground">
        {visit.hospital ? `병원 ${visit.hospital}` : '병원과 시간을 정해보세요.'}
      </span>
    </button>
  );
}

function VisitRow({
  visit,
  divided,
  onClick,
  past = false,
}: {
  visit: FollowUpVisit;
  divided: boolean;
  onClick: () => void;
  past?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-h-16 w-full items-center gap-3 px-4 text-left ${
        divided ? 'border-t border-border' : ''
      }`}
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-bold text-foreground">
          {formatVisitDate(visit.visitDate)}
        </span>
        <span className="mt-1 block truncate text-[13px] text-muted-foreground">
          {visit.hospital ?? '병원 미정'} · {visit.visitTime ?? '시간 미정'}
        </span>
        {past && <span className="sr-only">지난 진료</span>}
      </span>
      <span aria-hidden className="text-xl text-disabled-foreground">›</span>
    </button>
  );
}

function formatVisitDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  const weekday = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'][
    new Date(year, month - 1, day).getDay()
  ];
  return `${month}월 ${day}일 ${weekday}`;
}

function daysUntil(value: string): string {
  const today = todayString();
  const start = new Date(`${today}T00:00:00`).getTime();
  const target = new Date(`${value}T00:00:00`).getTime();
  const days = Math.round((target - start) / 86_400_000);
  if (days <= 0) return '오늘';
  return `${days}일 남음`;
}
