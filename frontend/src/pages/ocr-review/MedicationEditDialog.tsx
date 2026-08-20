import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
} from '@/shared/ui';
import { cn } from '@/shared/lib/cn';
import type { OcrMedication } from '@/entities/document';

/**
 * `O07 복약 정보 편집 모달` (Figma node 204:25)
 *
 * Figma는 목록 상태만 그려져 있고 수정/추가 입력 폼은 미설계 상태입니다.
 * 아래는 기획에서 확정해 준 결정을 그대로 구현한 것입니다(Figma는 추후 이 코드에
 * 맞춰 따라 수정 예정):
 * - 모달을 추가로 띄우지 않고, Dialog 하나 안에서 'list' ↔ 'edit' 뷰를 전환합니다.
 * - 삭제 확인도 별도 모달 없이 해당 카드 안에서 인라인으로 처리합니다.
 * - 닫기 시 미저장 변경사항이 있으면 인라인 확인 바를 띄웁니다(Dialog 중첩 없음).
 *
 * ESC·오버레이 클릭·우상단 X도 전부 같은 onOpenChange(false) 경로를 타므로,
 * "닫기" 버튼뿐 아니라 이 경로들도 전부 미저장 변경 확인을 거칩니다.
 * 로컬 상태만 편집하고, [변경 저장]을 눌러야 `onSave`로 부모(07 화면)에 반영됩니다.
 */

export interface MedicationEditDialogProps {
  open: boolean;
  medications: OcrMedication[];
  onOpenChange: (open: boolean) => void;
  onSave: (medications: OcrMedication[]) => void;
}

type View = 'list' | 'edit';

interface EditingTarget {
  mode: 'add' | 'edit';
  tempId: string;
}

interface Draft {
  name: string;
  dose: string;
  timesPerDay: number | null;
  note: string;
}

const TIMES_PER_DAY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '1', label: '1회' },
  { value: '2', label: '2회' },
  { value: '3', label: '3회' },
  { value: '4', label: '4회' },
  { value: 'prn', label: '필요 시' },
];

/**
 * 복용 시점 프리셋 — 여러 개를 함께 고를 수 있는 토글입니다.
 *
 * "필요 시"는 넣지 않습니다. 바로 위 "1일 복용 횟수" Select에 이미 같은 선택지가 있어서
 * 둘 다 고르면 약 카드에 "필요 시 · 필요 시"로 찍힙니다. 복용 안 하는 조건은 Select
 * 한 곳에서만 정합니다.
 *
 * 프리셋에서 뺐다고 frequencyText의 "필요 시" 접두어 가드를 지우면 안 됩니다 — OCR이
 * note에 "필요 시, 6시간 이상 간격"처럼 보내오므로(entities/document/api.mock.ts 참고)
 * 그 가드는 지금도 실제로 동작합니다.
 *
 * "취침 전"은 09 화면의 취침 슬롯 자동 배정(slotsFromTiming)이 이 문구를 읽어 켜므로
 * 남겨둡니다. 09의 "취침" 슬롯과 이름이 겹쳐 보이지만 중복 입력이 아니라 그 입력값입니다.
 */
const NOTE_PRESETS = ['식전', '식후', '취침 전'];

const NOTE_SEPARATOR = ' · ';

/**
 * 프리셋을 note에 넣거나 뺍니다.
 *
 * 기존 텍스트를 덮어쓰지 않아서 (1) 여러 개를 함께 고를 수 있고 (2) OCR 원문
 * ("아침·저녁 식후")이 살아남습니다. 예전에는 칩을 누르면 note 전체가 프리셋 하나로
 * 교체돼서 조합이 불가능했습니다.
 */
function toggleNoteToken(note: string, token: string): string {
  const at = note.indexOf(token);
  if (at === -1) {
    const trimmed = note.trim();
    return trimmed ? `${trimmed}${NOTE_SEPARATOR}${token}` : token;
  }
  // 토큰에 붙어 있던 구분자까지 같이 걷어냅니다. OCR 원문은 쉼표로 나누기도 하므로
  // ("필요 시, 6시간 이상 간격") · 와 , 를 모두 구분자로 봅니다. 한 종류만 처리하면
  // 토글을 끈 뒤 "아침," 처럼 구분자가 덜렁 남습니다.
  const before = note.slice(0, at).replace(/[\s·,]+$/, '');
  const after = note.slice(at + token.length).replace(/^[\s·,]+/, '');
  const joined =
    before && after ? `${before}${NOTE_SEPARATOR}${after}` : `${before}${after}`;
  // 남은 양끝 구분자·공백을 한 번 더 걷어냅니다.
  return joined.replace(/^[\s·,]+|[\s·,]+$/g, '');
}

function timesPerDayToSelectValue(timesPerDay: number | null): string {
  return timesPerDay === null ? 'prn' : String(timesPerDay);
}

function selectValueToTimesPerDay(value: string): number | null {
  return value === 'prn' ? null : Number(value);
}

function frequencyText(med: OcrMedication): string {
  const note = med.note.trim();
  if (med.timesPerDay === null) {
    // note가 이미 "필요 시"로 시작하면(예: "필요 시, 6시간 이상 간격") 접두어를 또 붙이지 않습니다.
    return note.startsWith('필요 시') ? note : ['필요 시', note].filter(Boolean).join(' · ');
  }
  // note 가 비어 있으면 구분자만 덜렁 남으므로(예: "1일 2회 · ") 빈 값은 걸러냅니다.
  // 프리셋이 토글이 된 뒤로는 마지막 칩을 끄면 note 가 실제로 빈 문자열이 됩니다.
  return [`1일 ${med.timesPerDay}회`, note].filter(Boolean).join(' · ');
}

function toDraft(med: OcrMedication): Draft {
  return { name: med.name, dose: med.dose, timesPerDay: med.timesPerDay, note: med.note };
}

export function MedicationEditDialog({
  open,
  medications,
  onOpenChange,
  onSave,
}: MedicationEditDialogProps) {
  const initialMedsRef = useRef<OcrMedication[]>(medications);
  const newIdCounterRef = useRef(0);

  const [localMeds, setLocalMeds] = useState<OcrMedication[]>(medications);
  const [view, setView] = useState<View>('list');
  const [editingTarget, setEditingTarget] = useState<EditingTarget | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // 열릴 때마다(닫힌 상태 → 열린 상태) 부모가 들고 있는 최신 medications 기준으로
  // 모든 로컬 편집 상태를 초기화합니다.
  useEffect(() => {
    if (!open) return;
    initialMedsRef.current = medications;
    setLocalMeds(medications);
    setView('list');
    setEditingTarget(null);
    setDraft(null);
    setDeletingId(null);
    setShowCloseConfirm(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function hasUnsavedChanges(): boolean {
    return JSON.stringify(localMeds) !== JSON.stringify(initialMedsRef.current);
  }

  function handleAddStart() {
    newIdCounterRef.current += 1;
    setEditingTarget({ mode: 'add', tempId: `new_${newIdCounterRef.current}` });
    setDraft({ name: '', dose: '', timesPerDay: 1, note: '' });
    setView('edit');
  }

  function handleEditStart(tempId: string) {
    const med = localMeds.find((m) => m.tempId === tempId);
    if (!med) return;
    setEditingTarget({ mode: 'edit', tempId });
    setDraft(toDraft(med));
    setView('edit');
  }

  function handleCancelEdit() {
    setView('list');
    setEditingTarget(null);
    setDraft(null);
  }

  function handleConfirmEdit() {
    if (!draft || !editingTarget || !draft.name.trim()) return;
    setLocalMeds((prev) => {
      if (editingTarget.mode === 'add') {
        return [...prev, { tempId: editingTarget.tempId, ...draft }];
      }
      return prev.map((m) => (m.tempId === editingTarget.tempId ? { ...m, ...draft } : m));
    });
    setView('list');
    setEditingTarget(null);
    setDraft(null);
  }

  function handleConfirmDelete(tempId: string) {
    setLocalMeds((prev) => prev.filter((m) => m.tempId !== tempId));
    setDeletingId(null);
  }

  /** "닫기" 버튼, X 버튼, ESC, 오버레이 클릭 — 전부 이 함수를 거칩니다. */
  function requestClose() {
    if (view === 'edit') {
      setView('list');
      setEditingTarget(null);
      setDraft(null);
    }
    setDeletingId(null);

    if (hasUnsavedChanges()) {
      setShowCloseConfirm(true);
      return;
    }
    onOpenChange(false);
  }

  function handleSaveChanges() {
    onSave(localMeds);
    onOpenChange(false);
  }

  function handleDialogOpenChange(next: boolean) {
    if (next) {
      onOpenChange(true);
      return;
    }
    requestClose();
  }

  return (
    <Dialog open={open} onOpenChange={handleDialogOpenChange}>
      <DialogContent>
        {view === 'edit' && draft ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-1">
              <button
                type="button"
                aria-label="목록으로"
                onClick={handleCancelEdit}
                className="-ml-2.5 flex size-touch items-center justify-center text-xl text-foreground"
              >
                ←
              </button>
              <DialogTitle>{editingTarget?.mode === 'add' ? '약 추가' : '약 수정'}</DialogTitle>
            </div>
            <DialogDescription className="sr-only">
              {editingTarget?.mode === 'add' ? '새 약을 추가합니다.' : '약 정보를 수정합니다.'}
            </DialogDescription>

            <Input
              label="약품명"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="예: 셀레콕시브"
            />
            <Input
              label="용량"
              value={draft.dose}
              onChange={(e) => setDraft({ ...draft, dose: e.target.value })}
              placeholder="예: 200mg"
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-bold text-foreground">1일 복용 횟수</label>
              <Select
                value={timesPerDayToSelectValue(draft.timesPerDay)}
                onValueChange={(value) =>
                  setDraft({ ...draft, timesPerDay: selectValueToTimesPerDay(value) })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMES_PER_DAY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-bold text-foreground">복용 시점</label>
              <div className="flex flex-wrap gap-2">
                {NOTE_PRESETS.map((preset) => {
                  const selected = draft.note.includes(preset);
                  return (
                    <button
                      key={preset}
                      type="button"
                      aria-pressed={selected}
                      onClick={() =>
                        setDraft({ ...draft, note: toggleNoteToken(draft.note, preset) })
                      }
                      className={cn(
                        'min-h-touch rounded-pill border px-4 text-sm transition-colors',
                        selected
                          ? 'border-primary bg-primary-bg font-bold text-primary-strong'
                          : 'border-border bg-card text-foreground hover:bg-muted-bg',
                      )}
                    >
                      {preset}
                    </button>
                  );
                })}
              </div>
              <Input
                value={draft.note}
                onChange={(e) => setDraft({ ...draft, note: e.target.value })}
                placeholder="예: 아침·저녁 식후"
              />
            </div>

            <DialogFooter>
              <Button onClick={handleConfirmEdit} disabled={!draft.name.trim()}>
                확인
              </Button>
              <Button variant="secondary" onClick={handleCancelEdit}>
                취소
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>복약 정보 편집</DialogTitle>
              <DialogDescription>
                약을 추가하거나 추출 내용을 수정·삭제할 수 있습니다.
              </DialogDescription>
            </DialogHeader>

            <Button variant="secondary" onClick={handleAddStart}>
              + 약 추가
            </Button>

            <div className="flex max-h-[45vh] flex-col gap-2 overflow-y-auto">
              {localMeds.map((med) =>
                deletingId === med.tempId ? (
                  <div
                    key={med.tempId}
                    className="flex flex-col gap-3 rounded-card border border-border bg-card px-3.5 py-2.5"
                  >
                    <p className="text-sm text-foreground">이 약을 삭제할까요?</p>
                    <div className="flex gap-2">
                      <Button variant="danger" onClick={() => handleConfirmDelete(med.tempId)}>
                        삭제
                      </Button>
                      <Button variant="secondary" onClick={() => setDeletingId(null)}>
                        취소
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div
                    key={med.tempId}
                    className="flex flex-col gap-2 rounded-card border border-border bg-card px-3.5 py-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-bold text-foreground">
                        {med.name} {med.dose}
                      </p>
                      {med.confidence === 'low' && <StatusBadge type="review" />}
                    </div>
                    <p className="text-sm text-muted-foreground">{frequencyText(med)}</p>
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="secondary"
                        fullWidth={false}
                        className="h-touch px-4"
                        onClick={() => handleEditStart(med.tempId)}
                      >
                        수정
                      </Button>
                      <Button
                        variant="danger"
                        fullWidth={false}
                        className="h-touch px-4"
                        onClick={() => setDeletingId(med.tempId)}
                      >
                        삭제
                      </Button>
                    </div>
                  </div>
                ),
              )}
            </div>

            {showCloseConfirm ? (
              <div className="flex flex-col gap-2 rounded-card border border-border bg-muted-bg px-3.5 py-2.5">
                <p className="text-sm text-foreground">저장하지 않고 닫을까요?</p>
                <div className="flex gap-2">
                  <Button onClick={() => onOpenChange(false)}>닫고 나가기</Button>
                  <Button variant="secondary" onClick={() => setShowCloseConfirm(false)}>
                    계속 편집
                  </Button>
                </div>
              </div>
            ) : (
              <DialogFooter>
                <Button onClick={handleSaveChanges}>변경 저장</Button>
                <Button variant="secondary" onClick={requestClose}>
                  닫기
                </Button>
              </DialogFooter>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
