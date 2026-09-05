import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router';
import {
  listMedicationNotes,
  type MedicationNote,
  type MedicationNotePage,
} from '@/entities/medication-note';
import { useSession } from '@/app/SessionContext';
import { formatDateLabel } from '@/shared/lib/dateLabel';
import { BottomTabbar, Button, Card, Header } from '@/shared/ui';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';

function noteDateLabel(value: string): string {
  const date = value.slice(0, 10);
  const time = value.slice(11, 16);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return value;
  return `${formatDateLabel(date)} ${time}`;
}

export function MedicationNotesPage() {
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const [page, setPage] = useState<MedicationNotePage | null>(null);
  const [initialLoadError, setInitialLoadError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPage(null);
    setInitialLoadError(null);
    setLoadMoreError(null);
    listMedicationNotes()
      .then((nextPage) => {
        if (cancelled) return;
        setPage(nextPage);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setInitialLoadError(error instanceof Error ? error.message : '복약 메모를 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [principalKey]);

  async function loadMore() {
    if (!page?.nextCursor || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const nextPage = await listMedicationNotes({ cursor: page.nextCursor });
      setPage((current) => {
        if (!current) return nextPage;
        const existingIds = new Set(current.items.map((note) => note.id));
        return {
          items: [...current.items, ...nextPage.items.filter((note) => !existingIds.has(note.id))],
          total: nextPage.total,
          nextCursor: nextPage.nextCursor,
        };
      });
    } catch (error: unknown) {
      setLoadMoreError(error instanceof Error ? error.message : '복약 메모를 더 불러오지 못했어요.');
    } finally {
      setLoadingMore(false);
    }
  }

  const notes = page?.items ?? [];
  const notesHeading = page ? `복약 메모 ${page.total}개` : '복약 메모 목록';

  function prescriptionLabel(note: MedicationNote): string {
    if (note.careEpisodeAlias) return note.careEpisodeAlias;
    if (note.careEpisodeStartDate) {
      return `${formatDateLabel(note.careEpisodeStartDate, { includeYear: true })} 처방`;
    }
    return note.careEpisodeTitle;
  }

  function medicineLabel(note: MedicationNote): string {
    if (note.medicationId === null) return '처방 전체';
    return note.medication
      ? `${note.medication.name} ${note.medication.dose ?? ''}`.trim()
      : '삭제된 약';
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="복약 메모" onBack={() => navigate('/medications')} />
      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        <Button
          className="self-start"
          fullWidth={false}
          onClick={() => navigate('/medications/notes/new')}
        >
          <Plus aria-hidden className="mr-1 size-4" />
          새 메모 작성
        </Button>

        <section className="flex flex-col gap-3" aria-labelledby="medication-notes-title">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="medication-notes-title" aria-label={notesHeading} className="text-xl font-bold text-foreground">
              {notesHeading}
            </h2>
          </div>
          {initialLoadError ? (
            <p role="alert" className="text-sm text-danger-strong">{initialLoadError}</p>
          ) : page === null ? (
            <div role="status" aria-label="복약 메모 불러오는 중" className="min-h-32 animate-pulse rounded-card bg-muted-bg" />
          ) : notes.length === 0 ? (
            <Card className="p-5">
              <p>복용 후 느낀 점을 남겨두면 다음 진료 때 도움이 돼요.</p>
            </Card>
          ) : (
            <div className="flex flex-col gap-3">
              {notes.map((note) => (
                <button
                  key={note.id}
                  type="button"
                  aria-label={`${medicineLabel(note)} ${note.body}`}
                  className="flex min-h-28 w-full flex-col gap-2 rounded-card bg-card p-4 text-left shadow-card transition-colors hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => navigate(`/medications/notes/${encodeURIComponent(note.id)}`)}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <span className="tnum">{noteDateLabel(note.dosedAt)}</span>
                    <span className="rounded-pill bg-primary-bg px-2.5 py-1 font-bold text-primary-strong">
                      {prescriptionLabel(note)}
                    </span>
                  </div>
                  <p className="font-bold text-foreground">{medicineLabel(note)}</p>
                  <p className="truncate text-sm text-muted-foreground">{note.body}</p>
                </button>
              ))}
              {loadMoreError && (
                <p role="alert" className="text-sm text-danger-strong">{loadMoreError}</p>
              )}
              {page.nextCursor && (
                <Button
                  variant="secondary"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  aria-busy={loadingMore}
                >
                  {loadingMore ? '불러오는 중...' : '더 보기'}
                </Button>
              )}
            </div>
          )}
        </section>
      </main>
      <BottomTabbar
        active="medication"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
    </div>
  );
}
