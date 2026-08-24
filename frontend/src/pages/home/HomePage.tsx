import { useState, type ComponentType } from 'react';
import {
  ChevronRight,
  Clock3,
  MessageCircle,
  Pill,
  ShoppingBag,
  Sprout,
  UserRound,
} from 'lucide-react';
import { useNavigate } from 'react-router';
import { useSession } from '@/app/SessionContext';
import { BottomTabbar, Button, Card, Header, type TabKey } from '@/shared/ui';
import { LoginPromptSheet } from './LoginPromptSheet';

export type MedicationHomeState = 'empty' | 'active' | 'ended';

interface HomePageProps {
  authenticatedOverride?: boolean;
  medicationState?: MedicationHomeState;
}

interface FeatureItem {
  key: Exclude<TabKey, 'home' | 'my'>;
  title: string;
  description: string;
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  tone: 'primary' | 'warning';
}

const GUEST_FEATURES: FeatureItem[] = [
  {
    key: 'medication',
    title: '복용약 관리',
    description: '약봉투 등록 · 시간 알림',
    icon: Pill,
    tone: 'primary',
  },
  {
    key: 'supplement',
    title: '영양제 관리',
    description: '성분 합계 · 상한 비교',
    icon: Sprout,
    tone: 'primary',
  },
  {
    key: 'chat',
    title: 'AI 상담',
    description: '근거와 함께 답해드려요',
    icon: MessageCircle,
    tone: 'warning',
  },
];

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

export function HomePage({ authenticatedOverride, medicationState = 'empty' }: HomePageProps) {
  const navigate = useNavigate();
  const { authenticated } = useSession();
  const isAuthenticated = authenticatedOverride ?? authenticated;
  const [loginPromptOpen, setLoginPromptOpen] = useState(false);

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
          <LoggedInHero state={medicationState} onUpload={() => navigate('/document-upload')} />
        ) : (
          <GuestCarousel />
        )}

        <section aria-label="주요 기능" className="flex flex-col gap-3">
          {GUEST_FEATURES.map((feature) => (
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

function GuestCarousel() {
  const [activeBannerIndex, setActiveBannerIndex] = useState(0);
  const banners = [
    {
      title: '약봉투를 찍으면\n먹을 시간을 알려드려요',
      description: '약 이름을 몰라도 됩니다. 사진 한 장으로 등록해요.',
      icon: ShoppingBag,
      tone: 'bg-primary-bg text-primary',
    },
    {
      title: '영양제 성분을\n한눈에 더해드려요',
      description: '등록한 제품끼리 성분 합계와 상한을 비교해요.',
      icon: Sprout,
      tone: 'bg-warning-bg text-warning',
    },
    {
      title: '내 약을 바탕으로\n차분하게 답해드려요',
      description: '확인할 수 있는 근거가 있을 때 함께 보여드려요.',
      icon: MessageCircle,
      tone: 'bg-muted-bg text-primary-strong',
    },
  ] as const;

  return (
    <section aria-label="포케 기능 소개" className="flex flex-col gap-3">
      <div
        className="-mr-page-x flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1"
        onScroll={(event) => {
          const children = Array.from(event.currentTarget.children) as HTMLElement[];
          const firstOffset = children[0]?.offsetLeft ?? 0;
          const nextIndex = children.reduce((closestIndex, child, index) => {
            const closestDistance = Math.abs(
              children[closestIndex].offsetLeft - firstOffset - event.currentTarget.scrollLeft,
            );
            const childDistance = Math.abs(
              child.offsetLeft - firstOffset - event.currentTarget.scrollLeft,
            );
            return childDistance < closestDistance ? index : closestIndex;
          }, 0);
          setActiveBannerIndex(nextIndex);
        }}
      >
        {banners.map(({ title, description, icon: Icon, tone }) => (
          <article
            key={title}
            className={`flex min-h-64 min-w-[88%] snap-start flex-col rounded-card p-5 shadow-card ${tone}`}
          >
            <span className="flex size-12 items-center justify-center rounded-pill bg-card/80">
              <Icon aria-hidden className="size-6" />
            </span>
            <h2 className="mt-6 whitespace-pre-line text-2xl font-bold text-foreground">{title}</h2>
            <p className="mt-auto text-base text-muted-foreground">{description}</p>
          </article>
        ))}
      </div>
      <div
        aria-label={`현재 배너 ${activeBannerIndex + 1} / ${banners.length}`}
        className="flex justify-center gap-2"
      >
        {banners.map((banner, index) => (
          <span
            aria-hidden
            key={banner.title}
            className={
              index === activeBannerIndex
                ? 'h-1.5 w-5 rounded-pill bg-primary'
                : 'size-1.5 rounded-pill bg-border'
            }
          />
        ))}
      </div>
    </section>
  );
}

function FeatureRow({ feature, onClick }: { feature: FeatureItem; onClick: () => void }) {
  const Icon = feature.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-20 w-full items-center gap-4 rounded-card bg-card px-4 py-3 text-left shadow-card"
    >
      <span
        className={`flex size-12 shrink-0 items-center justify-center rounded-pill ${
          feature.tone === 'warning'
            ? 'bg-warning-bg text-warning'
            : 'bg-primary-bg text-primary-strong'
        }`}
      >
        <Icon aria-hidden className="size-6" />
      </span>
      <span className="min-w-0 flex-1">
        <strong className="block text-lg text-foreground">{feature.title}</strong>
        <span className="block truncate text-sm text-muted-foreground">{feature.description}</span>
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
        <span className="text-sm text-muted-foreground">3일 남음</span>
      </div>
      <Card tone="info" className="gap-4 p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-12 items-center justify-center rounded-pill bg-card text-primary">
            <Clock3 aria-hidden className="size-6" />
          </span>
          <div>
            <p className="text-xl font-bold text-foreground tnum">아침 08:00</p>
            <p className="text-sm text-muted-foreground">셀레콕시브 · 리바록사반 · 파모티딘</p>
          </div>
        </div>
        <Button>먹었어요</Button>
      </Card>
    </section>
  );
}
