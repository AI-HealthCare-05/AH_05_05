import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';
import type { DoseRecord, MedicationOverview } from '@/entities/medication/types';
import { useChallengeMock } from '@/features/challenges';
import { BottomTabbar, DrawnChevron, Header } from '@/shared/ui';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import { HomeSectionPanel, HomeSectionTabs } from '@/pages/home/HomePage';
import { MedicationTimeline } from '@/pages/home/MedicationTimeline';
import { HomeChallengeSummary } from './HomeChallengeSummary';

const PREVIEW_EVENING = new Date(2026, 8, 13, 19, 0);

/** Isolated, in-memory Home demo. Never invokes the production record loaders/savers. */
export function ChallengeHomePreviewPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'medication' | 'supplement'>('medication');
  const { medicationEpisodes, participations, demoToday, setMedicationDose } = useChallengeMock();
  const overviews: MedicationOverview[] = medicationEpisodes.map((episode, index) => {
    const days = Math.round((Date.parse(episode.endDate) - Date.parse(episode.startDate)) / 86_400_000) + 1;
    return {
      recordId: episode.recordId,
      alias: episode.label,
      documentImageUrl: '',
      start: { date: episode.startDate, slot: 'morning' },
      endDate: episode.endDate,
      daysRemaining: 1,
      isFinished: false,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
      medications: (index === 0 ? ['아세트아미노펜정500mg', '로라타딘정10mg'] : ['예시 처방약 A', '예시 처방약 B']).map((name, medicationIndex) => ({
        medicationId: episode.recordId * 10 + medicationIndex,
        name,
        dose: '1정',
        days,
        daysRemaining: 1,
        slots: episode.slots,
        asNeeded: false,
      })),
    };
  });
  const records: DoseRecord[] = medicationEpisodes.filter((episode) => episode.todayTaken).map((episode) => ({
    recordId: episode.recordId, date: demoToday, slot: 'evening', taken: true,
  }));

  return (
    <div className="mx-auto flex h-dvh min-h-dvh w-full max-w-app flex-col overflow-hidden bg-background">
      <Header title={<img src="/images/rxvita-logo-480.png" alt="RxVita" className="h-6 w-auto" />} />
      <p className="shrink-0 bg-muted-bg px-page-x py-1.5 text-center text-micro text-tertiary-foreground">
        목업 홈 · 2026.09.13 저녁 · 실제 복약 기록에 저장되지 않아요
      </p>
      <main className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5 [scrollbar-gutter:stable]">
        <HomeSectionTabs activeTab={tab} onChange={setTab}>
          <HomeSectionPanel value={tab}>
            {tab === 'medication' ? (
              <MedicationTimeline
                referenceTime={PREVIEW_EVENING}
                overviews={overviews}
                doseRecords={records}
                currentDate={demoToday}
                onDoseChange={(ids, slot, taken) => {
                  if (!taken && medicationEpisodes.some((episode) => ids.includes(episode.recordId) && participations.some((item) => item.episodeId === episode.id && item.status === 'achieved'))) {
                    toast.info('달성 후 기록 취소·배지 회수 정책은 협의 중이라 이 목업에서는 취소하지 않아요.');
                    return Promise.resolve(false);
                  }
                  if (slot === 'evening') setMedicationDose(ids, taken);
                  return Promise.resolve(true);
                }}
                onMemo={() => toast.info('복약 메모 작성은 이 챌린지 목업의 검토 범위에 포함되지 않아요.')}
              />
            ) : (
              <section aria-label="오늘의 영양제" className="space-y-3 rounded-card bg-card p-5 shadow-card">
                <h2 className="text-base font-bold">저녁 19:00</h2>
                <p className="text-sm">오메가3 <span className="float-right text-muted-foreground">1캡슐</span></p>
                <p className="text-caption text-muted-foreground">영양제는 표시용 예시예요. 이번 연동 검토는 복약 탭에서 진행해요.</p>
              </section>
            )}
          </HomeSectionPanel>
        </HomeSectionTabs>
        <HomeChallengeSummary />
        <p className="text-caption text-muted-foreground">9월 7일 처방은 13/14회 예시예요. 챌린지 참여 후 저녁 기록으로 개별 달성과 배지 획득을 확인해보세요.</p>
        <Link to="/dev/challenges/tailored/medication" className="min-h-touch py-3 text-right text-sm font-bold text-primary">
          복약 챌린지 참여 처방 확인 <DrawnChevron direction="right" className="inline size-3.5 align-middle" />
        </Link>
      </main>
      <BottomTabbar active="home" className="border-t border-border" onChange={(key) => {
        if (key === 'home') return;
        navigate(key === 'my' ? '/dev/my-authenticated' : TAB_ROUTES[key]);
      }} />
    </div>
  );
}
