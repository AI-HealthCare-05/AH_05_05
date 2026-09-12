import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Plus } from 'lucide-react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import {
  listMedicationNoteEpisodes,
  listMedicationNotes,
  type MedicationNote,
  type MedicationNoteEpisode,
  type MedicationNotePage,
} from '@/entities/medication-note';
import { useSession } from '@/app/SessionContext';
import { formatDateLabel } from '@/shared/lib/dateLabel';
import { navigateBackOrReplace, trustedBackTarget } from '@/shared/lib/navigation';
import {
  BottomTabbar,
  Button,
  Card,
  Header,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/shared/ui';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import { consumeSavedNoteFilter } from './medicationNoteReturnFilter';

type NotesTab = 'withoutNotes' | 'withNotes';

interface EpisodePageState {
  page: MedicationNotePage | null;
  error: string | null;
  loadingMore: boolean;
}

function noteDateLabel(value: string): string {
  const date = value.slice(0, 10);
  const time = value.slice(11, 16);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return value;
  return `${formatDateLabel(date)} ${time}`;
}

function episodeLabel(episode: MedicationNoteEpisode): string {
  if (episode.alias) return episode.alias;
  if (episode.startDate) {
    return `${formatDateLabel(episode.startDate, { includeYear: true })} 처방`;
  }
  return '처방';
}

function episodeMedicationSummary(episode: MedicationNoteEpisode): string {
  const first = episode.representativeMedicationName?.trim();
  if (!first) return '처방약 정보 없음';
  const count = episode.medicationCount ?? 0;
  return count > 1 ? `${first} 외 ${count - 1}개` : first;
}

function medicineLabel(note: MedicationNote): string {
  if (note.medicationId === null) return '처방 전체';
  return note.medication?.name ?? '삭제된 약';
}

export function MedicationNotesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const enteredFromMedications =
    (location.state as { entry?: unknown } | null)?.entry === 'medications';
  const myReturnTarget = trustedBackTarget(location.state, ['/my', '/dev/my-authenticated']);
  const [searchParams, setSearchParams] = useSearchParams();
  const { principalKey } = useSession();
  const episodeIdParam = searchParams.get('episodeId');
  const parsedEpisodeId = episodeIdParam === null ? undefined : Number(episodeIdParam);
  const selectedEpisodeId =
    parsedEpisodeId !== undefined && Number.isSafeInteger(parsedEpisodeId) && parsedEpisodeId > 0
      ? parsedEpisodeId
      : undefined;
  const invalidEpisodeId = episodeIdParam !== null && selectedEpisodeId === undefined;
  const [tab, setTab] = useState<NotesTab>(selectedEpisodeId ? 'withNotes' : 'withoutNotes');
  const [expandedEpisodeId, setExpandedEpisodeId] = useState<number | null>(selectedEpisodeId ?? null);
  const [noteEpisodes, setNoteEpisodes] = useState<MedicationNoteEpisode[] | null>(null);
  const [noteEpisodesError, setNoteEpisodesError] = useState<string | null>(null);
  const [metadataRetryKey, setMetadataRetryKey] = useState(0);
  const [episodePages, setEpisodePages] = useState<Record<number, EpisodePageState>>({});
  const metadataGenerationRef = useRef(0);
  const appliedUrlSelectionRef = useRef<string | null>(null);
  const episodeRequestGenerationRef = useRef(new Map<number, number>());
  const principalKeyRef = useRef(principalKey);
  principalKeyRef.current = principalKey;

  useEffect(() => {
    const savedEpisodeId = consumeSavedNoteFilter(location.key, principalKey);
    if (savedEpisodeId !== null) {
      setSearchParams({ episodeId: String(savedEpisodeId) }, { replace: true, state: location.state });
    }
  }, [location.key, location.state, principalKey, setSearchParams]);

  useEffect(() => {
    const generation = metadataGenerationRef.current + 1;
    metadataGenerationRef.current = generation;
    const requestPrincipal = principalKey;
    setNoteEpisodes(null);
    setNoteEpisodesError(null);
    setEpisodePages({});
    appliedUrlSelectionRef.current = null;
    episodeRequestGenerationRef.current.clear();

    void listMedicationNoteEpisodes({ includeWithoutNotes: true })
      .then((episodes) => {
        if (metadataGenerationRef.current === generation && principalKeyRef.current === requestPrincipal) {
          setNoteEpisodes(episodes);
        }
      })
      .catch(() => {
        if (metadataGenerationRef.current === generation && principalKeyRef.current === requestPrincipal) {
          setNoteEpisodesError('메모가 있는 처방을 불러오지 못했어요.');
        }
      });
    return () => {
      if (metadataGenerationRef.current === generation) metadataGenerationRef.current += 1;
      episodeRequestGenerationRef.current.clear();
    };
  }, [metadataRetryKey, principalKey]);

  const loadEpisodePage = useCallback(async (id: number, cursor?: string) => {
    const requestPrincipal = principalKey;
    const requestGeneration = (episodeRequestGenerationRef.current.get(id) ?? 0) + 1;
    episodeRequestGenerationRef.current.set(id, requestGeneration);
    setEpisodePages((current) => ({
      ...current,
      [id]: {
        page: cursor ? current[id]?.page ?? null : null,
        error: null,
        loadingMore: cursor !== undefined,
      },
    }));
    try {
      const nextPage = await listMedicationNotes({ episodeId: id, ...(cursor ? { cursor } : {}) });
      if (
        episodeRequestGenerationRef.current.get(id) !== requestGeneration ||
        principalKeyRef.current !== requestPrincipal
      ) return;
      setEpisodePages((current) => {
        const previous = cursor ? current[id]?.page : null;
        const existingIds = new Set(previous?.items.map((item) => item.id) ?? []);
        return {
          ...current,
          [id]: {
            page: previous
              ? {
                  items: [...previous.items, ...nextPage.items.filter((item) => !existingIds.has(item.id))],
                  total: nextPage.total,
                  nextCursor: nextPage.nextCursor,
                }
              : nextPage,
            error: null,
            loadingMore: false,
          },
        };
      });
    } catch (error: unknown) {
      if (
        episodeRequestGenerationRef.current.get(id) !== requestGeneration ||
        principalKeyRef.current !== requestPrincipal
      ) return;
      setEpisodePages((current) => ({
        ...current,
        [id]: {
          page: current[id]?.page ?? null,
          error: error instanceof Error ? error.message : '건강상태 기록을 불러오지 못했어요.',
          loadingMore: false,
        },
      }));
    }
  }, [principalKey]);

  useEffect(() => {
    if (!selectedEpisodeId || !noteEpisodes) return;
    const selectedEpisode = noteEpisodes.find((episode) => episode.careEpisodeId === selectedEpisodeId);
    if (!selectedEpisode) return;
    const selectionKey = `${metadataGenerationRef.current}:${selectedEpisodeId}`;
    if (appliedUrlSelectionRef.current === selectionKey) return;
    appliedUrlSelectionRef.current = selectionKey;
    const hasNotes = (selectedEpisode.noteCount ?? 0) > 0;
    setTab(hasNotes ? 'withNotes' : 'withoutNotes');
    setExpandedEpisodeId(selectedEpisodeId);
    if (hasNotes) void loadEpisodePage(selectedEpisodeId);
  }, [loadEpisodePage, noteEpisodes, selectedEpisodeId]);

  const episodesWithNotesIds = useMemo(
    () => new Set(noteEpisodes?.filter((episode) => (episode.noteCount ?? 0) > 0).map((episode) => episode.careEpisodeId) ?? []),
    [noteEpisodes],
  );
  const episodesWithoutNotes = useMemo(
    () => noteEpisodes?.filter((episode) => !episodesWithNotesIds.has(episode.careEpisodeId)) ?? [],
    [noteEpisodes, episodesWithNotesIds],
  );
  const episodesWithNotes = useMemo(
    () => noteEpisodes?.filter((episode) => episodesWithNotesIds.has(episode.careEpisodeId)) ?? [],
    [noteEpisodes, episodesWithNotesIds],
  );
  const selectedEpisodeMissing = selectedEpisodeId !== undefined && noteEpisodes !== null &&
    !noteEpisodes.some((episode) => episode.careEpisodeId === selectedEpisodeId);

  function formEntry(id?: number) {
    return {
      entry: 'notes',
      fromMedications: enteredFromMedications,
      listKey: location.key,
      initialEpisodeId: id,
      referenceNoteId: id === undefined ? undefined : episodePages[id]?.page?.items[0]?.id,
    };
  }

  function openNewNote(id?: number) {
    navigate('/medications/notes/new', { state: formEntry(id) });
  }

  function changeTab(value: string) {
    const next = value as NotesTab;
    setTab(next);
    setExpandedEpisodeId(null);
    if (next === 'withoutNotes' && episodeIdParam !== null) {
      setSearchParams({}, { replace: true, state: location.state });
    }
  }

  function toggleEpisode(episode: MedicationNoteEpisode, kind: NotesTab) {
    const id = episode.careEpisodeId;
    if (expandedEpisodeId === id) {
      setExpandedEpisodeId(null);
      return;
    }
    setExpandedEpisodeId(id);
    appliedUrlSelectionRef.current = `${metadataGenerationRef.current}:${id}`;
    setSearchParams({ episodeId: String(id) }, { replace: true, state: location.state });
    if (kind === 'withNotes') {
      if (!episodePages[id]) void loadEpisodePage(id);
    }
  }

  function returnToMedications() {
    if (enteredFromMedications) navigateBackOrReplace(navigate, '/medications');
    else if (myReturnTarget !== null) navigateBackOrReplace(navigate, myReturnTarget);
    else navigate('/medications', { replace: true, state: { entry: 'direct-note-exit' } });
  }

  function renderEpisodeHeader(episode: MedicationNoteEpisode, kind: NotesTab) {
    const id = episode.careEpisodeId;
    const expanded = expandedEpisodeId === id;
    const baseLabel = episodeLabel(episode);
    const date = episode.startDate;
    const summary = episodeMedicationSummary(episode);
    const matchingEpisodes = noteEpisodes?.filter((candidate) =>
      episodeLabel(candidate) === baseLabel &&
      candidate.startDate === date &&
      episodeMedicationSummary(candidate) === summary
    ) ?? [];
    const duplicateIndex = matchingEpisodes.findIndex((candidate) => candidate.careEpisodeId === id);
    const label = matchingEpisodes.length > 1 ? `${baseLabel} · 처방 ${duplicateIndex + 1}` : baseLabel;
    const details = [
      date ? formatDateLabel(date, { includeYear: true }) : null,
      summary,
    ].filter(Boolean).join(' · ');
    return (
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={`medication-note-episode-${id}`}
        aria-label={`${label} · ${details} ${expanded ? '접기' : '펼치기'}`}
        onClick={() => toggleEpisode(episode, kind)}
        className="flex min-h-20 w-full items-center gap-3 rounded-card px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <span className="min-w-0 flex-1">
          <strong className="block [overflow-wrap:anywhere] text-base text-foreground">{label}</strong>
          <span className="mt-1 block [overflow-wrap:anywhere] text-sm text-muted-foreground">
            {date && `${formatDateLabel(date, { includeYear: true })} · `}{episodeMedicationSummary(episode)}
          </span>
        </span>
        <ChevronDown
          aria-hidden
          className={`size-5 shrink-0 text-primary transition-transform motion-reduce:transition-none ${expanded ? 'rotate-180' : ''}`}
        />
      </button>
    );
  }

  function renderWithoutNotesEpisode(episode: MedicationNoteEpisode) {
    const expanded = expandedEpisodeId === episode.careEpisodeId;
    return (
      <article key={episode.careEpisodeId} className="overflow-hidden rounded-card bg-card shadow-card">
        {renderEpisodeHeader(episode, 'withoutNotes')}
        {expanded && (
          <div id={`medication-note-episode-${episode.careEpisodeId}`} className="flex flex-col gap-3 border-t border-border px-4 pb-4 pt-3">
            <p className="text-sm text-muted-foreground">이 처방의 건강상태 기록이 아직 없어요.</p>
            <Button onClick={() => openNewNote(episode.careEpisodeId)}>이 처방에 메모 작성</Button>
          </div>
        )}
      </article>
    );
  }

  function renderWithNotesEpisode(episode: MedicationNoteEpisode) {
    const id = episode.careEpisodeId;
    const expanded = expandedEpisodeId === id;
    const state = episodePages[id];
    const notes = state?.page?.items ?? [];
    return (
      <article key={id} className="overflow-hidden rounded-card bg-card shadow-card">
        {renderEpisodeHeader(episode, 'withNotes')}
        {expanded && (
          <div id={`medication-note-episode-${id}`} className="flex flex-col gap-3 border-t border-border px-3 pb-3 pt-3">
            {!state || (state.page === null && !state.error) ? (
              <div role="status" aria-label="건강상태 기록 불러오는 중" className="min-h-24 animate-pulse rounded-card bg-muted-bg" />
            ) : state.page === null ? (
              <Card className="items-start p-4">
                <p role="alert" className="text-danger-strong">{state.error}</p>
                <Button className="mt-3" variant="secondary" fullWidth={false} onClick={() => void loadEpisodePage(id)}>
                  다시 시도
                </Button>
              </Card>
            ) : (
              <>
                <h3 className="px-1 text-sm font-bold text-muted-foreground">
                  건강상태 기록 {state.page.total}개
                </h3>
                {notes.length === 0 ? (
                  <Card className="p-4">이 처방의 건강상태 기록이 아직 없어요.</Card>
                ) : notes.map((note) => (
                  <button
                    key={note.id}
                    type="button"
                    aria-label={`${medicineLabel(note)} ${note.body}`}
                    onClick={() => navigate(`/medications/notes/${note.id}`, { state: formEntry(id) })}
                    className="flex min-h-28 w-full flex-col gap-2 rounded-card bg-muted-bg p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="flex w-full flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                      <span>{medicineLabel(note)}</span>
                      <span className="tnum">{noteDateLabel(note.dosedAt)}</span>
                    </span>
                    <span className="whitespace-pre-wrap [overflow-wrap:anywhere] text-base text-foreground">{note.body}</span>
                  </button>
                ))}
                {state.error && <p role="alert" className="px-1 text-sm text-danger-strong">{state.error}</p>}
                {state.page.nextCursor && (
                  <Button
                    variant="secondary"
                    disabled={state.loadingMore}
                    loading={state.loadingMore}
                    onClick={() => void loadEpisodePage(id, state.page?.nextCursor ?? undefined)}
                  >
                    {state.loadingMore ? '불러오는 중...' : '더 보기'}
                  </Button>
                )}
                <Button variant="secondary" onClick={() => openNewNote(id)}>이 처방에 새 메모</Button>
              </>
            )}
          </div>
        )}
      </article>
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title="복약 메모"
        onBack={returnToMedications}
        right={(
          <button
            type="button"
            aria-label="새 메모 작성"
            onClick={() => openNewNote()}
            className="flex min-h-touch items-center gap-1 rounded-control px-2 text-sm font-bold text-primary-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Plus aria-hidden className="size-4" />
            새 메모
          </button>
        )}
      />
      <main className="flex flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
        <p className="text-sm text-muted-foreground">
          처방을 펼쳐 복용 중 느낀 건강상태 변화를 확인하세요.
        </p>
        {invalidEpisodeId && (
          <Card className="p-4">
            <p role="alert" className="text-danger-strong">올바르지 않은 처방 주소예요.</p>
          </Card>
        )}
        {selectedEpisodeMissing && (
          <Card className="p-4">
            <p role="alert" className="text-danger-strong">선택한 처방을 찾지 못했어요.</p>
          </Card>
        )}
        <Tabs value={tab} onValueChange={changeTab}>
          <TabsList aria-label="복약 메모 처방 분류">
            <TabsTrigger value="withoutNotes">메모작성하기</TabsTrigger>
            <TabsTrigger value="withNotes">작성한 메모</TabsTrigger>
          </TabsList>
          <TabsContent value="withoutNotes" className="pt-2">
            {noteEpisodesError ? (
              <Card className="items-start p-5">
                <p role="alert" className="text-danger-strong">
                  {noteEpisodesError}
                </p>
                <Button className="mt-3" variant="secondary" fullWidth={false} onClick={() => setMetadataRetryKey((value) => value + 1)}>
                  다시 시도
                </Button>
              </Card>
            ) : noteEpisodes === null ? (
              <div role="status" aria-label="메모작성하기 처방 불러오는 중" className="min-h-32 animate-pulse rounded-card bg-muted-bg" />
            ) : noteEpisodes.length === 0 ? (
              <Card className="p-5">등록된 처방이 없어요.</Card>
            ) : episodesWithoutNotes.length === 0 ? (
              <Card className="p-5">모든 처방에 건강상태 기록이 있어요.</Card>
            ) : (
              <div className="flex flex-col gap-3">{episodesWithoutNotes.map(renderWithoutNotesEpisode)}</div>
            )}
          </TabsContent>
          <TabsContent value="withNotes" className="pt-2">
            {noteEpisodesError ? (
              <Card className="items-start p-5">
                <p role="alert" className="text-danger-strong">{noteEpisodesError}</p>
                <Button className="mt-3" variant="secondary" fullWidth={false} onClick={() => setMetadataRetryKey((value) => value + 1)}>
                  다시 시도
                </Button>
              </Card>
            ) : noteEpisodes === null ? (
              <div role="status" aria-label="작성한 메모 불러오는 중" className="min-h-32 animate-pulse rounded-card bg-muted-bg" />
            ) : episodesWithNotes.length === 0 ? (
              <Card className="p-5">작성한 건강상태 기록이 아직 없어요.</Card>
            ) : (
              <div className="flex flex-col gap-3">{episodesWithNotes.map(renderWithNotesEpisode)}</div>
            )}
          </TabsContent>
        </Tabs>
      </main>
      <BottomTabbar
        active="medication"
        onChange={(key) => key === 'medication' ? returnToMedications() : navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
    </div>
  );
}
