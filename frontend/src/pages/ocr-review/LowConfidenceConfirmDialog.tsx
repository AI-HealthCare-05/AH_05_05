import {
  Button,
  Card,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui';

/**
 * `O08 낮은 신뢰도 항목 확인` (Figma node 205:25)
 *
 * REQ-DOC-003: "저장하기는 바로 다음 화면으로 넘어가지 않고 '낮은 신뢰도 항목을 모두
 * 확인하셨나요?' 확인 모달을 1회 노출(미확인 항목 수 표시), 확인 시에만 이동."
 *
 * Figma는 "진단명과 복약 정보를 다시 확인해주세요."처럼 항목 이름이 하드코딩된
 * 2개짜리 예시로 그려져 있습니다. 실제로는 어떤 항목이 낮은 신뢰도인지가 매번 달라지므로
 * 이름 목록을 넘겨받아 문장을 조립합니다(조사도 받침에 맞춰 바꿉니다).
 */

export interface LowConfidenceConfirmDialogProps {
  open: boolean;
  /** 낮은 신뢰도로 판정된 항목 이름들. 예: ['진단명', '복약 정보'] */
  itemNames: string[];
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 한글 음절의 받침 유무. 한글이 아니면 받침 없는 것으로 봅니다.
 * 항목 이름에 "복약 정보(2건)"처럼 괄호가 붙는 경우가 있어, 닫는 괄호는 벗겨내고
 * 안쪽 마지막 글자로 판정합니다("(2건)을"이 자연스럽고 "(2건)를"은 어색합니다).
 */
function hasFinalConsonant(word: string): boolean {
  const last = word.trim().replace(/[)\]}]+$/, '').at(-1);
  if (!last) return false;
  const code = last.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return false;
  return (code - 0xac00) % 28 !== 0;
}

/**
 * 항목 이름들을 자연스러운 한국어 문장으로 잇습니다.
 *   1개  — "진단명을"
 *   2개  — "진단명과 복약 정보를"   (Figma 문구와 동일)
 *   3개+ — "진단명, 수술명, 복용일수를"
 */
function joinItemNames(names: string[]): string {
  if (names.length === 0) return '';

  let joined: string;
  if (names.length === 1) {
    joined = names[0];
  } else if (names.length === 2) {
    joined = `${names[0]}${hasFinalConsonant(names[0]) ? '과' : '와'} ${names[1]}`;
  } else {
    joined = names.join(', ');
  }

  return `${joined}${hasFinalConsonant(joined) ? '을' : '를'}`;
}

export function LowConfidenceConfirmDialog({
  open,
  itemNames,
  onConfirm,
  onCancel,
}: LowConfidenceConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent showCloseButton={false} className="bg-warning-bg">
        <DialogHeader>
          <DialogTitle>낮은 신뢰도 항목을 모두 확인하셨나요?</DialogTitle>
        </DialogHeader>

        <Card tone="warning" title={`${itemNames.length}개 항목 미확인`}>
          <DialogDescription>
            {joinItemNames(itemNames)} 다시 확인해주세요.
          </DialogDescription>
        </Card>

        <DialogFooter>
          <Button onClick={onConfirm}>확인 후 저장</Button>
          <Button variant="secondary" onClick={onCancel}>
            항목 다시 확인
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
