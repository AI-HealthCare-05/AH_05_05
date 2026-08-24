import { useEffect, useState, type MouseEvent, type ReactNode } from 'react';
import { AlertTriangle, ChevronRight, Plus } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import {
  confirmOcrResult,
  getOcrResult,
  type Confidence,
  type OcrMedication,
  type OcrResult,
} from '@/entities/document';
import {
  Button,
  Card,
  ErrorDialog,
  Header,
  ImageViewer,
  Input,
  StatusBadge,
  type StatusBadgeType,
} from '@/shared/ui';
import { LowConfidenceConfirmDialog } from './LowConfidenceConfirmDialog';
import { MedicationEditDialog } from './MedicationEditDialog';

interface OcrReviewLocationState {
  batchId?: string;
}

type MedicationEditorTarget =
  | { mode: 'add' }
  | { mode: 'edit'; tempId: string };

/**
 * 오늘 날짜(YYYY-MM-DD). 조제일은 미래일 수 없으므로 입력 상한과 저장 검증에 함께 씁니다.
 * 복약 시간 화면과 같은 로컬 기준을 써야 두 화면의 날짜 입력이 다르게 동작하지 않습니다.
 */
function todayISO(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** 다른 화면이 매핑을 재사용할 수 있으므로 high 항목도 지우지 않습니다. */
const CONFIDENCE_BADGE: Record<Confidence, { type: StatusBadgeType; label: string }> = {
  high: { type: 'active', label: '확인됨' },
  medium: { type: 'dose', label: '확인 권장' },
  low: { type: 'review', label: '확인 필요' },
};

function ConfidenceBadge({ confidence }: { confidence?: Confidence }) {
  if (!confidence || confidence === 'high') return null;
  const badge = CONFIDENCE_BADGE[confidence];
  return <StatusBadge type={badge.type}>{badge.label}</StatusBadge>;
}

export function OcrReviewPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as OcrReviewLocationState | null) ?? {};
  const batchId = state.batchId ?? 'b_mock_9f21';

  const [result, setResult] = useState<OcrResult | null>(null);
  const [dispensedDate, setDispensedDate] = useState('');
  const [dispensedDateConfidence, setDispensedDateConfidence] = useState<Confidence | null>(null);
  const [medications, setMedications] = useState<OcrMedication[]>([]);
  const [medicationEditorTarget, setMedicationEditorTarget] =
    useState<MedicationEditorTarget | null>(null);
  const [reviewConfirmOpen, setReviewConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [dismissedOcrFailure, setDismissedOcrFailure] = useState(false);
  const [imageViewerOpen, setImageViewerOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getOcrResult(batchId)
      .then((data) => {
        if (cancelled) return;
        setResult(data);
        // 판별 유니온 계약: 결과 필드가 있는 두 상태를 확인한 뒤에만 fields를 읽습니다.
        if (data.ocrStatus !== 'ready_for_review' && data.ocrStatus !== 'complete') return;
        setDispensedDate(data.fields.dispensedDate.value ?? '');
        setDispensedDateConfidence(data.fields.dispensedDate.confidence);
        setMedications(data.medications);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '판독 결과를 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  function openDatePicker(event: MouseEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (typeof input.showPicker !== 'function') return;
    try {
      input.showPicker();
    } catch {
      // 미지원 브라우저에서는 기본 date input 동작에 맡깁니다.
    }
  }

  const reviewItemNames: string[] = [];
  if (dispensedDateConfidence && dispensedDateConfidence !== 'high') {
    reviewItemNames.push('조제일');
  }
  for (const medication of medications) {
    if (medication.confidence && medication.confidence !== 'high') {
      reviewItemNames.push(medication.name || '복약 정보');
    }
  }

  const maxDispensedDate = todayISO();
  const dispensedDateInFuture = dispensedDate > maxDispensedDate;
  const canSave = Boolean(dispensedDate) && !dispensedDateInFuture && !saving;

  function handleSaveClick() {
    if (!canSave) return;
    if (reviewItemNames.length > 0) {
      setReviewConfirmOpen(true);
      return;
    }
    void save();
  }

  async function save() {
    if (!result || !dispensedDate) return;
    setSaving(true);
    setSaveError(null);
    try {
      const { recordId, hasMedication } = await confirmOcrResult(batchId, {
        dispensedDate,
        medications: medications.map((medication) => ({
          tempId: medication.tempId,
          name: medication.name,
          dose: medication.dose,
          timesPerDay: medication.timesPerDay,
          days: medication.days,
          note: medication.note,
        })),
      });
      toast.success('저장했어요.');
      if (hasMedication) {
        navigate('/medication-schedule', { state: { recordId, dispensedDate } });
      } else {
        navigate('/home', { replace: true });
      }
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '저장하지 못했어요.');
    } finally {
      setSaving(false);
    }
  }

  if (loadError !== null || result === null) {
    return (
      <PageFrame onBack={() => navigate(-1)}>
        {loadError ? (
          <Card title="판독 결과를 불러오지 못했어요">{loadError}</Card>
        ) : (
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        )}
      </PageFrame>
    );
  }

  if (result.ocrStatus === 'queued' || result.ocrStatus === 'processing') {
    return (
      <PageFrame onBack={() => navigate(-1)}>
        <Card tone="info" title="약봉투를 읽고 있어요">
          잠시만 기다려주세요. 다 읽으면 확인할 내용을 보여드릴게요.
        </Card>
      </PageFrame>
    );
  }

  if (result.ocrStatus === 'complete') {
    return (
      <PageFrame onBack={() => navigate(-1)}>
        <Card tone="success" title="이미 등록된 약봉투예요">
          이 약봉투는 확인과 저장이 끝났습니다. 등록된 내용은 복용약 화면에서 볼 수 있어요.
        </Card>
        <div className="mt-auto flex flex-col gap-2 pb-4">
          <Button onClick={() => navigate('/home', { replace: true })}>홈으로</Button>
          <Button variant="secondary" onClick={() => navigate('/document-upload')}>
            다른 약봉투 등록
          </Button>
        </div>
      </PageFrame>
    );
  }

  const ocrFailed = result.ocrStatus === 'failed';
  const ocrCancelled = result.ocrStatus === 'cancelled';
  const showOcrFailure = (ocrFailed || ocrCancelled) && !dismissedOcrFailure;
  const documentImageUrl = 'documentImageUrl' in result ? result.documentImageUrl : null;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="확인해주세요" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col gap-5 px-page-x py-5">
        {reviewItemNames.length > 0 ? (
          <Card tone="warning" className="gap-2 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0 text-warning-strong" />
              <div>
                <p className="text-lg font-bold text-foreground">
                  {reviewItemNames.length}곳만 확인해주세요
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  나머지는 잘 읽혔습니다. 아무 항목이나 눌러 고칠 수 있어요.
                </p>
              </div>
            </div>
          </Card>
        ) : (
          <Card tone="info" title="내용을 잘 읽었어요">
            저장하기 전에 조제일과 약 정보를 한 번 확인해주세요.
          </Card>
        )}

        {documentImageUrl && (
          <button
            type="button"
            aria-label="등록한 약봉투 원본 크게 보기"
            className="overflow-hidden rounded-card bg-card text-left shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setImageViewerOpen(true)}
          >
            <img
              src={documentImageUrl}
              alt="등록한 약봉투 원본"
              className="h-24 w-full object-cover object-top"
            />
            <span className="flex min-h-touch items-center justify-between gap-3 px-4 text-sm font-bold text-foreground">
              촬영한 약봉투 원본
              <span className="text-muted-foreground">크게 보기</span>
            </span>
          </button>
        )}

        <Card className="gap-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="dispensedDate" className="text-base font-bold text-foreground">
              조제일
            </label>
            <ConfidenceBadge confidence={dispensedDateConfidence ?? undefined} />
          </div>
          <Input
            id="dispensedDate"
            aria-label="조제일"
            type="date"
            max={maxDispensedDate}
            value={dispensedDate}
            onChange={(event) => setDispensedDate(event.target.value)}
            onClick={openDatePicker}
            error={dispensedDateInFuture ? '조제일은 오늘까지만 고를 수 있어요.' : undefined}
            hint="복용 시작일을 이 날짜로 채워둘게요."
          />
        </Card>

        <section className="flex flex-col gap-3" aria-labelledby="ocr-medication-title">
          <h2 id="ocr-medication-title" className="text-xl font-bold text-foreground">
            약 {medications.length}개
          </h2>
          {medications.map((medication) => (
            <button
              key={medication.tempId}
              type="button"
              className="flex min-h-20 w-full items-center gap-3 rounded-card bg-card px-4 py-3 text-left shadow-card"
              onClick={() =>
                setMedicationEditorTarget({ mode: 'edit', tempId: medication.tempId })
              }
            >
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <strong className="text-lg text-foreground">
                    {medication.name} {medication.dose}
                  </strong>
                  <ConfidenceBadge confidence={medication.confidence} />
                </span>
                <span className="mt-1 block text-sm text-muted-foreground">
                  {medicationSummary(medication)}
                </span>
              </span>
              <ChevronRight aria-hidden className="size-5 shrink-0 text-disabled-foreground" />
            </button>
          ))}
          <button
            type="button"
            className="flex min-h-touch items-center justify-center gap-2 rounded-card border border-dashed border-border text-sm font-bold text-muted-foreground"
            onClick={() => setMedicationEditorTarget({ mode: 'add' })}
          >
            <Plus aria-hidden className="size-5" />
            빠진 약 직접 추가
          </button>
        </section>

        <p className="text-sm text-muted-foreground">
          사진에서 읽은 내용입니다. 실제 약봉투와 다르면 고쳐주세요.
        </p>

        <div className="mt-auto flex flex-col gap-2 pb-4">
          <Button onClick={handleSaveClick} disabled={!canSave}>
            {saving ? '저장 중...' : '저장하고 복약 시간 설정'}
          </Button>
          <Button variant="secondary" onClick={() => navigate('/document-upload')}>
            다시 촬영하기
          </Button>
        </div>
      </main>

      <MedicationEditDialog
        open={medicationEditorTarget !== null}
        mode={medicationEditorTarget?.mode ?? 'add'}
        medication={
          medicationEditorTarget?.mode === 'edit'
            ? medications.find(
                (medication) => medication.tempId === medicationEditorTarget.tempId,
              ) ?? null
            : null
        }
        onOpenChange={(open) => {
          if (!open) setMedicationEditorTarget(null);
        }}
        onSave={(savedMedication) => {
          setMedications((current) =>
            medicationEditorTarget?.mode === 'edit'
              ? current.map((medication) =>
                  medication.tempId === savedMedication.tempId ? savedMedication : medication,
                )
              : [...current, savedMedication],
          );
          setMedicationEditorTarget(null);
        }}
        onDelete={
          medicationEditorTarget?.mode === 'edit'
            ? () => {
                setMedications((current) =>
                  current.filter(
                    (medication) => medication.tempId !== medicationEditorTarget.tempId,
                  ),
                );
                setMedicationEditorTarget(null);
              }
            : undefined
        }
      />
      <ErrorDialog
        open={showOcrFailure}
        title={ocrCancelled ? '검토 시간이 지났어요' : '문서를 읽지 못했어요'}
        message={
          ocrCancelled
            ? '검토 가능한 시간이 지나 결과를 사용할 수 없어요. 약봉투를 다시 등록해주세요.'
            : '약봉투에서 내용을 읽어내지 못했어요. 다시 촬영하거나 직접 입력할 수 있어요.'
        }
        retryLabel="다시 촬영하기"
        onRetry={() => navigate('/document-upload')}
        secondaryLabel={ocrFailed ? '그대로 직접 입력' : undefined}
        onSecondary={ocrFailed ? () => setDismissedOcrFailure(true) : undefined}
      />
      <ErrorDialog
        open={saveError !== null}
        title="저장하지 못했어요"
        message={saveError ?? ''}
        onRetry={() => {
          setSaveError(null);
          void save();
        }}
      />
      <LowConfidenceConfirmDialog
        open={reviewConfirmOpen}
        itemNames={reviewItemNames}
        onConfirm={() => {
          setReviewConfirmOpen(false);
          void save();
        }}
        onCancel={() => setReviewConfirmOpen(false)}
      />
      {documentImageUrl && (
        <ImageViewer
          open={imageViewerOpen}
          src={documentImageUrl}
          title="약봉투 원본 크게 보기"
          onOpenChange={setImageViewerOpen}
        />
      )}
    </div>
  );
}

function PageFrame({ onBack, children }: { onBack: () => void; children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="확인해주세요" onBack={onBack} />
      <main className="flex flex-1 flex-col gap-3 px-page-x py-5">{children}</main>
    </div>
  );
}

function medicationSummary(medication: OcrMedication): string {
  const frequency =
    medication.timesPerDay === null ? '필요할 때만' : `1일 ${medication.timesPerDay}회`;
  const days = medication.days === null ? '' : `${medication.days}일분`;
  return [frequency, days].filter(Boolean).join(' · ');
}
