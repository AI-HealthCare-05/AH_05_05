import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Button } from '@/shared/ui';

export const TUTORIAL_SEEN_KEY = 'poke:tutorial-seen';

const TUTORIAL_STEPS = [
  {
    title: ['약봉투를 찍으면', '복약 일정이 만들어져요'],
    description: ['약 이름을 몰라도 돼요.', '사진 한 장으로 횟수와 기간까지 등록해요.'],
    illustration: '약봉투 · 카메라 일러스트',
    tone: 'bg-primary-bg',
  },
  {
    title: ['먹을 시간에', '알려드려요'],
    description: ['아침 · 점심 · 저녁 · 자기전.', '정해둔 시간에 알림을 보내드려요.'],
    illustration: '알림 · 시계 일러스트',
    tone: 'bg-info-bg',
  },
  {
    title: ['영양제 성분을', '더해서 보여드려요'],
    description: ['여러 제품의 성분 합계와 상한을', '한 화면에서 확인해요.'],
    illustration: '성분 합계 바 일러스트',
    tone: 'bg-warning-bg',
  },
  {
    title: ['내 약을 근거로', '답해드려요'],
    description: ['확인할 수 있는 출처가 있을 때', '함께 보여드려요.'],
    illustration: '챗봇 · 출처 일러스트',
    tone: 'bg-primary-bg',
  },
] as const;

export function TutorialPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (window.sessionStorage.getItem(TUTORIAL_SEEN_KEY) === 'true') {
      navigate('/home', { replace: true });
    }
  }, [navigate]);

  function finish() {
    window.sessionStorage.setItem(TUTORIAL_SEEN_KEY, 'true');
    navigate('/home', { replace: true });
  }

  function next() {
    if (step === TUTORIAL_STEPS.length - 1) {
      finish();
      return;
    }
    setStep((current) => current + 1);
  }

  const current = TUTORIAL_STEPS[step];

  return (
    <main className="relative mx-auto flex min-h-dvh w-full max-w-app flex-col bg-card px-page-x pb-[92px] pt-24">
      <button
        type="button"
        onClick={finish}
        className="absolute right-5 top-10 flex min-h-touch items-center px-2 text-sm font-medium text-tertiary-foreground"
      >
        건너뛰기
      </button>

      <div>
        <h1 className="text-[26px] font-bold leading-9 text-foreground">
          <span>{current.title[0]}</span>
          <br />
          <span>{current.title[1]}</span>
        </h1>
        <p className="mt-4 text-sm leading-[22px] text-muted-foreground">
          <span>{current.description[0]}</span>
          <br />
          <span>{current.description[1]}</span>
        </p>
      </div>

      <div
        className={`mt-9 flex h-[300px] items-center justify-center overflow-hidden rounded-card ${current.tone}`}
        aria-label="RxVita 기능 소개 일러스트"
      >
        <span className="text-caption text-tertiary-foreground">{current.illustration}</span>
      </div>

      <div className="mt-9 flex justify-center gap-1.5" aria-label={`튜토리얼 ${step + 1} / 4`}>
        {TUTORIAL_STEPS.map((_, index) => (
          <span
            key={index}
            aria-hidden="true"
            className={`h-2 rounded-pill ${index === step ? 'w-4 bg-primary' : 'size-2 bg-border'}`}
          />
        ))}
      </div>

      <div className="mt-auto grid grid-cols-2 gap-4 pt-[92px]">
        <Button variant="secondary" onClick={finish}>
          둘러보기
        </Button>
        <Button onClick={next}>{step === TUTORIAL_STEPS.length - 1 ? '시작하기' : '다음'}</Button>
      </div>
    </main>
  );
}
