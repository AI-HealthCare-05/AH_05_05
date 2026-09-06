import { useEffect, useState } from 'react';
import type { FollowUpVisit, FollowUpVisitInput } from '@/entities/follow-up-visit';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
} from '@/shared/ui';

interface FollowUpVisitSheetProps {
  open: boolean;
  visit: FollowUpVisit | null;
  onOpenChange: (open: boolean) => void;
  onSave: (input: FollowUpVisitInput) => Promise<void>;
  onDelete: (visit: FollowUpVisit) => void;
}

export function FollowUpVisitSheet({
  open,
  visit,
  onOpenChange,
  onSave,
  onDelete,
}: FollowUpVisitSheetProps) {
  const [visitDate, setVisitDate] = useState('');
  const [visitTime, setVisitTime] = useState('');
  const [hospital, setHospital] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setVisitDate(visit?.visitDate ?? '');
    setVisitTime(visit?.visitTime ?? '');
    setHospital(visit?.hospital ?? '');
    setSaving(false);
  }, [open, visit]);

  async function save() {
    if (!visitDate || saving) return;
    setSaving(true);
    try {
      await onSave({
        visitDate,
        visitTime: visitTime || null,
        hospital: hospital.trim() || null,
      });
      onOpenChange(false);
    } catch {
      // 부모 화면의 ErrorDialog가 실패 내용을 보여주고 시트는 그대로 유지합니다.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" className="max-h-[90dvh] overflow-y-auto">
        <div aria-hidden className="mx-auto h-1 w-10 rounded-pill bg-border" />
        <DialogHeader>
          <DialogTitle>{visit ? '진료일정 수정' : '진료일정 추가'}</DialogTitle>
          <DialogDescription>진료일은 필수이고 병원과 시간은 나중에 정해도 돼요.</DialogDescription>
        </DialogHeader>
        <Input
          label="진료일"
          type="date"
          value={visitDate}
          onChange={(event) => setVisitDate(event.target.value)}
        />
        <Input
          label="진료 시간"
          type="time"
          value={visitTime}
          onChange={(event) => setVisitTime(event.target.value)}
        />
        <Input
          label="병원"
          maxLength={255}
          placeholder="병원 이름 (선택)"
          value={hospital}
          onChange={(event) => setHospital(event.target.value)}
        />
        <DialogFooter className="pt-2">
          <Button disabled={!visitDate || saving} onClick={() => void save()}>
            {saving ? '저장 중...' : '저장'}
          </Button>
          {visit && (
            <Button
              variant="secondary"
              className="text-danger-strong"
              disabled={saving}
              onClick={() => onDelete(visit)}
            >
              삭제
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
