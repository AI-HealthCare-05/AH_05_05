import { useLocation, useNavigate } from 'react-router';
import { Button, Card, Header } from '@/shared/ui';

/**
 * 개발용 흐름 종료 화면 — REQ에 대응하는 실제 화면이 아니라 임시 스캐폴드입니다.
 * 그래서 pages/ 가 아니라 DevGallery와 같은 app/ 레벨에 둡니다.
 *
 * 문서 등록 흐름의 마지막 지점(복약 시간 설정 완료 / 복약 정보 없어 건너뜀)은 원래
 * 홈 대시보드(REQ-HOME-001)로 이어집니다. 홈이 아직 없어서 토스트만 띄우고 화면에
 * 머물러 있었는데, 사용자 입장에서는 버튼을 눌렀는데 아무 일도 안 일어난 것으로 보입니다.
 * 홈이 만들어지면 이 화면으로 오던 세 경로를 홈으로 돌리고 이 파일은 지웁니다.
 */
type FlowReason = 'schedule-saved' | 'schedule-skipped' | 'no-medication';

interface FlowCompleteState {
  reason?: FlowReason;
}

const MESSAGE: Record<FlowReason, { title: string; body: string }> = {
  'schedule-saved': {
    title: '복약 시간을 저장했어요',
    body: '설정한 시각에 복약 알림을 보냅니다. 마이페이지에서 언제든 다시 바꿀 수 있어요.',
  },
  'schedule-skipped': {
    title: '기본 시간으로 설정했어요',
    body: '아침·저녁 기본 시각으로 알림을 보냅니다. 마이페이지에서 언제든 다시 바꿀 수 있어요.',
  },
  'no-medication': {
    title: '진료기록을 저장했어요',
    body: '등록한 문서에서 복약 정보가 확인되지 않아 복약 시간 설정은 건너뛰었어요.',
  },
};

const FALLBACK = {
  title: '문서 등록을 마쳤어요',
  body: '진료기록이 저장되었습니다.',
};

export function DevFlowComplete() {
  const navigate = useNavigate();
  const location = useLocation();
  const reason = (location.state as FlowCompleteState | null)?.reason;
  const message = reason ? MESSAGE[reason] : FALLBACK;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="등록 완료" />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <p className="text-base text-foreground">{message.title}</p>

        <Card tone="info">{message.body}</Card>

        <Card title="여기까지가 현재 구현 범위입니다">
          홈 대시보드(REQ-HOME-001)는 다음 단계에서 연결됩니다. 이 화면은 개발용 임시
          화면이며 실제 앱에서는 홈으로 바로 이동합니다.
        </Card>

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button onClick={() => navigate('/dev/document-upload')}>
            처음부터 다시 보기
          </Button>
          <Button variant="secondary" onClick={() => navigate('/dev/gallery')}>
            컴포넌트 갤러리
          </Button>
        </div>
      </main>
    </div>
  );
}
