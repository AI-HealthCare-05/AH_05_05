import { useEffect, useState } from 'react';
import { CalendarDays, Plus } from 'lucide-react';
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
import { Card, ErrorDialog, Header } from '@/shared/ui';
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
      <Header
        title="진료일정"
        onBack={() => navigate(-1)}
        right={
          <button
            type="button"
            aria-label="진료일정 추가"
            className="flex size-touch items-center justify-center text-primary-strong"
            onClick={openCreateSheet}
          >
            <Plus aria-hidden className="size-6" />
          </button>
        }
      />
      <main className="flex flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
        <button
          type="button"
          className="min-h-touch self-start text-sm font-bold text-primary-strong"
          onClick={() => setShowPast((current) => !current)}
        >
          {showPast ? '예정된 일정만 보기' : '지난 일정 보기'}
        </button>

        {loadError ? (
          <Card title="진료일정을 불러오지 못했어요">{loadError}</Card>
        ) : loading && visits.length === 0 ? (
          <p className="text-sm text-muted-foreground">진료일정을 불러오는 중...</p>
        ) : visits.length === 0 ? (
          <Card title="등록된 진료일정이 없어요">오른쪽 위 + 버튼으로 일정을 추가해보세요.</Card>
        ) : (
          <section aria-label="진료일정 목록" className="flex flex-col gap-3">
            {visits.map((visit) => (
              <button
                key={visit.id}
                type="button"
                onClick={() => openEditSheet(visit)}
                className="flex min-h-24 w-full items-center gap-3 rounded-card bg-card p-4 text-left shadow-card"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-pill bg-primary-bg text-primary-strong">
                  <CalendarDays aria-hidden className="size-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-base font-bold text-foreground">
                    {formatVisitDate(visit.visitDate)}
                  </span>
                  <span className="mt-1 block truncate text-sm text-muted-foreground">
                    {visit.hospital ?? '병원 미정'} · {visit.visitTime ?? '시간 미정'}
                  </span>
                  {visit.visitDate < todayString() && (
                    <span className="mt-1 block text-xs font-bold text-muted-foreground">지난 진료</span>
                  )}
                </span>
                <span aria-hidden className="text-xl text-disabled-foreground">›</span>
              </button>
            ))}
          </section>
        )}
      </main>

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

function formatVisitDate(value: string): string {
  const [, month, day] = value.split('-').map(Number);
  return month && day ? `${month}월 ${day}일` : value;
}
