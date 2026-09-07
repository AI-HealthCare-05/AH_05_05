import { useMemo, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router';
import { useChallengeMock } from '@/features/challenges';
import { Button, Card } from '@/shared/ui';

type TailoredKind = 'medication' | 'supplement' | 'review' | 'visit';

const definitionByKind: Record<TailoredKind, string> = {
  medication: 'medication-routine',
  supplement: 'supplement-routine',
  review: 'review-records',
  visit: 'visit-records',
};

const supplements = [
  { id: 'omega-3', label: '오메가3 · 저녁' },
  { id: 'multivitamin', label: '종합비타민 · 아침' },
  { id: 'probiotics', label: '유산균 · 아침' },
] as const;

const medicationEpisodes = [
  { id: 'prescription-sep-07-cold', label: '감기약 · 09.07 ~ 09.13', detail: '아침 · 점심 · 저녁 · 예정된 복용 9회' },
  { id: 'prescription-sep-07', label: '9월 7일 처방 · 09.07 ~ 09.13', detail: '아침 · 저녁 · 예정된 복용 14회' },
] as const;

function isTailoredKind(value: string | undefined): value is TailoredKind {
  return value === 'medication' || value === 'supplement' || value === 'review' || value === 'visit';
}

export function ChallengeTargetPage() {
  const { kind } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { joinChallenge, participations } = useChallengeMock();
  const base = pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const storedSupplementTargets = participations.find(
    (participation) => participation.challengeId === definitionByKind.supplement,
  )?.targetIds;
  const storedMedicationTargets = participations.find(
    (participation) => participation.challengeId === definitionByKind.medication,
  )?.targetIds;
  const [selectedSupplements, setSelectedSupplements] = useState<string[]>(() =>
    storedSupplementTargets ? [...storedSupplementTargets] : ['omega-3', 'multivitamin'],
  );
  const [selectedMedications, setSelectedMedications] = useState<string[]>(() =>
    storedMedicationTargets ? [...storedMedicationTargets] : ['prescription-sep-07-cold'],
  );

  const selectedSummary = useMemo(
    () => supplements.filter((item) => selectedSupplements.includes(item.id)).map((item) => item.label.split(' · ')[0]),
    [selectedSupplements],
  );
  const selectedMedicationSummary = useMemo(
    () => medicationEpisodes.filter((item) => selectedMedications.includes(item.id)).map((item) => item.label.split(' · ')[0]),
    [selectedMedications],
  );

  if (!isTailoredKind(kind)) {
    return <Navigate to={`${base}/tailored`} replace />;
  }

  const copy = {
    medication: {
      title: '내 복약 루틴',
      subtitle: '기록 연동 · 참여 대상 확인',
      action: '이 대상으로 참여하기',
    },
    supplement: {
      title: '내 영양제 루틴',
      subtitle: '참여할 영양제를 선택해주세요',
      action: '선택한 영양제로 참여하기',
    },
    review: {
      title: '이번 주 기록 돌아보기',
      subtitle: '09.07 ~ 09.13 기록 확인',
      action: '이 기록으로 참여하기',
    },
    visit: {
      title: '다음 진료 준비',
      subtitle: '2026.09.21 진료 일정',
      action: '이 일정으로 참여하기',
    },
  }[kind];

  const handleJoin = () => {
    const selection = kind === 'medication'
      ? { targetIds: selectedMedications, targetSummary: selectedMedicationSummary.join(' · ') }
      : kind === 'supplement'
        ? { targetIds: selectedSupplements, targetSummary: selectedSummary.join(' · ') }
        : undefined;
    const participationId = joinChallenge(definitionByKind[kind], selection);
    navigate(`${base}/participations/${participationId}`);
  };

  return (
    <main className="flex min-h-full flex-col gap-4 px-5 py-5">
      <div className="space-y-1">
        <h1 className="text-[22px] font-bold leading-8 text-foreground">{copy.title}</h1>
        <p className="text-sm text-muted-foreground">{copy.subtitle}</p>
      </div>

      {kind === 'medication' && (
        <>
          <Card className="gap-2 p-5 shadow-none">
            <h2 className="text-base font-bold text-foreground">참여할 처방</h2>
            <p className="text-xs text-primary">선택한 처방 {selectedMedications.length}개 · 일정 연동</p>
            <div className="flex flex-col gap-2">
              {medicationEpisodes.map((episode) => (
                <label key={episode.id} className="flex min-h-touch items-start gap-2 py-1 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={selectedMedications.includes(episode.id)}
                    onChange={(event) => {
                      setSelectedMedications((current) =>
                        event.target.checked
                          ? [...current, episode.id]
                          : current.filter((id) => id !== episode.id),
                      );
                    }}
                    className="mt-0.5 size-5 shrink-0 accent-primary"
                  />
                  <span>
                    <strong className="block">{episode.label}</strong>
                    <span className="text-xs text-muted-foreground">{episode.detail}</span>
                  </span>
                </label>
              ))}
            </div>
            <p className="text-sm text-muted-foreground">
              선택 대상: {selectedMedicationSummary.length ? selectedMedicationSummary.join(' · ') : '없음'}
            </p>
          </Card>
          <InfoCard title="기록은 자동으로 반영돼요" meta="중간에 시작해도 참여 가능">
            홈·복약에서 남긴 기록이 반영돼요. 이미 지난 시간의 복용을 요구하지 않아요.
          </InfoCard>
          <InfoCard title="복용 일정이 바뀌면" meta="안전한 참여 원칙">
            처방 중단·변경 이후 일정은 다시 확인해요. 추가 복용을 유도하지 않아요.
          </InfoCard>
        </>
      )}

      {kind === 'supplement' && (
        <>
          <Card className="gap-3 p-5 shadow-none">
            <h2 className="text-base font-bold text-foreground">참여 대상</h2>
            <p className="text-xs text-primary">선택한 영양제 {selectedSupplements.length}개</p>
            <div className="flex flex-col gap-2">
              {supplements.map((supplement) => (
                <label key={supplement.id} className="flex min-h-touch items-center gap-2 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={selectedSupplements.includes(supplement.id)}
                    onChange={(event) => {
                      setSelectedSupplements((current) =>
                        event.target.checked
                          ? [...current, supplement.id]
                          : current.filter((id) => id !== supplement.id),
                      );
                    }}
                    className="size-5 accent-primary"
                  />
                  {supplement.label}
                </label>
              ))}
            </div>
            <p className="text-sm text-muted-foreground">
              선택 대상: {selectedSummary.length ? selectedSummary.join(' · ') : '없음'}
            </p>
          </Card>
          <InfoCard title="기록 방법" meta="기존 복용 기록 연동">
            선택한 영양제의 예정된 시간만 반영돼요. 새 제품을 추가로 먹을 필요는 없어요.
          </InfoCard>
          <InfoCard title="참여 기간" meta="예시 · 7일">
            09.07 ~ 09.13 · 대상과 기간을 확인하고 시작해요.
          </InfoCard>
        </>
      )}

      {kind === 'review' && (
        <InfoCard title="이번 주 기록" meta="09.07 ~ 09.13">
          복약 기록 6회 · 영양제 기록 5회 · 복약 메모는 아직 없어요.
        </InfoCard>
      )}

      {kind === 'visit' && (
        <>
          <InfoCard title="예정된 진료" meta="09.21 월요일">
            오후 2:00 · 내과 · 등록한 진료 일정 기준
          </InfoCard>
          <InfoCard title="기록이 없어도 괜찮아요" meta="진료 일정이 있으면 참여 가능">
            약·영양제·메모가 없으면 확인할 기록이 없는 상태로 안내해요.
          </InfoCard>
        </>
      )}

      <div className="mt-auto flex flex-col gap-2 pt-4">
        <Button
          onClick={handleJoin}
          disabled={(kind === 'supplement' && selectedSupplements.length === 0) || (kind === 'medication' && selectedMedications.length === 0)}
        >
          {copy.action}
        </Button>
        <Link to={`${base}/tailored`} className="min-h-touch py-3 text-center text-sm font-bold text-primary">
          맞춤 챌린지로 돌아가기
        </Link>
      </div>
    </main>
  );
}

function InfoCard({ title, meta, children }: { title: string; meta: string; children: string }) {
  return (
    <Card className="gap-2 p-5 shadow-none">
      <h2 className="text-base font-bold text-foreground">{title}</h2>
      <p className="text-xs text-primary">{meta}</p>
      <p className="text-sm leading-6 text-muted-foreground">{children}</p>
    </Card>
  );
}
