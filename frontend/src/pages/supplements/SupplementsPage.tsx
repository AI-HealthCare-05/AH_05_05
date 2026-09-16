import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Star } from 'lucide-react';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { getMyProfile, type Gender } from '@/entities/account';
import { getCustomChallengeParticipations, invalidateCustomChallengeProgress } from '@/entities/custom-challenge';
import {
  addSupplement,
  getSupplements,
  stopSupplement,
  summarizeNutrients,
  updateSupplement,
  type AddSupplementPayload,
  type NutrientStandards,
  type Supplement,
  type UpdateSupplementPayload,
} from '@/entities/supplement';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import { NutrientTotals } from '@/entities/supplement/ui/NutrientTotals';
import { calculateFullAge } from '@/shared/lib/birthDate';
import { mealSlotLabel } from '@/shared/model/mealSlot';
import { navigateBackOrReplace } from '@/shared/lib/navigation';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  SelectionActions,
  SelectionCheckbox,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/shared/ui';
import { AddSupplementSheet } from './AddSupplementSheet';
import { EditSupplementSheet } from './EditSupplementSheet';
import { SupplementsBrowseView } from './SupplementsBrowseView';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog';

const numberFormat = new Intl.NumberFormat('ko-KR');

interface SupplementsPageProps {
  supplementsOverride?: Supplement[];
  profileOverride?: NutrientStandardProfile;
}

export interface NutrientStandardProfile {
  birthDate: string | null;
  gender: Gender | null;
  maskedName: string;
}

export function SupplementsPage({
  supplementsOverride,
  profileOverride,
}: SupplementsPageProps = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const activeView = searchParams.get('tab') === 'browse' ? 'browse' : 'my';
  const routePresetProductId = presetProductIdFromState(location.state);
  const routeEditSupplementId = editSupplementIdFromState(location.state);
  const [supplements, setSupplements] = useState<Supplement[] | null>(supplementsOverride ?? null);
  const [standards, setStandards] = useState<NutrientStandards | null>(null);
  const [profile, setProfile] = useState<NutrientStandardProfile | null>(
    profileOverride ?? null,
  );
  const [profileResolved, setProfileResolved] = useState(profileOverride !== undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(routePresetProductId !== null);
  const [presetProductId, setPresetProductId] = useState<string | null>(routePresetProductId);
  const [editingSupplement, setEditingSupplement] = useState<Supplement | null>(null);
  const [listEditOpen, setListEditOpen] = useState(false);
  const [selectedSupplementIds, setSelectedSupplementIds] = useState<Set<number>>(new Set());
  const [bulkStopping, setBulkStopping] = useState(false);
  const [removalWarning, setRemovalWarning] = useState<{
    count: number;
    endsChallenge: boolean;
    excludesFromChallenge: boolean;
    stopName?: string;
  } | null>(null);
  const removalDecision = useRef<((confirmed: boolean) => void) | null>(null);
  const mounted = useRef(true);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveErrorTitle, setSaveErrorTitle] = useState('영양제를 추가하지 못했어요');
  const totals = useMemo(
    () => summarizeNutrients(supplements ?? [], standards),
    [standards, supplements],
  );
  const hasStandardProfile = standards !== null;
  const registeredProductIds = useMemo(
    () =>
      new Set(
        (supplements ?? []).flatMap((supplement) =>
          supplement.productId === null ? [] : [supplement.productId],
        ),
      ),
    [supplements],
  );

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      removalDecision.current?.(false);
      removalDecision.current = null;
    };
  }, []);

  function resolveRemoval(confirmed: boolean) {
    removalDecision.current?.(confirmed);
    removalDecision.current = null;
    setRemovalWarning(null);
  }

  async function confirmSupplementRemoval(ids: number[], stopName?: string): Promise<boolean> {
    try {
      // Read at the point of deletion so newly joined challenges are included.
      const { items } = await getCustomChallengeParticipations();
      if (!mounted.current) return false;
      const selected = new Set(ids);
      const affected = items.filter((participation) =>
        participation.status === 'ACTIVE' && participation.challengeType === 'SUPPLEMENT' &&
        participation.targets.some((target) => !target.isExcluded && selected.has(target.sourceId)),
      );
      if (affected.length === 0 && stopName === undefined) return true;
      const endsChallenge = affected.some((participation) =>
        participation.targets.filter((target) => !target.isExcluded)
          .every((target) => selected.has(target.sourceId)),
      );
      const excludesFromChallenge = affected.some((participation) =>
        participation.targets.some((target) => !target.isExcluded && !selected.has(target.sourceId)),
      );
      return await new Promise<boolean>((resolve) => {
        removalDecision.current = resolve;
        setRemovalWarning({ count: ids.length, endsChallenge, excludesFromChallenge, stopName });
      });
    } catch (error: unknown) {
      if (mounted.current) {
        setSaveErrorTitle('연결된 챌린지를 확인하지 못했어요');
        setSaveError(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.');
      }
      return false;
    }
  }

  useEffect(() => {
    if (routePresetProductId === null) return;
    setPresetProductId(routePresetProductId);
    setAddOpen(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, navigate, routePresetProductId]);

  useEffect(() => {
    if (routeEditSupplementId === null || supplements === null || loadError !== null) return;
    // Resolve only from the authenticated user's loaded registrations, never fetch an arbitrary ID.
    const owned = supplements.find(item => item.supplementId === routeEditSupplementId);
    if (owned) setEditingSupplement(owned);
    // Consume the one-shot intent even when the registration was removed in the meantime.
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
  }, [loadError, location.pathname, location.search, navigate, routeEditSupplementId, supplements]);

  function openAddSheet() {
    setPresetProductId(null);
    setAddOpen(true);
  }

  function changeView(view: 'my' | 'browse') {
    const search = view === 'browse' ? '?tab=browse' : '';
    navigate(`${location.pathname}${search}`, { replace: true });
  }

  function changeAddOpen(open: boolean) {
    setAddOpen(open);
    if (!open) setPresetProductId(null);
  }

  function toggleListEdit() {
    setListEditOpen((current) => !current);
    setSelectedSupplementIds(new Set());
  }

  function toggleSupplementSelection(supplementId: number) {
    setSelectedSupplementIds((current) => {
      const next = new Set(current);
      if (next.has(supplementId)) next.delete(supplementId);
      else next.add(supplementId);
      return next;
    });
  }

  async function stopSelectedSupplements() {
    if (selectedSupplementIds.size === 0 || bulkStopping) return;
    setBulkStopping(true);
    const selectedIds = [...selectedSupplementIds];
    const failedIds = new Set<number>();
    try {
      if (!(await confirmSupplementRemoval(selectedIds))) return;
      for (const supplementId of selectedIds) {
        try {
          await stopActiveSupplement(supplementId);
        } catch {
          failedIds.add(supplementId);
        }
      }
      const visibleFailedIds = new Set(
        selectedIds.filter(
          (supplementId) =>
            failedIds.has(supplementId) &&
            supplements?.some((supplement) => supplement.supplementId === supplementId),
        ),
      );
      setSelectedSupplementIds(visibleFailedIds);
      if (visibleFailedIds.size === 0) setListEditOpen(false);
    } finally {
      setBulkStopping(false);
    }
  }

  useEffect(() => {
    if (supplementsOverride) {
      setSupplements(supplementsOverride);
    }
    let cancelled = false;
    getSupplements()
      .then((result) => {
        if (cancelled) return;
        if (!supplementsOverride) setSupplements(result.items);
        const overrideHasProfile =
          profileOverride === undefined ||
          Boolean(profileOverride.birthDate && profileOverride.gender);
        setStandards(overrideHasProfile ? result.standards : null);
      })
      .catch((error: unknown) => {
        if (cancelled || supplementsOverride) return;
        setLoadError(error instanceof Error ? error.message : '영양제를 불러오지 못했어요.');
      });
    return () => {
      cancelled = true;
    };
  }, [profileOverride, supplementsOverride]);

  useEffect(() => {
    if (profileOverride !== undefined) {
      setProfile(profileOverride);
      setProfileResolved(true);
      return;
    }
    let cancelled = false;
    getMyProfile()
      .then((result) => {
        if (!cancelled) setProfile(result);
      })
      .catch(() => {
        if (!cancelled) setProfile(null);
      })
      .finally(() => {
        if (!cancelled) setProfileResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [profileOverride]);

  async function saveSupplement(payload: AddSupplementPayload) {
    try {
      const saved = await addSupplement(payload);
      setSupplements((current) => [
        saved,
        ...(current ?? []).filter(
          (supplement) =>
            supplement.supplementId !== saved.supplementId &&
            (saved.productId === null || supplement.productId !== saved.productId),
        ),
      ]);
      invalidateCustomChallengeProgress();
    } catch (error: unknown) {
      setSaveErrorTitle('영양제를 추가하지 못했어요');
      setSaveError(error instanceof Error ? error.message : '영양제를 추가하지 못했어요.');
      throw error;
    }
  }

  async function editSupplement(
    supplementId: number,
    payload: UpdateSupplementPayload,
  ) {
    try {
      const updated = await updateSupplement(supplementId, payload);
      setEditingSupplement((current) => current?.supplementId === supplementId ? updated : current);
      setSupplements((current) =>
        (current ?? []).map((supplement) =>
          supplement.supplementId === supplementId ? updated : supplement,
        ),
      );
      invalidateCustomChallengeProgress();
    } catch (error: unknown) {
      setSaveErrorTitle('영양제 정보를 저장하지 못했어요');
      setSaveError(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.');
      throw error;
    }
  }

  async function stopActiveSupplement(supplementId: number) {
    try {
      await stopSupplement(supplementId);
      setSupplements((current) =>
        (current ?? []).filter((supplement) => supplement.supplementId !== supplementId),
      );
      invalidateCustomChallengeProgress();
    } catch (error: unknown) {
      setSaveErrorTitle('영양제 복용을 중단하지 못했어요');
      setSaveError(error instanceof Error ? error.message : '잠시 후 다시 시도해주세요.');
      throw error;
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title="영양제"
        onBack={() => navigateBackOrReplace(navigate, '/home')}
        right={
          <Button
            size="compact"
            fullWidth={false}
            className="px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            onClick={() => navigate('/reports/new?source=supplements')}
          >
            AI 보고서 받기
          </Button>
        }
      />

      <div className="px-page-x pt-5">
        <Tabs
          value={activeView}
          onValueChange={(view) => changeView(view as 'my' | 'browse')}
          className="gap-0"
        >
          <TabsList aria-label="영양제 화면">
            <TabsTrigger id="supplements-tab-my" value="my" aria-controls="supplements-panel">
              내 영양제
            </TabsTrigger>
            <TabsTrigger id="supplements-tab-browse" value="browse" aria-controls="supplements-panel">
              둘러보기
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <main
        id="supplements-panel"
        role="tabpanel"
        aria-labelledby={`supplements-tab-${activeView}`}
        className="flex flex-1 flex-col gap-6 overflow-y-auto px-page-x py-5"
      >
        {activeView === 'browse' ? (
          <SupplementsBrowseView
            registeredProductIds={registeredProductIds}
            registrationPending={supplements === null}
            onSelectProduct={(productId) =>
              navigate(
                `${location.pathname.startsWith('/dev/') ? '/dev/supplements/product/' : '/supplements/product/'}${encodeURIComponent(productId)}`,
              )
            }
          />
        ) : loadError !== null ? (
          <Card title="영양제를 불러오지 못했어요">{loadError}</Card>
        ) : supplements === null ? (
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        ) : (
          <>
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2">
                {supplements.length > 0 ? (
                  <h2 id="supplement-list-title" className="shrink-0 text-xl font-bold text-foreground">
                    영양제 {supplements.length}개
                  </h2>
                ) : (
                  <h2 id="supplement-list-title" className="sr-only">
                    먹고 있는 영양제
                  </h2>
                )}
                {supplements.length > 0 && (
                  <div className="ml-auto flex shrink-0 items-center gap-2">
                    {!listEditOpen && (
                      <Button
                        fullWidth={false}
                        variant="primary"
                        onClick={openAddSheet}
                      >
                        <Plus aria-hidden className="mr-1 size-4" />
                        영양제 추가
                      </Button>
                    )}
                    <SelectionActions
                      aria-label="영양제 선택"
                      selectionMode={listEditOpen}
                      selectedCount={selectedSupplementIds.size}
                      deletePending={bulkStopping}
                      onStart={toggleListEdit}
                      onCancel={toggleListEdit}
                      onDelete={() => void stopSelectedSupplements()}
                    />
                  </div>
                )}
              </div>

              <section aria-label="먹고 있는 영양제">
                {supplements.length === 0 ? (
                  <div className="flex flex-col items-center gap-3 rounded-card border border-border bg-card px-4 py-8 text-center shadow-card">
                    <h3 className="text-lg font-bold text-foreground">영양제를 등록하고 관리하기</h3>
                    <p className="text-sm text-muted-foreground">
                      영양제를 등록하면 성분 합계와 상한을 한눈에 볼 수 있어요.
                    </p>
                    <Button className="mt-1 max-w-[150px]" onClick={openAddSheet}>
                      영양제 추가
                    </Button>
                  </div>
                ) : listEditOpen ? (
                  <div className="flex flex-col gap-3 rounded-card border border-border bg-card p-3 shadow-card">
                    <ul>
                      {supplements.map((supplement) => {
                        const selected = selectedSupplementIds.has(supplement.supplementId);
                        return (
                          <li key={supplement.supplementId} className="border-t border-border first:border-t-0">
                            <label className="flex min-h-touch min-w-0 cursor-pointer items-center gap-3 px-1 py-2">
                              <SelectionCheckbox
                                aria-label={`${supplement.name} 선택`}
                                checked={selected}
                                onCheckedChange={() => toggleSupplementSelection(supplement.supplementId)}
                              />
                              <span className="min-w-0 flex-1">
                                <strong className="block [overflow-wrap:anywhere] text-base text-foreground">
                                  {supplement.name}
                                </strong>
                                <span className="block text-sm text-muted-foreground">
                                  하루 {supplement.slots.length}회 · 1회 {formatDoseAmount(supplement.doseAmount)}
                                  {supplement.doseUnit}
                                </span>
                                <span className="mt-0.5 block text-sm text-muted-foreground">
                                  {supplement.slots.map((slot) => mealSlotLabel(slot, 'short')).join(' · ')}
                                </span>
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : (
                  <div className="overflow-hidden rounded-card border border-border bg-card shadow-card">
                    <ul>
                      {supplements.map((supplement) => (
                        <li key={supplement.supplementId} className="border-t border-border first:border-t-0">
                          <button
                            type="button"
                            className="flex min-h-touch w-full min-w-0 items-center gap-3 px-4 py-2 text-left"
                            onClick={() => setEditingSupplement(supplement)}
                          >
                            <span className="min-w-0 flex-1">
                              <strong className="block [overflow-wrap:anywhere] text-base text-foreground">
                                {supplement.name}
                              </strong>
                              <span className="block text-sm text-muted-foreground">
                                하루 {supplement.slots.length}회 · 1회 {formatDoseAmount(supplement.doseAmount)}
                                {supplement.doseUnit}
                              </span>
                              <span className="mt-0.5 block text-sm text-muted-foreground">
                                {supplement.slots.map((slot) => mealSlotLabel(slot, 'short')).join(' · ')}
                              </span>
                              {supplement.score !== null && (
                                <span
                                  className="mt-1 flex items-center gap-0.5"
                                  aria-label={`별 ${supplement.score}점`}
                                >
                                  {Array.from({ length: supplement.score }, (_, index) => (
                                    <Star
                                      key={index}
                                      aria-hidden
                                      className="size-4 fill-current text-warning-strong"
                                    />
                                  ))}
                                </span>
                              )}
                            </span>
                            <DrawnChevron direction="right" className="size-5 shrink-0 text-disabled-foreground" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            </div>

            {supplements.length > 0 && (
              <>
                <section className="flex flex-col gap-3" aria-labelledby="nutrient-total-title">
                  <h2 id="nutrient-total-title" className="text-xl font-bold text-foreground">
                    성분 합계
                  </h2>
                  <NutrientTotals totals={totals} showStandards={hasStandardProfile} />
                </section>

                <div className="flex flex-col gap-1 text-sm text-muted-foreground">
                  <p>{standardSourceLabel(profile)}</p>
                  <p>검색된 영양제의 성분만 합산된 결과예요.</p>
                  <p>직접 입력한 영양제는 성분 합산에 포함되지 않아요.</p>
                  <p>음식과 의약품을 통한 섭취량은 포함되지 않아요.</p>
                  {profileResolved && !hasStandardProfile && (
                    <button
                      type="button"
                      className="mt-2 flex min-h-touch items-center justify-between gap-3 rounded-control bg-card px-4 py-3 text-left text-sm font-bold text-foreground shadow-card"
                      onClick={() =>
                        navigate(
                          location.pathname.startsWith('/dev/') ? '/dev/my/profile' : '/my/profile',
                        )
                      }
                    >
                      <span>생년월일과 성별을 입력하면 나이·성별에 맞는 기준을 보여드려요</span>
                      <DrawnChevron direction="right" className="size-5 shrink-0 text-disabled-foreground" />
                    </button>
                  )}
                </div>
              </>
            )}

          </>
        )}
      </main>

      <BottomTabbar
        active="supplement"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
      <AddSupplementSheet
        open={addOpen}
        presetProductId={presetProductId}
        onOpenChange={changeAddOpen}
        onSave={saveSupplement}
      />
      <EditSupplementSheet
        open={editingSupplement !== null}
        supplement={editingSupplement}
        maskedName={profile?.maskedName ?? '익명'}
        onOpenChange={(open) => {
          if (!open) setEditingSupplement(null);
        }}
        onSave={editSupplement}
        onProductInfo={(productId) =>
          navigate(
            `${location.pathname.startsWith('/dev/') ? '/dev/supplements/product/' : '/supplements/product/'}${encodeURIComponent(productId)}`,
          )
        }
      />
      <Dialog open={removalWarning !== null} onOpenChange={(open) => { if (!open) resolveRemoval(false); }}>
        <DialogContent showCloseButton={false} className="gap-4 p-6">
          <DialogHeader>
            <DialogTitle className="[overflow-wrap:anywhere]">
              {removalWarning?.stopName ? `${removalWarning.stopName} 복용을 중단할까요?` : '영양제를 삭제할까요?'}
            </DialogTitle>
            <DialogDescription>
              {removalWarning?.endsChallenge && removalWarning.excludesFromChallenge
                ? '일부 챌린지는 종료되고, 나머지 챌린지에서는 선택한 영양제가 제외돼요.'
                : removalWarning?.endsChallenge
                  ? `${removalWarning.stopName ? '복용을 중단하면' : '삭제하면'} 참여 중인 챌린지가 종료돼요.`
                  : removalWarning?.excludesFromChallenge
                    ? <>이 영양제로 참여 중인 챌린지가 있어요.<br />{removalWarning.stopName ? '복용을 중단하면' : '삭제하면'} 해당 챌린지의 대상에서 제외돼요.</>
                    : '성분 합계에서 제외됩니다. 다시 추가할 수 있어요.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => resolveRemoval(false)}>취소</Button>
            <Button variant="danger" onClick={() => resolveRemoval(true)}>
              {removalWarning?.stopName ? '중단하기' : `삭제 ${removalWarning?.count}개`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ErrorDialog
        open={saveError !== null}
        title={saveErrorTitle}
        message={saveError ?? ''}
        retryLabel="확인"
        onRetry={() => setSaveError(null)}
      />
    </div>
  );
}


function standardSourceLabel(profile: NutrientStandardProfile | null): string {
  if (!profile?.birthDate || !profile.gender) {
    return '2025 한국인 영양소 섭취기준';
  }
  const age = calculateFullAge(profile.birthDate);
  const gender = profile.gender === 'female' ? '여성' : '남성';
  return `2025 한국인 영양소 섭취기준 · 만 ${age}세 ${gender}`;
}

function formatDoseAmount(amount: number): string {
  return numberFormat.format(amount);
}

function presetProductIdFromState(state: unknown): string | null {
  if (state === null || typeof state !== 'object' || !('presetProductId' in state)) return null;
  const productId = (state as { presetProductId?: unknown }).presetProductId;
  return typeof productId === 'string' && productId ? productId : null;
}

function editSupplementIdFromState(state: unknown): number | null {
  if (state === null || typeof state !== 'object' || !('editSupplementId' in state)) return null;
  const id = (state as { editSupplementId?: unknown }).editSupplementId;
  return typeof id === 'number' && Number.isSafeInteger(id) && id > 0 ? id : null;
}
