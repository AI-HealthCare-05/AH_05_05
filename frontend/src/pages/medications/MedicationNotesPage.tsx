import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router';
import { listMedicationNotes, type MedicationNote } from '@/entities/medication-note';
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
  const [notes, setNotes] = useState<MedicationNote[] | null>(null);

  useEffect(() => {
    setNotes(listMedicationNotes());
  }, []);

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
            <h2 id="medication-notes-title" className="text-xl font-bold text-foreground">
              복약 메모 {notes ? `${notes.length}개` : ''}
            </h2>
          </div>
          {notes === null ? (
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
                  aria-label={`${note.medicineLabel} ${note.experience}`}
                  className="flex min-h-28 w-full flex-col gap-2 rounded-card bg-card p-4 text-left shadow-card transition-colors hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => navigate(`/medications/notes/${encodeURIComponent(note.id)}`)}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <span className="tnum">{noteDateLabel(note.takenAt)}</span>
                    <span className="rounded-pill bg-primary-bg px-2.5 py-1 font-bold text-primary-strong">
                      {note.prescriptionLabel}
                    </span>
                  </div>
                  <p className="font-bold text-foreground">{note.medicineLabel}</p>
                  <p className="text-sm text-muted-foreground">{note.experience}</p>
                </button>
              ))}
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
