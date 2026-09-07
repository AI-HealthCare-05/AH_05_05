import { useEffect } from 'react';
import { Link, useLocation, useParams } from 'react-router';
import { useChallengeMock, type ChallengeChecklistItem } from '@/features/challenges';
import { Card } from '@/shared/ui';

const recordCopy: Record<ChallengeChecklistItem['destination'], { title: string; eyebrow: string }> = {
  medications: { title: '복약 기록', eyebrow: '복용 중인 처방' },
  supplements: { title: '영양제 기록', eyebrow: '먹고 있는 영양제' },
  notes: { title: '복약 메모', eyebrow: '복용 후 남긴 메모' },
  visit: { title: '진료 일정', eyebrow: '다가오는 일정' },
};

export function ChallengeRecordPage() {
  const { participationId, itemId } = useParams();
  const { pathname } = useLocation();
  const { participations, completeChecklist } = useChallengeMock();
  const base = pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const participation = participations.find((item) => item.id === participationId);
  const checklistItem = participation?.checklist?.find((item) => item.id === itemId);
  const returnPath = participation
    ? `${base}/participations/${participation.id}`
    : `${base}/tailored`;
  const hasSuccessfulContent = Boolean(participation && checklistItem?.available && recordCopy[checklistItem.destination]);

  useEffect(() => {
    if (hasSuccessfulContent && participation && checklistItem && !checklistItem.checked) {
      completeChecklist(participation.id, checklistItem.id);
    }
  }, [checklistItem, completeChecklist, hasSuccessfulContent, participation]);

  if (!participation || !checklistItem) {
    return (
      <RecordState
        title="기록을 불러오지 못했어요."
        description="챌린지에 연결된 기록인지 확인하고 다시 시도해주세요."
        returnPath={returnPath}
      />
    );
  }

  if (!checklistItem.available) {
    return (
      <RecordState
        title="확인할 기록이 아직 없어요."
        description="기록이 생기면 이 챌린지에서 다시 확인할 수 있어요."
        returnPath={returnPath}
      />
    );
  }

  const copy = recordCopy[checklistItem.destination];
  const period = participation.kind === 'review'
    ? '2026-09-07 ~ 2026-09-13'
    : checklistItem.destination === 'visit'
      ? '2026-09-21'
      : `${participation.startDate} ~ ${participation.endDate}`;

  return (
    <main className="flex min-h-full flex-col gap-4 px-5 py-5">
      <div className="space-y-1">
        <h1 className="text-[22px] font-bold leading-8 text-foreground">{copy.title}</h1>
        <p className="text-sm text-muted-foreground">{period}</p>
      </div>
      <p className="text-lg font-bold text-foreground">{copy.eyebrow}</p>
      <RecordContent destination={checklistItem.destination} />
      <p className="text-xs leading-5 text-muted-foreground">
        이 화면은 챌린지 흐름을 확인하기 위한 로컬 예시 기록이에요.
      </p>
      <Link to={returnPath} className="mt-auto min-h-touch rounded-button bg-primary px-4 py-4 text-center text-sm font-bold text-card">
        챌린지로 돌아가기
      </Link>
    </main>
  );
}

function RecordContent({ destination }: { destination: ChallengeChecklistItem['destination'] }) {
  if (destination === 'medications') {
    return (
      <Card className="gap-3 p-5 shadow-none">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-bold text-foreground">9월 7일 처방</h2>
          <span className="text-xs font-bold text-primary">이번 주 6회</span>
        </div>
        <p>아모잘탄정 5/50mg</p>
        <p>가스모틴정 5mg</p>
        <div className="grid gap-2 border-t border-border pt-3 text-sm">
          <RecordLine title="09.07 · 아침" detail="복약 기록 완료" />
          <RecordLine title="09.09 · 저녁" detail="복약 기록 완료" />
          <RecordLine title="09.12 · 아침" detail="복약 기록 완료" />
        </div>
      </Card>
    );
  }

  if (destination === 'supplements') {
    return (
      <Card className="gap-3 p-5 shadow-none">
        <RecordLine title="09.08 · 오메가3" detail="저녁 복용 기록 완료" />
        <RecordLine title="09.10 · 종합비타민" detail="아침 복용 기록 완료" />
        <RecordLine title="09.12 · 유산균" detail="아침 복용 기록 완료" />
      </Card>
    );
  }

  if (destination === 'visit') {
    return (
      <Card className="gap-3 p-5 shadow-none">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-bold text-foreground">9월 21일 월요일</h2>
          <span className="text-xs font-bold text-primary">8일 남음</span>
        </div>
        <p className="font-bold text-foreground">오후 2:00 · 내과</p>
        <p>메모 · 최근 기록을 준비해요</p>
      </Card>
    );
  }

  return (
    <Card className="gap-3 p-5 shadow-none">
      <p className="text-xs font-bold text-muted-foreground">09.03 · 오후 3:20</p>
      <h2 className="text-base font-bold text-foreground">아모잘탄정 5/50mg</h2>
      <p>약을 먹고 2시간 뒤 어지러움이 조금 있었어요.</p>
    </Card>
  );
}

function RecordLine({ title, detail }: { title: string; detail: string }) {
  return (
    <div>
      <p className="text-sm font-bold text-foreground">{title}</p>
      <p className="text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function RecordState({ title, description, returnPath }: { title: string; description: string; returnPath: string }) {
  return (
    <main className="flex min-h-full flex-col gap-4 px-5 py-5">
      <h1 className="text-[22px] font-bold leading-8 text-foreground">기록 확인</h1>
      <Card className="gap-2 p-5 shadow-none">
        <h2 className="text-base font-bold text-foreground">{title}</h2>
        <p className="text-sm leading-6 text-muted-foreground">{description}</p>
      </Card>
      <Link to={returnPath} className="mt-auto min-h-touch rounded-button bg-primary px-4 py-4 text-center text-sm font-bold text-card">
        챌린지로 돌아가기
      </Link>
    </main>
  );
}
