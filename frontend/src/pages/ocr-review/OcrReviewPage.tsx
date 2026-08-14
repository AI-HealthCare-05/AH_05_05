import { useEffect, useState, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button, Card, Header, Input, StatusBadge } from '@/shared/ui';
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

  useEffect(() => {
    let cancelled = false;
    getOcrResult(batchId).then((data) => {
      if (cancelled) return;
      setResult(data);
      setDiagnosis(data.fields.diagnosis.value ?? '');
      setSurgery(data.fields.surgery.value ?? '');
      setDischargeDate(data.fields.dischargeDate.value ?? '');
      setMedicationDays(data.fields.medicationDays.value != null ? String(data.fields.medicationDays.value) : '');
      setMedications(data.medications);
      setAdvices(data.advices);
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
    if (result.fields.diagnosis.confidence === 'low') lowConfidenceItemNames.push('진단명');
    if (result.fields.surgery.confidence === 'low') lowConfidenceItemNames.push('수술명');
    if (result.fields.dischargeDate.confidence === 'low') lowConfidenceItemNames.push('퇴원일');
    if (result.fields.medicationDays.confidence === 'low') lowConfidenceItemNames.push('복용일수');
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
    } finally {
      setSaving(false);
    }
  }

  if (!result) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="OCR 결과 확인" onBack={() => navigate(-1)} />
        <main className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        </main>
      </div>
    );
  }

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
            <ConfidenceBadge confidence={result.fields.diagnosis.confidence} />
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
            <ConfidenceBadge confidence={result.fields.surgery.confidence} />
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
            <ConfidenceBadge confidence={result.fields.dischargeDate.confidence} />
          </div>
          <Input
            id="dischargeDate"
            type="date"
            value={dischargeDate}
            onChange={(e) => setDischargeDate(e.target.value)}
            onClick={openDatePicker}
            hint={dischargeDate ? undefined : '추출된 퇴원일이 없습니다. 달력에서 선택해주세요.'}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="medicationDays" className="text-sm font-bold text-foreground">
              복용일수
            </label>
            <ConfidenceBadge confidence={result.fields.medicationDays.confidence} />
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
          <Button onClick={handleSaveClick} disabled={saving}>
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

      <LowConfidenceConfirmDialog
        open={lowConfidenceConfirmOpen}
        itemNames={lowConfidenceItemNames}
        onConfirm={handleLowConfidenceConfirm}
        onCancel={() => setLowConfidenceConfirmOpen(false)}
      />
    </div>
  );
}
