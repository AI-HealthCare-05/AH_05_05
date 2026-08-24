import { useEffect, useState, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button, Card, ErrorDialog, Header, Input, StatusBadge } from '@/shared/ui';
import type { StatusBadgeType } from '@/shared/ui';
import {
  confirmOcrResult,
  getOcrResult,
  type Confidence,
  type OcrAdvice,
  type OcrMedication,
  type OcrResult,
} from '@/entities/document';
import { LowConfidenceConfirmDialog } from './LowConfidenceConfirmDialog';
import { MedicationEditDialog } from './MedicationEditDialog';

/**
 * REQ-DOC-003 · Figma `07 OCR 결과 확인·수정` (66:115)
 *
 * 신뢰도 배지: high → 확인됨, medium → 확인 권장, low → 확인 필요.
 * StatusBadge에 새 variant를 추가하지 않고, 기존 dose/review/active 톤 + children
 * 오버라이드만 사용했습니다(계약서 "Card/StatusBadge는 교체하지 않는다" 준수).
 *
 * medium과 low의 문구를 반드시 다르게 둡니다. 둘 다 "확인 필요"였을 때, 화면에는
 * 배지가 4개 붙어 있는데 O08 모달은 low만 세어 "3개 미확인"이라고 말해서 사용자가
 * 남은 하나를 찾아 헤매는 문제가 있었습니다. 모달이 세는 대상(low)과 같은 문구를
 * 쓰는 배지는 low 하나뿐이어야 합니다.
 *
 * "복용일수" 필드(fields.medicationDays)는 원래 07/O07 어디에도 입·수정 UI가 없었으나,
 * 활성 기간 계산의 핵심 값이라 기획 결정에 따라 퇴원일 바로 아래에 추가했습니다.
 *
 * "다시 촬영·재업로드"는 최초 업로드 경로에서는 문서 업로드(05)로 그냥 돌아갑니다.
 * 재업로드 경로(07-R)에서 기존 기록과 병합할지 고르는 히스토리 매칭(REQ-HIST-001)은
 * 아직 미구현이며, 그 화면이 생기면 진입 경로에 따라 분기해야 합니다.
 */
interface OcrReviewLocationState {
  batchId?: string;
}

/**
 * 오늘 날짜(YYYY-MM-DD). 퇴원일 상한으로만 씁니다 — 퇴원일이 미래일 수는 없습니다.
 * 09 화면(복약 시작일)과 같은 로컬 기준을 씁니다. 두 화면의 날짜 입력이 다르게
 * 동작하면 안 됩니다.
 */
function todayISO(): string {
  const now = new Date();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${m}-${d}`;
}

const CONFIDENCE_BADGE: Record<Confidence, { type: StatusBadgeType; label: string }> = {
  high: { type: 'active', label: '확인됨' },
  medium: { type: 'dose', label: '확인 권장' },
  low: { type: 'review', label: '확인 필요' },
};

function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const badge = CONFIDENCE_BADGE[confidence];
  return <StatusBadge type={badge.type}>{badge.label}</StatusBadge>;
}

export function OcrReviewPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as OcrReviewLocationState | null) ?? {};
  const batchId = state.batchId ?? 'b_mock_9f21';

  const [result, setResult] = useState<OcrResult | null>(null);
  const [diagnosis, setDiagnosis] = useState('');
  const [surgery, setSurgery] = useState('');
  const [dischargeDate, setDischargeDate] = useState('');
  const [medicationDays, setMedicationDays] = useState('');
  const [medications, setMedications] = useState<OcrMedication[]>([]);
  const [advices, setAdvices] = useState<OcrAdvice[]>([]);
  const [medicationDialogOpen, setMedicationDialogOpen] = useState(false);
  const [lowConfidenceConfirmOpen, setLowConfidenceConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  /** 저장 실패 팝업. 입력값은 그대로 두고 재시도만 제공합니다. */
  const [saveError, setSaveError] = useState<string | null>(null);
  /**
   * OCR 실패(failed·cancelled) 팝업을 사용자가 닫고 직접 입력하기로 한 상태.
   * 여기서 막으면 서비스를 아예 쓸 수 없으므로 직접 입력 경로를 반드시 남깁니다.
   */
  const [dismissedOcrFailure, setDismissedOcrFailure] = useState(false);
  /**
   * 필드별 신뢰도. 결과가 온 상태에서만 채워집니다.
   *
   * 값을 로드 시점에 지역 상태로 옮겨두면 렌더가 `result.fields` 를 만지지 않아도 됩니다 —
   * failed 에서 "그대로 직접 입력" 으로 들어온 폼에는 신뢰도가 아예 없고(추출된 게 없으니
   * 당연합니다), 그때 배지를 숨기는 판단이 null 하나로 끝납니다.
   */
  const [fieldConfidence, setFieldConfidence] = useState<{
    diagnosis: Confidence;
    surgery: Confidence;
    dischargeDate: Confidence;
    medicationDays: Confidence;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getOcrResult(batchId)
      .then((data) => {
        if (cancelled) return;
        setResult(data);
        // 명세 4번 — queued·processing·failed·cancelled 에는 결과 필드가 없습니다.
        // 상태를 먼저 검사하지 않으면 undefined 접근으로 throw 해서, 아래 대기·실패 분기에
        // 도달하지 못하고 loadError 카드로 떨어집니다.
        if (data.ocrStatus !== 'ready_for_review' && data.ocrStatus !== 'complete') return;
        setDiagnosis(data.fields.diagnosis.value ?? '');
        setSurgery(data.fields.surgery.value ?? '');
        setDischargeDate(data.fields.dischargeDate.value ?? '');
        setMedicationDays(
          data.fields.medicationDays.value != null ? String(data.fields.medicationDays.value) : '',
        );
        setFieldConfidence({
          diagnosis: data.fields.diagnosis.confidence,
          surgery: data.fields.surgery.confidence,
          dischargeDate: data.fields.dischargeDate.confidence,
          medicationDays: data.fields.medicationDays.confidence,
        });
        setMedications(data.medications);
        setAdvices(data.advices);
      })
      // catch 가 없으면 실 API 오류에서 result 가 null 로 남아 "불러오는 중"에
      // 영구히 멈춥니다. 로딩과 실패는 화면에서 구분되어야 합니다.
      .catch((error: unknown) => {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : 'OCR 결과를 불러오지 못했어요.');
      });
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  function updateAdviceText(tempId: string, text: string) {
    setAdvices((prev) => prev.map((a) => (a.tempId === tempId ? { ...a, text } : a)));
  }

  /**
   * 퇴원일은 날짜 입력(type="date")이라 브라우저·OS 기본 달력을 씁니다.
   * 데스크톱 크롬은 우측 달력 아이콘을 눌러야만 열리는데, 고령 사용자 기준으로는
   * 입력칸 아무 곳이나 눌러도 달력이 열리는 편이 낫다고 보고 showPicker()를 붙였습니다.
   * (지원하지 않는 브라우저에서는 조용히 무시하고 기존 동작을 그대로 둡니다.)
   */
  function openDatePicker(event: MouseEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (typeof input.showPicker !== 'function') return;
    try {
      input.showPicker();
    } catch {
      // 사용자 제스처가 아니거나 미지원인 경우 — 기본 동작에 맡깁니다.
    }
  }

  /**
   * OCR 결과가 통째로 잘못 나왔을 때 사용자가 쓸 유일한 탈출구입니다.
   * 최초 업로드 경로에서는 히스토리 매칭이 없으므로 문서 업로드로 바로 돌아갑니다.
   */
  function handleReupload() {
    navigate('/dev/document-upload');
  }

  /*
    max 는 달력 UI만 제한하고 키보드로 넣은 미래 날짜는 그대로 올라옵니다.
    그래서 저장도 같은 조건으로 막습니다(09 복약 시작일과 같은 방식).
  */
  const maxDischargeDate = todayISO();
  const dischargeDateInFuture = dischargeDate > maxDischargeDate;

  /**
   * 낮은 신뢰도 항목 이름 목록 — O08 모달 문구와 07의 "확인 필요 항목" 카드가 함께 씁니다.
   *
   * 스펙 3-2는 lowConfidenceCount를 서버가 세어주고 "프론트에서 다시 세지 않는다"로
   * 정하고 있습니다. 다만 O07에서 약을 지우거나 추가하면 그 값이 즉시 낡습니다
   * (낮은 신뢰도였던 약을 지웠는데도 계속 "N개 미확인"으로 남음). 화면에 보이는 상태와
   * 어긋나면 안 되므로 표시용 개수·이름은 현재 상태에서 다시 계산합니다.
   * 서버 값은 최초 로드 시점의 기준값으로만 두고 화면에 직접 쓰지 않습니다.
   */
  const lowConfidenceItemNames: string[] = [];
  if (result) {
    if (fieldConfidence?.diagnosis === 'low') lowConfidenceItemNames.push('진단명');
    if (fieldConfidence?.surgery === 'low') lowConfidenceItemNames.push('수술명');
    if (fieldConfidence?.dischargeDate === 'low') lowConfidenceItemNames.push('퇴원일');
    if (fieldConfidence?.medicationDays === 'low') lowConfidenceItemNames.push('복용일수');
    // 약이 여러 건 낮게 나올 수 있어 건수를 함께 표기합니다. 항목 이름만 두면
    // "복약 정보 1개"로 세어져, 실제로 확인해야 할 약이 2건일 때 개수가 어긋납니다.
    const lowMedCount = medications.filter((m) => m.confidence === 'low').length;
    if (lowMedCount === 1) lowConfidenceItemNames.push('복약 정보');
    else if (lowMedCount > 1) lowConfidenceItemNames.push(`복약 정보(${lowMedCount}건)`);
  }

  /**
   * REQ-DOC-003: 저장하기는 바로 넘어가지 않고 O08 확인 모달을 1회 거칩니다.
   * 낮은 신뢰도 항목이 하나도 없으면 모달 없이 바로 저장합니다.
   */
  function handleSaveClick() {
    if (lowConfidenceItemNames.length > 0) {
      setLowConfidenceConfirmOpen(true);
      return;
    }
    void doSave();
  }

  function handleLowConfidenceConfirm() {
    setLowConfidenceConfirmOpen(false);
    void doSave();
  }

  async function doSave() {
    if (!result) return;
    setSaving(true);
    setSaveError(null);
    try {
      const { recordId, hasMedication } = await confirmOcrResult(batchId, {
        diagnosis,
        surgery,
        dischargeDate,
        medicationDays: Number(medicationDays) || 0,
        medications: medications.map((m) => ({
          tempId: m.tempId,
          name: m.name,
          dose: m.dose,
          timesPerDay: m.timesPerDay,
          note: m.note,
        })),
        advices: advices.map((a) => ({ tempId: a.tempId, text: a.text })),
      });
      toast.success('저장 완료');

      // 스펙 3-3 / REQ-CARE-003: 복약 정보가 없으면 복약 시간 설정을 건너뛰고 홈으로 갑니다.
      if (hasMedication) {
        navigate('/dev/medication-schedule', { state: { recordId } });
      } else {
        navigate('/dev/flow-complete', { state: { reason: 'no-medication' } });
      }
    } catch (error: unknown) {
      // 화면 상태(diagnosis 등)는 건드리지 않습니다 — 방금 고친 값이 사라지면 안 됩니다.
      setSaveError(error instanceof Error ? error.message : '저장하지 못했어요.');
    } finally {
      setSaving(false);
    }
  }

  if (loadError !== null || !result) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="OCR 결과 확인" onBack={() => navigate(-1)} />
        <main className="flex flex-1 flex-col px-page-x py-4">
          {loadError !== null ? (
            <Card title="OCR 결과를 불러오지 못했어요">{loadError}</Card>
          ) : (
            <p className="text-sm text-muted-foreground">불러오는 중...</p>
          )}
        </main>
      </div>
    );
  }

  /*
    명세 4번: queued·processing 에서는 결과 필드가 오지 않습니다. 아직 실패가 아니라
    진행 중이므로 팝업이 아니라 화면 내 대기 표시로 두고, 결과 필드를 읽기 전에 갈랍니다.
  */
  if (result.ocrStatus === 'queued' || result.ocrStatus === 'processing') {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="OCR 결과 확인" onBack={() => navigate(-1)} />
        <main className="flex flex-1 flex-col px-page-x py-4">
          <Card tone="info" title="문서를 읽고 있어요">
            잠시만 기다려주세요. 다 읽으면 확인할 내용을 보여드립니다.
          </Card>
        </main>
      </div>
    );
  }

  /*
    complete 는 이미 확정이 끝난 작업입니다(ERD: 확정 시 structured_result 를 지우고
    상태를 COMPLETE 로). 실패가 아니고 뒤에 돌아갈 폼도 없으므로 팝업이 아니라 화면 내
    카드로 알립니다.

    **검토 폼을 렌더하지 않습니다.** 명세상 같은 hash 재요청만 기존 결과를 돌려주고 다른
    hash 는 409 로 거부하므로, 값을 고칠 수 있게 보여주면 저장에서 실패합니다.
  */
  if (result.ocrStatus === 'complete') {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="OCR 결과 확인" onBack={() => navigate(-1)} />
        <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
          <Card tone="success" title="이미 등록된 문서예요">
            이 문서는 확인과 저장이 끝났습니다. 등록된 내용은 복약·생활관리 화면에서 볼 수
            있어요.
          </Card>

          <div className="flex-1" />

          {/* 막다른 화면으로 두지 않습니다. complete 응답에는 recordId 가 없어
              복약 시간 설정으로 바로 보낼 수 없으므로 허브로 보냅니다. */}
          <div className="flex flex-col gap-2 pb-4">
            <Button onClick={() => navigate('/dev/flow-complete')}>다음으로</Button>
            <Button variant="secondary" onClick={() => navigate('/dev/document-upload')}>
              다른 문서 등록하기
            </Button>
          </div>
        </main>
      </div>
    );
  }

  /*
    failed·cancelled 는 사용자가 여기서 조치할 수 있는 실패라 팝업으로 알립니다.
    뒤에 빈 검토 폼이 남아 있어서(= 직접 입력 경로) 팝업이 의미가 있습니다.
  */
  const ocrFailed = result.ocrStatus === 'failed';
  const ocrCancelled = result.ocrStatus === 'cancelled';
  const showOcrFailureDialog = (ocrFailed || ocrCancelled) && !dismissedOcrFailure;

  const medicationConfidence: Confidence = medications.some((m) => m.confidence === 'low')
    ? 'low'
    : medications.some((m) => m.confidence === 'medium')
      ? 'medium'
      : 'high';

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="OCR 결과 확인" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <p className="text-base text-foreground">
          추출된 항목을 확인하고 잘못된 내용은 수정해주세요.
        </p>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="diagnosis" className="text-sm font-bold text-foreground">
              진단명
            </label>
            {fieldConfidence && <ConfidenceBadge confidence={fieldConfidence.diagnosis} />}
          </div>
          <Input
            id="diagnosis"
            value={diagnosis}
            onChange={(e) => setDiagnosis(e.target.value)}
            placeholder="추출된 진단명이 없습니다. 직접 입력해주세요."
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="surgery" className="text-sm font-bold text-foreground">
              수술명
            </label>
            {fieldConfidence && <ConfidenceBadge confidence={fieldConfidence.surgery} />}
          </div>
          <Input
            id="surgery"
            value={surgery}
            onChange={(e) => setSurgery(e.target.value)}
            placeholder="추출된 수술명이 없습니다. 직접 입력해주세요."
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="dischargeDate" className="text-sm font-bold text-foreground">
              퇴원일
            </label>
            {fieldConfidence && <ConfidenceBadge confidence={fieldConfidence.dischargeDate} />}
          </div>
          <Input
            id="dischargeDate"
            type="date"
            max={maxDischargeDate}
            value={dischargeDate}
            onChange={(e) => setDischargeDate(e.target.value)}
            onClick={openDatePicker}
            error={dischargeDateInFuture ? '퇴원일은 오늘까지만 고를 수 있어요.' : undefined}
            hint={dischargeDate ? undefined : '추출된 퇴원일이 없습니다. 달력에서 선택해주세요.'}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="medicationDays" className="text-sm font-bold text-foreground">
              복용일수
            </label>
            {fieldConfidence && <ConfidenceBadge confidence={fieldConfidence.medicationDays} />}
          </div>
          <div className="flex items-center gap-2">
            <Input
              id="medicationDays"
              type="number"
              inputMode="numeric"
              min={0}
              value={medicationDays}
              onChange={(e) => setMedicationDays(e.target.value)}
              placeholder="추출된 복용일수가 없습니다. 직접 입력해주세요."
            />
            <span className="shrink-0 text-sm text-muted-foreground">일</span>
          </div>
        </div>

        <Card
          tone="info"
          onClick={() => setMedicationDialogOpen(true)}
          title={`복약 정보 · ${medications.length}건`}
          titleRight={
            medications.length > 0 ? <ConfidenceBadge confidence={medicationConfidence} /> : undefined
          }
        >
          {medications.length > 0 ? (
            <div className="flex flex-col gap-0.5">
              {medications.map((m) => (
                <span key={m.tempId}>
                  {m.name} {m.dose} · {m.note}
                </span>
              ))}
            </div>
          ) : (
            '추출된 복약 정보가 없습니다. 저장하면 홈으로 이동합니다.'
          )}
        </Card>

        <div className="flex flex-col gap-2">
          <p className="text-sm font-bold text-foreground">의료진 권고사항</p>
          {advices.map((advice) => (
            <Input
              key={advice.tempId}
              aria-label="의료진 권고사항"
              value={advice.text}
              onChange={(e) => updateAdviceText(advice.tempId, e.target.value)}
            />
          ))}
        </div>

        {lowConfidenceItemNames.length > 0 && (
          <Card tone="warning" title="확인 필요 항목">
            낮은 신뢰도 항목 {lowConfidenceItemNames.length}개를 확인해주세요.
          </Card>
        )}

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button onClick={handleSaveClick} disabled={saving || dischargeDateInFuture}>
            {saving ? '저장 중...' : '저장하기'}
          </Button>
          <Button variant="secondary" onClick={handleReupload}>
            다시 촬영·재업로드
          </Button>
        </div>
      </main>

      <MedicationEditDialog
        open={medicationDialogOpen}
        medications={medications}
        onOpenChange={setMedicationDialogOpen}
        onSave={setMedications}
      />

      <ErrorDialog
        open={showOcrFailureDialog}
        title={ocrCancelled ? '검토 시간이 지났어요' : '문서를 읽지 못했어요'}
        message={
          ocrCancelled
            ? '검토 가능한 시간이 지나 결과를 사용할 수 없어요. 문서를 다시 등록해주세요.'
            : '문서에서 내용을 읽어내지 못했어요. 다시 촬영하거나 직접 입력할 수 있어요.'
        }
        retryLabel="다시 촬영하기"
        onRetry={() => navigate('/dev/document-upload')}
        // 여기서 막으면 사용자가 서비스를 아예 쓸 수 없으므로 직접 입력 경로를 남깁니다.
        // cancelled 는 결과 자체가 무효라 직접 입력을 제공하지 않습니다.
        secondaryLabel={ocrFailed ? '그대로 직접 입력' : undefined}
        onSecondary={ocrFailed ? () => setDismissedOcrFailure(true) : undefined}
      />

      <ErrorDialog
        open={saveError !== null}
        title="저장하지 못했어요"
        message={saveError ?? ''}
        onRetry={() => {
          setSaveError(null);
          void doSave();
        }}
      />

      <LowConfidenceConfirmDialog
        open={lowConfidenceConfirmOpen}
        itemNames={lowConfidenceItemNames}
        onConfirm={handleLowConfidenceConfirm}
        onCancel={() => setLowConfidenceConfirmOpen(false)}
      />
    </div>
  );
}
