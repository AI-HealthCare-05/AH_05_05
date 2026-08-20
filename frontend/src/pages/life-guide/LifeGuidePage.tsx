import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { BottomTabbar, Card, Header, type TabKey } from '@/shared/ui';
import {
  getLifeGuide,
  type LifeGuide,
  type RecordGuide,
  type RoutinePeriod,
} from '@/entities/life-guide';

/**
 * REQ-CARE-004 · 화면 15 생활관리 가이드 — LLM 결과를 보여주는 화면.
 *
 * 의도적으로 넣지 않은 것:
 * - **완료 체크박스.** REQ-CARE-004에서 두지 않기로 확정했습니다. 체크 상태를 소비하는
 *   기능이 없는데 퇴원 직후 환자에게 미완료 항목이 부담으로 작용합니다.
 *   `todayRoutine`은 체크리스트가 아니라 하루 흐름 안내입니다.
 * - **즉시 연락할 증상 접기.** 안전 정보라 항상 펼친 상태로 둡니다.
 *
 * 기록이 2건 이상이면 반드시 섹션을 분리합니다 — 생활관리는 진단에 종속되고 지침이
 * 상충할 수 있어(무릎은 걷기 권장, 다른 질환은 활동 제한) 합치면 어느 기록의 지침인지
 * 알 수 없습니다.
 */
const PERIOD_LABEL: Record<RoutinePeriod, string> = {
  morning: '아침',
  day: '낮',
  evening: '저녁',
};

export function LifeGuidePage() {
  const navigate = useNavigate();
  const [guide, setGuide] = useState<LifeGuide | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLifeGuide().then((data) => {
      if (!cancelled) setGuide(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 이번 범위에 있는 탭만 이동합니다. 나머지는 화면이 아직 없습니다. */
  function handleTabChange(key: TabKey) {
    if (key === 'life') return;
    if (key === 'chat') {
      navigate('/dev/chat');
      return;
    }
    toast('이 탭 화면은 아직 구현 전입니다.');
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="생활관리" />

      <main className="flex flex-1 flex-col gap-5 px-page-x py-4">
        {guide === null ? (
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        ) : guide.records.length === 0 ? (
          <Card title="아직 안내가 없어요">
            진료기록을 등록하면 그에 맞는 생활관리 안내를 만들어 드립니다.
          </Card>
        ) : (
          guide.records.map((record) => <RecordGuideSection key={record.recordId} record={record} />)
        )}
      </main>

      <BottomTabbar active="life" onChange={handleTabChange} />
    </div>
  );
}

function RecordGuideSection({ record }: { record: RecordGuide }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold text-foreground">{record.label}</h2>

      <Card title="오늘의 관리">
        <div className="flex flex-col gap-2 py-1">
          {record.todayRoutine.map((item, index) => (
            <div key={`${item.period}-${index}`} className="flex items-baseline gap-3">
              <span className="w-8 shrink-0 font-bold text-foreground">
                {PERIOD_LABEL[item.period]}
              </span>
              {/* time 이 null 인 항목은 00:00 같은 값을 만들지 않고 — 로 둡니다. */}
              <span className="w-12 shrink-0 tabular-nums text-muted-foreground">
                {item.time ?? '—'}
              </span>
              <span className="text-foreground">{item.text}</span>
            </div>
          ))}
        </div>
      </Card>

      {record.sections.map((section) => (
        <Card key={section.title} title={section.title}>
          {section.text}
        </Card>
      ))}

      <Card tone="warning" title={record.emergencySigns.title}>
        <ul className="flex flex-col gap-1 py-1">
          {record.emergencySigns.items.map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden className="text-warning-strong">
                ·
              </span>
              <span className="text-foreground">{item}</span>
            </li>
          ))}
        </ul>
        <span className="block pt-1 font-bold text-warning-strong">
          {record.emergencySigns.action}
        </span>
      </Card>
    </section>
  );
}
