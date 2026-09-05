import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useSession } from '@/app/SessionContext';
import {
  createMedicationNote,
  deleteMedicationNote,
  getMedicationNote,
  updateMedicationNote,
  type MedicationNote,
  type MedicationNoteMedication,
} from '@/entities/medication-note';
import {
  getMedicationOverviews,
  type MedicationOverview,
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

interface NoteEpisodeOption {
  id: number;
  title: string;
  alias: string | null;
  startDate: string | null;
  status: string;
  medications: MedicationNoteMedication[];
}

const DELETED_MEDICATION_ID = '__deleted__';

const EMPTY_FORM: NoteFormState = {
  recordId: '',
  medicationId: '',
  takenAt: '',
  experience: '',
};

function prescriptionLabel(episode: NoteEpisodeOption): string {
  if (episode.alias) return episode.alias;
  if (episode.startDate) {
    return `${formatDateLabel(episode.startDate, { includeYear: true })} 처방`;
  }
  return episode.title;
}

function medicineLabel(medication: MedicationNoteMedication): string {
  return `${medication.name} ${medication.dose ?? ''}`.trim();
}

function toLocalDateTime(value: string): string {
  return value.length >= 16 ? value.slice(0, 16) : value;
}

function initialForm(note: MedicationNote | null): NoteFormState {
  return note
    ? {
        recordId: String(note.careEpisodeId),
        medicationId: note.medicationId === null ? '' : String(note.medicationId),
        takenAt: toLocalDateTime(note.dosedAt),
        experience: note.body,
      }
    : EMPTY_FORM;
}

function episodeFromOverview(overview: MedicationOverview): NoteEpisodeOption {
  return {
    id: overview.recordId,
    title: `${overview.start.date} 조제약 복약안내`,
    alias: overview.alias ?? null,
    startDate: overview.start.date,
    status: overview.isFinished ? 'COMPLETED' : 'ACTIVE',
    medications: overview.medications.map((medication) => ({
      id: medication.medicationId,
      name: medication.name,
      dose: medication.dose || null,
    })),
  };
}

function episodeFromNote(note: MedicationNote): NoteEpisodeOption {
  return {
    id: note.careEpisodeId,
    title: note.careEpisodeTitle,
    alias: note.careEpisodeAlias,
    startDate: note.careEpisodeStartDate,
    status: note.careEpisodeStatus,
    medications: note.availableMedications,
  };
}

export function MedicationNoteFormPage() {
  const navigate = useNavigate();
  const { noteId } = useParams<{ noteId?: string }>();
  const { principalKey } = useSession();
  const editing = noteId !== undefined;
  const [note, setNote] = useState<MedicationNote | null>(null);
  const [episodes, setEpisodes] = useState<NoteEpisodeOption[] | null>(null);
  const [form, setForm] = useState<NoteFormState>(() => initialForm(null));
  const [initialLoadError, setInitialLoadError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const savingRef = useRef(false);
  const deletingRef = useRef(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setInitialLoadError(null);
    setMutationError(null);
    setEpisodes(null);
    const noteRequest = noteId
      ? getMedicationNote(decodeURIComponent(noteId))
      : Promise.resolve(null);
    const overviewRequest = getMedicationOverviews();
    Promise.allSettled([noteRequest, overviewRequest])
      .then(([noteResult, overviewResult]) => {
        if (cancelled) return;
        if (noteResult.status === 'rejected') {
          setInitialLoadError(
            noteResult.reason instanceof Error
              ? noteResult.reason.message
              : '복약 메모를 불러오지 못했어요.',
          );
          return;
        }
        const loadedNote = noteResult.value;
        if (noteId && !loadedNote) {
          setInitialLoadError('복약 메모를 찾지 못했어요.');
          return;
        }
        if (overviewResult.status === 'rejected' && !loadedNote) {
          setInitialLoadError(
            overviewResult.reason instanceof Error
              ? overviewResult.reason.message
              : '처방 목록을 불러오지 못했어요.',
          );
          return;
        }
        const activeEpisodes = overviewResult.status === 'fulfilled'
          ? overviewResult.value
              .filter((overview) => overview.medications.length > 0)
              .map(episodeFromOverview)
          : [];
        const originalEpisode = loadedNote ? episodeFromNote(loadedNote) : null;
        const nextEpisodes = originalEpisode
          ? [
              originalEpisode,
              ...activeEpisodes.filter((episode) => episode.id !== originalEpisode.id),
            ]
          : activeEpisodes;
        setNote(loadedNote);
        setEpisodes(nextEpisodes);
        const nextForm = initialForm(loadedNote);
        if (
          loadedNote &&
          loadedNote.medicationId !== null &&
          !originalEpisode?.medications.some((medication) => medication.id === loadedNote.medicationId)
        ) {
          nextForm.medicationId = DELETED_MEDICATION_ID;
        }
        setForm(nextForm);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setInitialLoadError(error instanceof Error ? error.message : '처방 목록을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [noteId, principalKey]);

  const selectedEpisode = useMemo(
    () => episodes?.find((episode) => String(episode.id) === form.recordId) ?? null,
    [episodes, form.recordId],
  );
  const availableMedications = selectedEpisode?.medications ?? [];
  const deletedMedication =
    editing && note?.medicationId !== null && note?.medicationId !== undefined &&
    !availableMedications.some((medication) => medication.id === note.medicationId)
      ? { id: note.medicationId, name: '삭제된 약', dose: null }
      : null;
  const medicationOptions = deletedMedication
    ? [deletedMedication, ...availableMedications]
    : availableMedications;
  const selectedMedication = medicationOptions.find(
    (medication) => String(medication.id) === form.medicationId,
  );
  const canSave =
    episodes !== null &&
    selectedEpisode !== null &&
    form.recordId !== '' &&
    form.takenAt !== '' &&
    form.experience.trim() !== '' &&
    (form.medicationId === '' || selectedMedication !== undefined);

  function setField<K extends keyof NoteFormState>(key: K, value: NoteFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function chooseOverview(value: string) {
    if (editing) return;
    const next = episodes?.find((episode) => String(episode.id) === value);
    setForm((current) => ({
      ...current,
      recordId: value,
      medicationId: next?.medications[0] ? String(next.medications[0].id) : '',
    }));
  }

  async function save() {
    if (!canSave || !selectedEpisode || savingRef.current || deletingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setMutationError(null);
    try {
      if (editing && noteId) {
        await updateMedicationNote(decodeURIComponent(noteId), {
          medicationId:
            form.medicationId === '' || form.medicationId === DELETED_MEDICATION_ID
              ? null
              : Number(form.medicationId),
          dosedAt: form.takenAt,
          body: form.experience.trim(),
        });
      } else {
        await createMedicationNote({
          careEpisodeId: Number(form.recordId),
          ...(form.medicationId !== '' ? { medicationId: Number(form.medicationId) } : {}),
          dosedAt: form.takenAt,
          body: form.experience.trim(),
        });
      }
      navigate('/medications/notes', { replace: true });
    } catch (error: unknown) {
      setMutationError(error instanceof Error ? error.message : '복약 메모를 저장하지 못했어요.');
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  async function remove() {
    if (!noteId || savingRef.current || deletingRef.current) return;
    deletingRef.current = true;
    setDeleting(true);
    setMutationError(null);
    try {
      await deleteMedicationNote(decodeURIComponent(noteId));
      setDeleteOpen(false);
      navigate('/medications/notes', { replace: true });
    } catch (error: unknown) {
      setMutationError(error instanceof Error ? error.message : '복약 메모를 삭제하지 못했어요.');
    } finally {
      deletingRef.current = false;
      setDeleting(false);
    }
  }

  const title = editing ? '복약 메모 수정' : '복약 메모 작성';

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title={title} onBack={() => navigate('/medications/notes')} />
      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        {initialLoadError ? (
          <p role="alert" className="text-sm text-danger-strong">
            {initialLoadError}
          </p>
        ) : (
          <>
            {mutationError && (
              <p role="alert" className="text-sm text-danger-strong">
                {mutationError}
              </p>
            )}
            <section className="flex flex-col gap-1">
              <h2 id="note-form-intro" className="text-xl font-bold text-foreground">
                느낀 점을 해당 복용 기록과 함께 남겨보세요.
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
                  disabled={editing || episodes === null}
                  className="h-control w-full rounded-input border border-input bg-card px-3.5 text-[length:var(--text-control)] font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:bg-muted-bg disabled:text-disabled-foreground"
                >
                  <option value="">처방을 선택해주세요</option>
                  {episodes?.map((episode) => (
                    <option key={episode.id} value={episode.id}>
                      {prescriptionLabel(episode)}
                    </option>
                  ))}
                </select>
                {editing && (
                  <span className="text-xs font-normal text-muted-foreground">
                    기존 복용 기록의 처방은 수정할 수 없어요.
                  </span>
                )}
              </label>

              <label className="flex flex-col gap-1 text-sm font-bold text-foreground">
                약
                <select
                  aria-label="약"
                  value={form.medicationId}
                  onChange={(event) => setField('medicationId', event.target.value)}
                  disabled={!selectedEpisode || episodes === null || saving || deleting}
                  className="h-control w-full rounded-input border border-input bg-card px-3.5 text-[length:var(--text-control)] font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:bg-muted-bg disabled:text-disabled-foreground"
                >
                  <option value="">처방 전체</option>
                  {deletedMedication && (
                    <option value={DELETED_MEDICATION_ID}>삭제된 약 (처방 전체로 변경)</option>
                  )}
                  {availableMedications.map((medication) => (
                    <option key={medication.id} value={medication.id}>
                      {medicineLabel(medication)}
                    </option>
                  ))}
                </select>
                {editing && note?.medicationId === null && (
                  <span className="text-xs font-normal text-muted-foreground">
                    약이 삭제되었거나 처방 전체에 대한 메모예요.
                  </span>
                )}
              </label>

              <Input
                label="복용 일시"
                aria-label="복용 일시"
                type="datetime-local"
                value={form.takenAt}
                onChange={(event) => setField('takenAt', event.target.value)}
                disabled={episodes === null || saving || deleting}
              />

              <label className="flex flex-col gap-1 text-sm font-bold text-foreground">
                복용 후 느낀 점
                <textarea
                  aria-label="복용 후 느낀 점"
                  value={form.experience}
                  onChange={(event) => setField('experience', event.target.value)}
                  rows={5}
                  maxLength={500}
                  disabled={episodes === null || saving || deleting}
                  placeholder="복용 후 느낀 점을 적어주세요."
                  className="w-full resize-y rounded-input border border-input bg-card px-3.5 py-3 text-base font-normal text-foreground placeholder:text-tertiary-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:bg-muted-bg disabled:text-disabled-foreground"
                />
              </label>
            </div>
          </>
        )}

        <div className="mt-auto flex flex-col gap-2 pb-4">
          <Button onClick={() => void save()} disabled={!canSave || saving || deleting}>
            {saving ? '저장 중...' : editing ? '수정 저장' : '저장'}
          </Button>
          {editing && (
            <Button
              variant="danger"
              onClick={() => setDeleteOpen(true)}
              disabled={saving || deleting}
            >
              {deleting ? '삭제 중...' : '삭제'}
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
            <DialogDescription>삭제한 복약 메모는 다시 볼 수 없어요.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              취소
            </Button>
            <Button variant="danger" onClick={() => void remove()} disabled={deleting || saving}>
              {deleting ? '삭제 중...' : '삭제'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
