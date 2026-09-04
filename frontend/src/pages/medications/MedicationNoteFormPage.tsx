import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  createMedicationNote,
  deleteMedicationNote,
  getMedicationNote,
  updateMedicationNote,
  type MedicationNote,
} from '@/entities/medication-note';
import {
  getMedicationOverviews,
  type MedicationOverview,
  type MedicationOverviewItem,
} from '@/entities/medication';
import { formatDateLabel } from '@/shared/lib/dateLabel';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import {
  BottomTabbar,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Header,
  Input,
} from '@/shared/ui';

interface NoteFormState {
  recordId: string;
  medicationId: string;
  takenAt: string;
  experience: string;
}

const EMPTY_FORM: NoteFormState = {
  recordId: '',
  medicationId: '',
  takenAt: '',
  experience: '',
};

function prescriptionLabel(overview: MedicationOverview): string {
  return `${formatDateLabel(overview.start.date, { includeYear: true })} 처방`;
}

function medicineLabel(medication: MedicationOverviewItem): string {
  return `${medication.name} ${medication.dose}`;
}

function toLocalDateTime(value: string): string {
  return value.length >= 16 ? value.slice(0, 16) : value;
}

function initialForm(note: MedicationNote | null): NoteFormState {
  return note
    ? {
        recordId: String(note.recordId),
        medicationId: String(note.medicationId),
        takenAt: toLocalDateTime(note.takenAt),
        experience: note.experience,
      }
    : EMPTY_FORM;
}

export function MedicationNoteFormPage() {
  const navigate = useNavigate();
  const { noteId } = useParams<{ noteId?: string }>();
  const editing = noteId !== undefined;
  const [note, setNote] = useState<MedicationNote | null>(null);
  const [overviews, setOverviews] = useState<MedicationOverview[] | null>(null);
  const [form, setForm] = useState<NoteFormState>(() => initialForm(null));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    const loadedNote = noteId ? getMedicationNote(decodeURIComponent(noteId)) : null;
    if (noteId && !loadedNote) {
      setLoadError('복약 메모를 찾지 못했어요.');
      return () => {
        cancelled = true;
      };
    }
    setNote(loadedNote);
    setForm(initialForm(loadedNote));
    getMedicationOverviews()
      .then((data) => {
        if (!cancelled) setOverviews(data.filter((overview) => overview.medications.length > 0));
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '처방 목록을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [noteId]);

  const selectedOverview = useMemo(
    () => overviews?.find((overview) => String(overview.recordId) === form.recordId) ?? null,
    [form.recordId, overviews],
  );
  const availableMedications = selectedOverview?.medications ?? [];
  const selectedMedication = availableMedications.find(
    (medication) => String(medication.medicationId) === form.medicationId,
  );
  const canSave =
    overviews !== null &&
    form.recordId !== '' &&
    form.medicationId !== '' &&
    form.takenAt !== '' &&
    form.experience.trim() !== '';

  function setField<K extends keyof NoteFormState>(key: K, value: NoteFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function chooseOverview(value: string) {
    const next = overviews?.find((overview) => String(overview.recordId) === value);
    setForm((current) => ({
      ...current,
      recordId: value,
      medicationId: next?.medications[0] ? String(next.medications[0].medicationId) : '',
    }));
  }

  function save() {
    if (!canSave || !selectedOverview || !selectedMedication) return;
    const payload = {
      recordId: Number(form.recordId),
      medicationId: Number(form.medicationId),
      takenAt: form.takenAt,
      experience: form.experience.trim(),
      prescriptionLabel: prescriptionLabel(selectedOverview),
      medicineLabel: medicineLabel(selectedMedication),
    };
    if (editing && noteId) {
      updateMedicationNote(decodeURIComponent(noteId), payload);
    } else {
      createMedicationNote(payload);
    }
    navigate('/medications/notes', { replace: true });
  }

  function remove() {
    if (!noteId) return;
    deleteMedicationNote(decodeURIComponent(noteId));
    setDeleteOpen(false);
    navigate('/medications/notes', { replace: true });
  }

  const title = editing ? '복약 메모 수정' : '복약 메모 작성';

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title={title} onBack={() => navigate('/medications/notes')} />
      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        {loadError ? (
          <p role="alert" className="text-sm text-danger-strong">
            {loadError}
          </p>
        ) : (
          <>
            <section className="flex flex-col gap-1">
              <h2 id="note-form-intro" className="text-xl font-bold text-foreground">
                복용 후 느낀 점을 기록해보세요
              </h2>
              <p className="text-sm text-muted-foreground">
                다음 진료 때 의료진과 함께 확인할 수 있어요.
              </p>
            </section>

            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1 text-sm font-bold text-foreground">
                처방
                <select
                  aria-label="처방"
                  value={form.recordId}
                  onChange={(event) => chooseOverview(event.target.value)}
                  className="h-control w-full rounded-input border border-input bg-card px-3.5 text-[length:var(--text-control)] font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="">처방을 선택해주세요</option>
                  {overviews?.map((overview) => (
                    <option key={overview.recordId} value={overview.recordId}>
                      {prescriptionLabel(overview)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-sm font-bold text-foreground">
                약
                <select
                  aria-label="약"
                  value={form.medicationId}
                  onChange={(event) => setField('medicationId', event.target.value)}
                  disabled={!selectedOverview}
                  className="h-control w-full rounded-input border border-input bg-card px-3.5 text-[length:var(--text-control)] font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:bg-muted-bg disabled:text-disabled-foreground"
                >
                  <option value="">약을 선택해주세요</option>
                  {availableMedications.map((medication) => (
                    <option key={medication.medicationId} value={medication.medicationId}>
                      {medicineLabel(medication)}
                    </option>
                  ))}
                </select>
              </label>

              <Input
                label="복용 일시"
                aria-label="복용 일시"
                type="datetime-local"
                value={form.takenAt}
                onChange={(event) => setField('takenAt', event.target.value)}
              />

              <label className="flex flex-col gap-1 text-sm font-bold text-foreground">
                복용 후 느낀 점
                <textarea
                  aria-label="복용 후 느낀 점"
                  value={form.experience}
                  onChange={(event) => setField('experience', event.target.value)}
                  rows={5}
                  placeholder="복용 후 몸의 변화를 적어주세요."
                  className="w-full resize-y rounded-input border border-input bg-card px-3.5 py-3 text-base font-normal text-foreground placeholder:text-tertiary-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </label>
            </div>
          </>
        )}

        <div className="mt-auto flex flex-col gap-2 pb-4">
          <Button onClick={save} disabled={!canSave}>
            {editing ? '수정 저장' : '저장'}
          </Button>
          {editing && (
            <Button variant="danger" onClick={() => setDeleteOpen(true)}>
              삭제
            </Button>
          )}
        </div>
      </main>
      <BottomTabbar
        active="medication"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent variant="sheet">
          <DialogHeader>
            <DialogTitle>이 메모를 삭제할까요?</DialogTitle>
            <DialogDescription>삭제한 복약 메모는 다시 복구할 수 없습니다.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)}>
              취소
            </Button>
            <Button variant="danger" onClick={remove}>
              삭제
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
