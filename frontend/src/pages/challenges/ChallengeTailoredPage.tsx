import { Link, useLocation } from 'react-router';
import { Card, DrawnChevron } from '@/shared/ui';

function useChallengeBase() {
  const { pathname } = useLocation();
  return pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
}

const tailoredOptions = [
  {
    kind: 'medication',
    title: '내 복약 루틴',
    meta: '복용 중인 처방이 있어요',
    body: '예정된 시간의 복약 기록을 모아요. 참여 대상을 확인한 뒤 시작해요.',
  },
  {
    kind: 'supplement',
    title: '내 영양제 루틴',
    meta: '등록한 영양제가 있어요',
    body: '참여할 영양제를 선택하고 기존 복용 기록으로 이어가요.',
  },
  {
    kind: 'review',
    title: '이번 주 기록 돌아보기',
    meta: '지난 기록이 있어요',
    body: '복약·영양제·메모를 하나씩 확인하며 이번 주를 돌아봐요.',
  },
  {
    kind: 'visit',
    title: '다음 진료 준비',
    meta: '예정된 진료가 있어요',
    body: '진료 전에 복약·영양제·메모와 일정을 차근차근 확인해요.',
  },
] as const;

export interface ChallengeTailoredPageProps {
  empty?: boolean;
}

export function ChallengeTailoredPage({ empty = false }: ChallengeTailoredPageProps) {
  const base = useChallengeBase();
  const medicationPath = base.startsWith('/dev/') ? '/dev/medications' : '/medications';

  return (
    <main className="flex min-h-full flex-col gap-4 px-5 py-5">
      <div className="space-y-1">
        <h1 className="text-[22px] font-bold leading-8 text-foreground">맞춤 챌린지</h1>
        <p className="text-sm text-muted-foreground">
          {empty ? '맞춤 챌린지에 활용할 기록이 아직 없어요' : '등록한 기록에 맞춰 챌린지를 골라드려요'}
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {empty ? (
          <>
            <Link to={medicationPath} className="block">
              <Card className="gap-2 p-5 shadow-none">
                <h2 className="text-base font-bold text-foreground">등록한 기록이 있으면 맞춰드려요</h2>
                <p className="text-xs text-primary">자동 참여되지는 않아요</p>
                <p className="text-sm leading-6 text-muted-foreground">
                  복용 중인 약, 영양제 또는 예정된 진료를 등록하면 관련 챌린지를 볼 수 있어요.
                </p>
                <span className="text-sm font-bold text-primary">기록 등록하기 <DrawnChevron direction="right" className="inline size-3.5 align-middle" /></span>
              </Card>
            </Link>
            <Link to={`${base}/browse`} className="block">
              <Card className="gap-2 p-5 shadow-none">
                <h2 className="text-base font-bold text-foreground">다른 챌린지도 있어요</h2>
                <p className="text-xs text-primary">누구나 둘러볼 수 있어요</p>
                <p className="text-sm leading-6 text-muted-foreground">
                  공식 챌린지에 참여하거나 나만의 작은 목표를 만들어보세요.
                </p>
                <span className="text-sm font-bold text-primary">둘러보기 <DrawnChevron direction="right" className="inline size-3.5 align-middle" /></span>
              </Card>
            </Link>
          </>
        ) : (
          tailoredOptions.map((option) => (
            <Link key={option.kind} to={`${base}/tailored/${option.kind}`} className="block">
              <Card className="gap-2 p-5 shadow-none">
                <h2 className="text-base font-bold text-foreground">{option.title}</h2>
                <p className="text-xs text-primary">{option.meta}</p>
                <p className="text-sm leading-6 text-muted-foreground">{option.body}</p>
                <span className="text-right text-sm font-bold text-primary">자세히 보기 <DrawnChevron direction="right" className="inline size-3.5 align-middle" /></span>
              </Card>
            </Link>
          ))
        )}

        {!empty && <Link to={`${base}/create`} className="block">
          <Card className="gap-2 p-5 shadow-none">
            <h2 className="text-base font-bold text-foreground">나만의 작은 루틴</h2>
            <p className="text-xs text-primary">누구나 시작할 수 있어요</p>
            <p className="text-sm leading-6 text-muted-foreground">걷기, 물 마시기 등 목표를 정해요.</p>
            <span className="text-sm font-bold text-primary">챌린지 만들기 <DrawnChevron direction="right" className="inline size-3.5 align-middle" /></span>
          </Card>
        </Link>}
      </div>

      <Link to={base} className="min-h-touch py-3 text-center text-sm font-bold text-primary">
        챌린지로 돌아가기
      </Link>
    </main>
  );
}
