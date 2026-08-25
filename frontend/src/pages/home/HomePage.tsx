import { useEffect, useState, type ComponentType } from 'react';
import {
  Check,
  ChevronRight,
  MessageCircle,
  Pill,
  Sprout,
  UserRound,
} from 'lucide-react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { getMedicationOverview, type MedicationOverview } from '@/entities/medication';
import {
  BottomTabbar,
  Button,
  Card,
  Header,
  PokeFeatureCarousel,
  type TabKey,
} from '@/shared/ui';
import { LoginPromptSheet } from './LoginPromptSheet';

export type MedicationHomeState = 'empty' | 'active' | 'ended';

interface HomePageProps {
  authenticatedOverride?: boolean;
  medicationState?: MedicationHomeState;
  medicationOverviewLoader?: () => Promise<MedicationOverview>;
}

interface FeatureItem {
  key: Exclude<TabKey, 'home' | 'my'>;
  title: string;
  description: string;
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  emphasis?: 'warning';
}

const DEFAULT_FEATURES: FeatureItem[] = [
  {
    key: 'medication',
    title: '복용약 관리',
    description: '약봉투 등록 · 시간 알림',
    icon: Pill,
  },
  {
    key: 'supplement',
    title: '영양제 관리',
    description: '성분 합계 · 상한 비교',
    icon: Sprout,
  },
  {
    key: 'chat',
    title: 'AI 상담',
    description: '근거와 함께 답해드려요',
    icon: MessageCircle,
  },
];

const ACTIVE_FEATURES: FeatureItem[] = [
  {
    key: 'medication',
    title: '복용약 관리',
    description: '약 4개 · 8월 28일까지',
    icon: Pill,
  },
  {
    key: 'supplement',
    title: '영양제 관리',
    description: '비타민 A 상한 초과',
    icon: Sprout,
    emphasis: 'warning',
  },
  {
    key: 'chat',
    title: 'AI 상담',
    description: '근거와 함께 답해드려요',
    icon: MessageCircle,
  },
];

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

export function HomePage({
  authenticatedOverride,
  medicationState,
  medicationOverviewLoader = getMedicationOverview,
}: HomePageProps) {
  const navigate = useNavigate();
  const { authenticated } = useSession();
  const isAuthenticated = authenticatedOverride ?? authenticated;
  const [loginPromptOpen, setLoginPromptOpen] = useState(false);
  const [medicationOverview, setMedicationOverview] = useState<MedicationOverview | null>(null);
  const [medicationLoadError, setMedicationLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || medicationState !== undefined) return;

    let cancelled = false;
    setMedicationOverview(null);
    setMedicationLoadError(null);
    medicationOverviewLoader()
      .then((overview) => {
        if (!cancelled) setMedicationOverview(overview);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMedicationLoadError(
            error instanceof Error ? error.message : '복약 정보를 불러오지 못했어요.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, medicationOverviewLoader, medicationState]);

  const resolvedMedicationState =
    medicationState ??
    (medicationOverview ? medicationHomeStateFromOverview(medicationOverview) : null);
  const features =
    isAuthenticated && resolvedMedicationState === 'active'
      ? ACTIVE_FEATURES
      : DEFAULT_FEATURES;

  function openFeature(key: FeatureItem['key']) {
    if (!isAuthenticated) {
      setLoginPromptOpen(true);
      return;
    }
    navigate(TAB_ROUTES[key]);
  }

  function handleTabChange(key: TabKey) {
    if (key === 'home') return;
    if (key === 'my') {
      navigate('/my');
      return;
    }
    if (!isAuthenticated) {
      setLoginPromptOpen(true);
      return;
    }
    navigate(TAB_ROUTES[key]);
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      {isAuthenticated ? (
        <Header
          title="포케"
          right={
            <button
              type="button"
              aria-label="마이페이지"
              className="flex size-touch items-center justify-center text-muted-foreground"
              onClick={() => navigate('/my')}
            >
              <UserRound aria-hidden className="size-6" />
            </button>
          }
        />
      ) : (
        <header className="flex h-header shrink-0 items-center justify-between bg-card px-page-x">
          <h1 className="text-xl font-bold text-foreground">포케</h1>
          <button
            type="button"
            className="min-h-touch text-sm font-bold text-primary-strong"
            onClick={() => navigate('/login')}
          >
            로그인
          </button>
        </header>
      )}

      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        {isAuthenticated ? (
          medicationLoadError ? (
            <Card title="복약 정보를 불러오지 못했어요">{medicationLoadError}</Card>
          ) : resolvedMedicationState ? (
            <LoggedInHero
              state={resolvedMedicationState}
              onUpload={() => navigate('/document-upload')}
            />
          ) : (
            <div
              role="status"
              aria-label="복약 정보 불러오는 중"
              className="min-h-84 animate-pulse rounded-card bg-muted-bg"
            />
          )
        ) : (
          <PokeFeatureCarousel />
        )}

        <section aria-label="주요 기능" className="flex flex-col gap-3">
          {features.map((feature) => (
            <FeatureRow key={feature.key} feature={feature} onClick={() => openFeature(feature.key)} />
          ))}
        </section>

        {!isAuthenticated && (
          <p className="mt-auto py-4 text-center text-sm text-disabled-foreground">
            기능을 쓰려면 로그인이 필요해요
          </p>
        )}
      </main>

      <BottomTabbar
        active="home"
        onChange={handleTabChange}
        className="border-t border-border"
      />
      <LoginPromptSheet
        open={loginPromptOpen}
        onOpenChange={setLoginPromptOpen}
        onLogin={() => navigate('/login')}
      />
    </div>
  );
}

function FeatureRow({ feature, onClick }: { feature: FeatureItem; onClick: () => void }) {
  const Icon = feature.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-18 w-full items-center gap-4 rounded-card bg-card px-4 py-3 text-left shadow-card"
    >
      <span
        className="flex size-12 shrink-0 items-center justify-center rounded-pill bg-muted-bg text-muted-foreground"
      >
        <Icon aria-hidden className="size-6" />
      </span>
      <span className="min-w-0 flex-1">
        <strong className="block text-lg text-foreground">{feature.title}</strong>
        <span
          className={`block truncate text-sm ${
            feature.emphasis === 'warning' ? 'text-warning-strong' : 'text-muted-foreground'
          }`}
        >
          {feature.description}
        </span>
      </span>
      <ChevronRight aria-hidden className="size-5 shrink-0 text-disabled-foreground" />
    </button>
  );
}

function LoggedInHero({ state, onUpload }: { state: MedicationHomeState; onUpload: () => void }) {
  if (state === 'empty') {
    return (
      <Card className="gap-4 bg-primary-bg p-5">
        <div>
          <p className="text-xl font-bold text-foreground">약봉투를 등록해 주세요</p>
          <p className="mt-1 text-sm text-muted-foreground">사진 한 장이면 오늘부터 알림을 드릴게요.</p>
        </div>
        <Button onClick={onUpload}>약봉투 등록</Button>
      </Card>
    );
  }

  if (state === 'ended') {
    return (
      <Card className="gap-4 p-5">
        <div>
          <p className="text-xl font-bold text-foreground">복용이 끝났어요</p>
          <p className="mt-1 text-sm text-muted-foreground">새 처방을 받았다면 약봉투를 다시 등록해 주세요.</p>
        </div>
        <Button variant="secondary" onClick={onUpload}>
          새 약봉투 등록
        </Button>
      </Card>
    );
  }

  return (
    <section className="flex flex-col gap-3" aria-labelledby="today-medication-title">
      <div className="flex items-center justify-between">
        <h2 id="today-medication-title" className="text-xl font-bold text-foreground">
          오늘의 복약
        </h2>
        <span className="text-base text-muted-foreground tnum">4일째 · 3일 남음</span>
      </div>
      <div
        role="group"
        aria-label="하루 복약 시간표"
        className="overflow-hidden rounded-card bg-card shadow-card"
      >
        <div
          role="group"
          aria-label="지난 복약"
          className="flex min-h-12 items-center gap-3 px-4 py-2 text-disabled-foreground"
        >
          <span className="flex size-5.5 shrink-0 items-center justify-center rounded-pill bg-muted-bg">
            <Check aria-hidden className="size-4" />
          </span>
          <span className="text-base tnum">기상 후 07:00</span>
          <span className="ml-auto text-sm">먹었어요</span>
        </div>

        <div role="group" aria-label="현재 복약" className="flex flex-col bg-primary-bg px-4 py-4">
          <div className="flex items-center gap-3">
            <span className="size-5.5 shrink-0 rounded-pill border-2 border-primary" />
            <p className="text-metric font-bold text-foreground tnum">아침 08:00</p>
            <span className="ml-auto rounded-pill bg-primary px-3 py-1 text-sm font-bold text-card">
              지금
            </span>
          </div>
          <ul aria-label="지금 먹을 약" className="ml-8.5 mt-2 flex flex-col gap-1">
            <li className="text-base text-foreground">
              셀레콕시브 <span className="text-muted-foreground">200mg</span>
            </li>
            <li className="text-base text-foreground">
              리바록사반 <span className="text-muted-foreground">10mg</span>
            </li>
            <li className="text-base text-foreground">
              파모티딘 <span className="text-muted-foreground">20mg</span>
            </li>
          </ul>
          <p className="ml-8.5 mt-2 text-sm text-muted-foreground">식사 후에 드세요</p>
          <Button fullWidth={false} className="ml-8.5 mt-3 w-auto gap-2 text-base tnum">
            <Check aria-hidden className="size-5" />
            3개 먹었어요
          </Button>
        </div>

        <div
          role="group"
          aria-label="다음 복약 점심"
          className="flex min-h-12 items-center gap-3 px-4 py-2"
        >
          <span className="size-5.5 shrink-0 rounded-pill border border-border" />
          <span className="text-base text-foreground tnum">점심 13:00</span>
          <span className="ml-auto text-base text-muted-foreground tnum">1개</span>
        </div>

        <div className="mx-4 border-t border-border">
          <div
            role="group"
            aria-label="다음 복약 저녁"
            className="flex min-h-12 items-center gap-3 py-2"
          >
            <span className="size-5.5 shrink-0 rounded-pill border border-border" />
            <span className="text-base text-foreground tnum">저녁 19:00</span>
            <span className="ml-auto text-base text-muted-foreground tnum">3개</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function medicationHomeStateFromOverview(overview: MedicationOverview): MedicationHomeState {
  if (overview.medications.length === 0) return 'empty';
  return overview.daysRemaining > 0 ? 'active' : 'ended';
}
